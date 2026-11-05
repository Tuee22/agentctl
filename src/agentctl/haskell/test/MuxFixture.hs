-- Copyright (c) 2026 agentctl contributors.
module MuxFixture (run) where

import qualified AgentCtl.Mux as Mux
import qualified AgentCtl.Mux.Command as Command
import qualified AgentCtl.Observe.Capture as Capture
import qualified AgentCtl.PaneExec as PaneExec
import qualified AgentCtl.Process as Process
import Data.Aeson (Value, eitherDecode, encode, object, toJSON, withObject, (.!=), (.:), (.:?), (.=))
import Data.Aeson.Types (parseEither)
import qualified Data.ByteString.Lazy.Char8 as Bytes
import qualified Data.Text as Text
import System.Environment (getEnvironment)
import System.Exit (die, exitFailure)

run :: IO ()
run = do
  input <- Bytes.getContents
  value <- either die pure (eitherDecode input)
  operation <- either die pure (parseEither (withObject "fixture" (.: "operation")) value)
  case (operation :: Text.Text) of
    "status" -> do
      path <- either die pure (parseEither (withObject "status" (.: "path")) value)
      result <- PaneExec.readStatus path
      either refused (Bytes.putStrLn . encode) result
    "command" -> command value
    "capture" -> capture value
    "request-reap" -> reap value
    _ -> die "unknown mux fixture operation"

capture :: Value -> IO ()
capture value = do
  (directory, pane) <- either die pure (parseEither context value)
  family <- maybe (die "unsupported native capture host") pure Mux.hostFamily
  environment <- getEnvironment
  resolved <- Mux.resolve family "unknown" directory environment
  mux <- either refused pure resolved
  result <- Capture.capture mux pane (Process.CommandContext directory environment 10000000)
  case result of
    Left failure -> refused failure
    Right screen -> Bytes.putStrLn (encode (object ["text" .= Capture.screenText screen, "dead" .= Capture.screenDead screen, "visual" .= Capture.screenVisual screen]))
  where
    context = withObject "capture context" $ \fields -> do
      directory <- fields .: "directory"
      pane <- fields .: "pane" >>= maybe (fail "invalid pane id") pure . Command.makePane
      pure (directory, pane)

command :: Value -> IO ()
command value = do
  (directory, limit, foreground) <- either die pure (parseEither context value)
  action <- either die pure (parseEither Command.parseCommand value)
  family <- maybe (die "unsupported native fixture host") pure Mux.hostFamily
  environment <- getEnvironment
  resolved <- Mux.resolve family "unknown" directory environment
  mux <- either refused pure resolved
  let settings = Process.CommandContext directory environment limit
  if foreground
    then do
      result <- Process.foregroundCommand mux action settings
      either refused (Bytes.putStrLn . encode . toJSON) result
    else do
      result <- Process.runCommand mux action settings
      case result of
        Left failure -> refused failure
        Right output -> Bytes.putStrLn (encode (object ["code" .= Process.exitCode output, "stdout" .= Process.stdoutText output, "stderr" .= Process.stderrText output]))
  where
    context = withObject "context" $ \fields ->
      (,,) <$> fields .: "directory" <*> (fields .:? "deadline" .!= 10000000) <*> (fields .:? "foreground" .!= False)

reap :: Value -> IO ()
reap value = do
  directory <- either die pure (parseEither (withObject "reap context" (.: "directory")) value)
  family <- maybe (die "unsupported native reap host") pure Mux.hostFamily
  environment <- getEnvironment
  resolved <- Mux.resolve family "unknown" directory environment
  mux <- either refused pure resolved
  result <- Process.requestReap mux (Process.CommandContext directory environment 10000000)
  either refused (\() -> Bytes.putStrLn (encode (object ["code" .= (0 :: Int)]))) result

refused :: (Show error) => error -> IO value
refused failure = Bytes.putStrLn (encode (object ["error" .= show failure])) >> exitFailure
