-- Copyright (c) 2026 agentctl contributors.
{-# LANGUAGE ForeignFunctionInterface #-}

module ScriptedAgent (run, withInput, readInput, paneIdentity, writeOutput) where

import AgentCtl.Native (processId)
import Control.Concurrent (threadDelay)
import Control.Concurrent.Async (link, withAsync)
import Control.Concurrent.MVar (MVar, modifyMVar_, newMVar, readMVar)
import Control.Exception (bracket_)
import Control.Monad (unless, void, when)
import Data.Aeson (FromJSON (parseJSON), eitherDecodeStrict', encode, object, withObject, (.:), (.=))
import qualified Data.Aeson.KeyMap as Keys
import Data.Aeson.Types (Pair)
import qualified Data.ByteString as Bytes
import qualified Data.ByteString.Lazy as Lazy
import Data.List (sort)
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Text
import qualified Data.Text.IO as Text
import Data.Time (getCurrentTime)
import Foreign.C.String (CString)
import Foreign.C.Types (CInt (..), CSize (..))
import GHC.Clock (getMonotonicTimeNSec)
import System.Directory (doesFileExist, renameFile)
import System.Environment (lookupEnv)
import System.Exit (die)
import System.FilePath (isAbsolute, (</>))
import System.IO (BufferMode (NoBuffering), Handle, IOMode (AppendMode), hClose, hFlush, hSetBinaryMode, hSetBuffering, stdin, stdout, withBinaryFile)
import System.IO.Temp (withTempFile)
import qualified System.Info as System

data Advance = Input Integer | File FilePath | Delay Double | Stay

data Frame = Frame FilePath Advance

newtype Script = Script [Frame]

instance FromJSON Script where
  parseJSON = withObject "script" $ \fields -> do
    unless (Keys.keys fields == ["frames"]) (fail "invalid script fields")
    frames <- fields .: "frames"
    unless (not (null frames) && length frames <= 64) (fail "script needs 1 to 64 frames")
    pure (Script frames)

instance FromJSON Frame where
  parseJSON = withObject "script frame" $ \fields -> do
    unless (sort (Keys.keys fields) == ["after", "screen"]) (fail "invalid script frame fields")
    path <- fields .: "screen"
    unless (isAbsolute path && '\0' `notElem` path) (fail "script screen needs an absolute path")
    Frame path <$> fields .: "after"

instance FromJSON Advance where
  parseJSON = withObject "frame advance" $ \fields -> do
    kind <- fields .: "kind"
    case (kind :: Text.Text, sort (Keys.keys fields)) of
      ("input", ["bytes", "kind"]) -> do
        count <- fields .: "bytes"
        if count > 0 then pure (Input count) else fail "input threshold must be positive"
      ("file", ["kind", "path"]) -> do
        path <- fields .: "path"
        if isAbsolute path && '\0' `notElem` path then pure (File path) else fail "trigger needs an absolute path"
      ("delay", ["kind", "seconds"]) -> do
        seconds <- fields .: "seconds"
        if not (isNaN seconds || isInfinite seconds) && seconds > 0 && seconds <= 60 then pure (Delay seconds) else fail "frame delay must be in (0, 60]"
      ("stay", ["kind"]) -> pure Stay
      _ -> fail "invalid frame advance"

data Identity = Identity String Integer (Maybe Text.Text) (Maybe String)

foreign import ccall unsafe "agentctl_fake_raw_begin"
  rawBegin :: IO CInt

foreign import ccall unsafe "agentctl_fake_raw_end"
  rawEnd :: IO CInt

foreign import ccall unsafe "agentctl_fake_input_ready"
  inputReady :: IO CInt

foreign import ccall safe "agentctl_fake_console_write"
  consoleWrite :: CString -> CSize -> IO CInt

writeOutput :: Text.Text -> IO ()
writeOutput text = Bytes.useAsCStringLen (Text.encodeUtf8 text) $ \(bytes, size) -> do
  code <- consoleWrite bytes (fromIntegral size)
  if code == -1
    then Text.putStr text
    else when (code /= 0) (die ("fake console output failed: " ++ show code))

run :: FilePath -> String -> Maybe Text.Text -> [String] -> IO ()
run directory nonce session arguments = case arguments of
  "--agentctl-script" : path : _ -> do
    script <- Bytes.readFile path >>= either (die . ("invalid fake script: " ++)) pure . eitherDecodeStrict'
    pid <- processId
    pane <- lookupEnv "TMUX_PANE"
    let identity = Identity nonce pid session (paneIdentity session pane)
    mapM_ (initialise directory) ["received.jsonl", "frames.jsonl"]
    withInput $
      withBinaryFile (directory </> "received.jsonl") AppendMode $ \received ->
        withBinaryFile (directory </> "frames.jsonl") AppendMode $ \frames -> do
          count <- newMVar 0
          withAsync (receive identity received count) $ \worker -> do
            link worker
            play directory identity frames count script
  _ -> die "scripted fake agent needs --agentctl-script PATH"

paneIdentity :: Maybe Text.Text -> Maybe String -> Maybe String
paneIdentity session pane
  | System.os == "mingw32" = (\name identifier -> "=" ++ Text.unpack name ++ ":." ++ identifier) <$> session <*> pane
  | otherwise = pane

withInput :: IO value -> IO value
withInput action = do
  hSetBinaryMode stdin True
  hSetBuffering stdin NoBuffering
  bracket_ (raw rawBegin) (raw rawEnd) action
  where
    raw operation = do
      code <- operation
      when (code /= 0) (die ("fake raw input failed: " ++ show code))

initialise :: FilePath -> FilePath -> IO ()
initialise directory name = withTempFile directory "script-log-" $ \temporary handle -> do
  hClose handle
  renameFile temporary (directory </> name)

writeEvent :: Identity -> Handle -> [Pair] -> IO ()
writeEvent (Identity nonce pid session pane) handle fields = do
  now <- getMonotonicTimeNSec
  utc <- getCurrentTime
  let record = object (["nonce" .= nonce, "pid" .= pid, "session" .= session, "pane" .= pane, "monotonic_ns" .= now, "utc" .= utc] ++ fields)
  Lazy.hPut handle (encode record <> "\n")
  hFlush handle

readInput :: IO (Maybe Bytes.ByteString)
readInput = do
  ready <- inputReady
  case ready of
    0 -> pure Nothing
    1 -> Just <$> Bytes.hGetSome stdin 4096
    _ -> die "fake input readiness failed"

receive :: Identity -> Handle -> MVar Integer -> IO ()
receive identity handle count = do
  chunk <- readInput
  case chunk of
    Nothing -> threadDelay 10000 >> receive identity handle count
    Just bytes ->
      unless (Bytes.null bytes) $ do
        modifyMVar_ count $ \previous -> do
          let next = previous + toInteger (Bytes.length bytes)
          writeEvent identity handle ["bytes" .= Bytes.unpack bytes, "total" .= next]
          pure next
        receive identity handle count

play :: FilePath -> Identity -> Handle -> MVar Integer -> Script -> IO ()
play directory identity handle count (Script frames) = advance 0 frames
  where
    advance :: Int -> [Frame] -> IO ()
    advance _ [] = void (waitUntil (pure False))
    advance index (Frame path trigger : remaining) = do
      previous <- readMVar count
      bytes <- Bytes.readFile path
      text <- either (die . show) pure (Text.decodeUtf8' bytes)
      writeOutput ("\ESC[2J\ESC[3J\ESC[H" <> text)
      hFlush stdout
      writeEvent identity handle ["index" .= index, "screen" .= path]
      began <- getMonotonicTimeNSec
      continued <- waitUntil (condition previous began trigger)
      when continued (advance (index + 1) remaining)
    condition previous began trigger = case trigger of
      Input threshold -> (>= previous + threshold) <$> readMVar count
      File path -> doesFileExist path
      Delay seconds -> do
        now <- getMonotonicTimeNSec
        pure (toInteger now - toInteger began >= round (seconds * 1000000000))
      Stay -> pure False
    waitUntil predicate = do
      stopped <- doesFileExist (directory </> "stop")
      if stopped
        then pure False
        else do
          ready <- predicate
          if ready then pure True else threadDelay 10000 >> waitUntil predicate
