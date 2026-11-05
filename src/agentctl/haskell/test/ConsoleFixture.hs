-- Copyright (c) 2026 agentctl contributors.
{-# LANGUAGE ForeignFunctionInterface #-}

module ConsoleFixture (run) where

import qualified AgentCtl.Mux as Mux
import qualified AgentCtl.Native as Native
import qualified AgentCtl.Paths as Paths
import qualified AgentCtl.Process as Process
import qualified AgentCtl.Supervisor.Lock as Lock
import Control.Concurrent (threadDelay)
import Control.Concurrent.Async (poll, wait, withAsync)
import Control.Monad (unless, when)
import Data.Aeson (encode, object, (.=))
import qualified Data.ByteString.Lazy as Bytes
import Foreign.C.Types (CInt (..), CLLong (..))
import GHC.Clock (getMonotonicTimeNSec)
import System.Directory (doesFileExist, getCurrentDirectory, renameFile)
import System.Environment (getEnv, getEnvironment)
import System.Exit (die)
import System.FilePath (takeDirectory)
import System.IO (hClose, hSetBinaryMode)
import System.IO.Temp (withTempFile)
import System.Timeout (timeout)

foreign import ccall safe "agentctl_fixture_console_ignore"
  ignoreControl :: IO CInt

foreign import ccall safe "agentctl_fixture_console_signal"
  signalControl :: CLLong -> CInt -> IO CInt

run :: [String] -> IO ()
run [core, kind, trigger, destination] = do
  unless (Mux.hostFamily == Just Mux.Windows) (die "console fixture requires native Windows")
  interrupt <- case kind of
    "interrupt" -> pure True
    "terminate" -> pure False
    _ -> die "unknown console signal"
  environment <- getEnvironment
  directory <- getCurrentDirectory
  nonce <- getEnv "AGENTCTL_FAKE_NONCE"
  paths <- either (die . show) pure (Paths.fromEnvironment True environment)
  code <- ignoreControl
  when (code /= 0) (die ("cannot install fixture console handler: " ++ show code))
  let childEnvironment = ("AGENTCTL_PROTOCOL_VERSION", "1") : filter (\(key, _) -> key `notElem` ["TMUX", "TMUX_PANE", "AGENTCTL_PROTOCOL_VERSION"]) environment
      arguments = ["supervisor", "run", "--poll-seconds", "0.05", "--initial-delay-seconds", "0.3", "--max-delay-seconds", "1.2", "--jitter-fraction", "0"]
      child =
        if interrupt
          then fmap (\status -> Process.Output status "" "") <$> Process.foreground (Process.Program core arguments directory childEnvironment)
          else Process.run (Process.Invocation core arguments directory childEnvironment 60000000)
  withAsync child $ \worker -> do
    began <- getMonotonicTimeNSec
    let awaitTrigger = do
          ready <- doesFileExist trigger
          unless ready $ do
            now <- getMonotonicTimeNSec
            when (now - began >= 30000000000) (die "console fixture trigger timed out")
            completed <- poll worker
            case completed of
              Just result -> die ("controller exited before its signal: " ++ show result)
              Nothing -> threadDelay 10000 >> awaitTrigger
    awaitTrigger
    holder <- Lock.withLock paths Lock.Supervisor (pure ())
    pid <- case holder of
      Left (Lock.NativeFailure (Native.LockBusy (Just value))) -> pure value
      _ -> die "console fixture did not find its live controller lock"
    signalled <- signalControl (fromInteger pid) (if interrupt then 1 else 0)
    when (signalled /= 0) (die ("cannot signal private console controller: " ++ show signalled))
    completed <- timeout 10000000 (wait worker)
    output <- case completed of
      Nothing -> die "private console controller did not exit after its signal"
      Just result -> either (die . show) pure result
    withTempFile (takeDirectory destination) "console-result-" $ \temporary handle -> do
      hSetBinaryMode handle True
      Bytes.hPut handle (encode (object ["nonce" .= nonce, "pid" .= pid, "status" .= Process.exitCode output]))
      hClose handle
      renameFile temporary destination
run _ = die "invalid console fixture arguments"
