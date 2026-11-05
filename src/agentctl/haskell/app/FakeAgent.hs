-- Copyright (c) 2026 agentctl contributors.
{-# LANGUAGE ForeignFunctionInterface #-}

module Main (main) where

import qualified AgentCtl.Mux as Mux
import AgentCtl.Native (processId)
import qualified AgentCtl.Process as Process
import Control.Applicative ((<|>))
import Control.Concurrent (threadDelay)
import Control.Concurrent.Async (withAsync)
import Control.Monad (forever, unless, when)
import Data.Aeson (encode, object, (.=))
import qualified Data.ByteString.Lazy as Bytes
import Data.Char (isAlphaNum, isAscii)
import Data.List (sort)
import Data.Maybe (fromMaybe)
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Text
import qualified Data.Text.IO as Text
import Foreign.C.Types (CInt (..))
import GHC.Clock (getMonotonicTimeNSec)
import qualified ScriptedAgent
import qualified SupervisorFixture
import System.Directory (doesFileExist, getCurrentDirectory, removeFile, renameFile)
import System.Environment (getArgs, getEnv, getEnvironment, getProgName, lookupEnv)
import System.Exit (ExitCode (..), die, exitSuccess, exitWith)
import System.FilePath (isAbsolute, takeDirectory, takeFileName, (</>))
import System.IO (BufferMode (LineBuffering), hClose, hFlush, hSetBinaryMode, hSetBuffering, hSetEncoding, hSetNewlineMode, noNewlineTranslation, stderr, stdin, stdout, utf8)
import System.IO.Temp (withTempFile)
import Text.Read (readMaybe)

main :: IO ()
main = do
  arguments <- getArgs
  program <- takeFileName <$> getProgName
  backend <- lookupEnv "AGENTCTL_FAKE_MUX_EXECUTABLE"
  case backend of
    Just executable | program `elem` ["tmux", "psmux.exe"] -> relayMux executable arguments
    _ -> agent arguments

observerNonce :: [String] -> IO String
observerNonce arguments = do
  suppliedNonce <- lookupEnv "AGENTCTL_FAKE_NONCE"
  nonce <- maybe (die "fake agent needs an observer nonce") pure (findNonce arguments <|> suppliedNonce)
  when (null nonce || any (\character -> not (isAscii character && (isAlphaNum character || character `elem` (".-_" :: String)))) nonce) $
    die "invalid fake-agent nonce"
  pure nonce

relayMux :: FilePath -> [String] -> IO ()
relayMux executable arguments = do
  nonce <- observerNonce []
  directory <- getEnv "AGENTCTL_FAKE_MUX_RECORD_DIR"
  environment <- getEnvironment
  cwd <- getCurrentDirectory
  writeRecord directory nonce arguments environment Nothing
  forward <- SupervisorFixture.beforeClient nonce arguments
  unless forward (exitWith (ExitFailure 73))
  response <- lookupEnv "AGENTCTL_FAKE_MUX_PID_RESPONSE"
  case response of
    Just text | arguments == ["list-sessions", "-F", "#{pid}"] -> putStr text
    _ -> do
      result <- Process.foreground (Process.Program executable arguments cwd environment)
      status <- either (die . show) pure result
      when (status == 0) (releaseCapture executable arguments cwd environment)
      exitWith (if status == 0 then ExitSuccess else ExitFailure status)

releaseCapture :: FilePath -> [String] -> FilePath -> [(String, String)] -> IO ()
releaseCapture executable arguments cwd environment = case (lookup "AGENTCTL_FAKE_CAPTURE_RELEASE" environment, arguments) of
  (Just path, ["display-message", "-p", "-t", pane, "#{pane_dead}|#{cursor_x}|#{cursor_y}|#{pane_width}|#{pane_height}"]) -> do
    pending <- doesFileExist path
    when pending $ do
      removeFile path
      writeFile (takeDirectory path </> "render") "cursor-change"
      began <- toInteger <$> getMonotonicTimeNSec
      waitCursor pane (began + 10000000000)
  _ -> pure ()
  where
    waitCursor pane deadline = do
      now <- toInteger <$> getMonotonicTimeNSec
      when (now >= deadline) (die "native cursor change did not render")
      let remaining = fromInteger (max 1 ((deadline - now) `div` 1000))
      observed <- Process.run (Process.Invocation executable ["display-message", "-p", "-t", pane, "#{cursor_x}"] cwd environment remaining)
      case observed of
        Right output | Process.exitCode output == 0 && Text.strip (Process.stdoutText output) == "3" -> pure ()
        _ -> threadDelay 10000 >> waitCursor pane deadline

agent :: [String] -> IO ()
agent arguments = do
  nonce <- observerNonce arguments
  directory <- getEnv "AGENTCTL_FAKE_RECORD_DIR"
  launchDisposition <- getEnv "AGENTCTL_FAKE_EXIT"
  authDisposition <- lookupEnv "AGENTCTL_FAKE_AUTH_EXIT"
  let disposition = if arguments `elem` [["auth", "status"], ["login", "status"]] then fromMaybe launchDisposition authDisposition else launchDisposition
  environment <- getEnvironment
  cwd <- getCurrentDirectory
  session <- sessionName cwd environment
  when (disposition == "observe-reap") $ do
    code <- watchReap
    when (code /= 0) (die "fake agent cannot observe child notification")
  writeRecord directory nonce arguments environment session
  hSetEncoding stdout utf8
  hSetEncoding stdin utf8
  hSetNewlineMode stdout noNewlineTranslation
  hSetBuffering stdout LineBuffering
  unless (disposition `elem` ["fixture", "scripted"]) (Text.putStrLn (Text.pack ("ready:" ++ nonce)))
  case disposition of
    "stay" -> withAsync echo (\_ -> waitStop (directory </> "stop")) >> exitSuccess
    "wait-exit-3" -> waitStop (directory </> "stop") >> exitWith (ExitFailure 3)
    "fixture" -> playFixture directory arguments
    "scripted" -> ScriptedAgent.run directory nonce session arguments
    "observe-reap" -> waitReap directory nonce
    "closed-streams" -> do
      surviveHangup
      mapM_ hClose [stdin, stdout, stderr]
      waitStop (directory </> "stop")
      exitWith (ExitFailure 3)
    _ -> case readMaybe disposition of
      Just 0 -> exitSuccess
      Just status | status > 0 -> exitWith (ExitFailure status)
      _ -> die "invalid fake-agent exit status"

playFixture :: FilePath -> [String] -> IO ()
playFixture directory arguments = case arguments of
  "--agentctl-screen-fixture" : path : _ -> do
    waitStop (directory </> "render")
    marker <- Bytes.readFile (directory </> "render")
    drawFixture path
    changes path marker
  _ -> die "fake fixture mode needs a screen fixture path"
  where
    changes path previous = do
      stopped <- doesFileExist (directory </> "stop")
      unless stopped $ do
        current <- Bytes.readFile (directory </> "render")
        when (current /= previous) (drawFixture path)
        threadDelay 10000
        changes path current

drawFixture :: FilePath -> IO ()
drawFixture path = do
  bytes <- Bytes.readFile path
  text <- either (die . show) pure (Text.decodeUtf8' (Bytes.toStrict bytes))
  Text.putStr "\ESC[2J\ESC[3J\ESC[H"
  Text.putStr text
  hFlush stdout

writeRecord :: FilePath -> String -> [String] -> [(String, String)] -> Maybe Text.Text -> IO ()
writeRecord directory nonce arguments environment session = do
  unless (isAbsolute directory) (die "fake record directory must be absolute")
  cwd <- getCurrentDirectory
  pid <- processId
  let record =
        object
          [ "nonce" .= nonce,
            "argv" .= arguments,
            "cwd" .= cwd,
            "env_keys" .= sort (map fst environment),
            "session" .= session,
            "pane" .= lookup "TMUX_PANE" environment,
            "pid" .= pid
          ]
  withTempFile directory "record-" $ \temporary handle -> do
    hSetBinaryMode handle True
    Bytes.hPut handle (encode record)
    hClose handle
    renameFile temporary (directory </> (nonce ++ "." ++ show pid ++ ".json"))

foreign import ccall unsafe "agentctl_fake_ignore_hangup"
  ignoreHangup :: IO CInt

foreign import ccall unsafe "agentctl_fake_watch_reap"
  watchReap :: IO CInt

foreign import ccall unsafe "agentctl_fake_reap_received"
  receivedReap :: IO CInt

surviveHangup :: IO ()
surviveHangup = do
  code <- ignoreHangup
  when (code /= 0) (die "fake agent cannot ignore terminal hangup")

findNonce :: [String] -> Maybe String
findNonce ("--agentctl-observer-nonce" : nonce : _) = Just nonce
findNonce (_ : remaining) = findNonce remaining
findNonce [] = Nothing

echo :: IO ()
echo = forever (Text.getLine >>= Text.putStrLn . ("echo:" <>))

waitStop :: FilePath -> IO ()
waitStop path = do
  stopped <- doesFileExist path
  if stopped then pure () else threadDelay 10000 >> waitStop path

waitReap :: FilePath -> String -> IO ()
waitReap directory nonce = do
  received <- receivedReap
  stopped <- doesFileExist (directory </> "stop")
  if stopped
    then pure ()
    else
      if received /= 0
        then writeFile (directory </> "reaped") nonce >> waitStop (directory </> "stop")
        else threadDelay 10000 >> waitReap directory nonce

sessionName :: FilePath -> [(String, String)] -> IO (Maybe Text.Text)
sessionName cwd environment = case lookup "TMUX_PANE" environment of
  Nothing -> pure Nothing
  Just pane -> do
    family <- maybe (die "unsupported fake-agent host") pure Mux.hostFamily
    resolved <- Mux.resolve family "unknown" cwd environment
    mux <- either (die . show) pure resolved
    observed <- Process.run (Process.Invocation (Mux.muxExecutable mux) ["display-message", "-p", "-t", pane, "#{session_name}"] cwd environment 10000000)
    case observed of
      Right output | Process.exitCode output == 0 -> pure (Just (Text.strip (Process.stdoutText output)))
      _ -> die "cannot observe fake-agent session"
