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
import Data.Aeson (Value, encode, object, (.=))
import qualified Data.ByteString.Lazy as Bytes
import Foreign.C.Types (CInt (..), CLLong (..))
import GHC.Clock (getMonotonicTimeNSec)
import System.Directory (doesFileExist, getCurrentDirectory, renameFile)
import System.Environment (getEnvironment)
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
run [core, kind, trigger, destination, pollSeconds, initialSeconds, maximumSeconds, nonce] = do
  unless (Mux.hostFamily == Just Mux.Windows) (die "console fixture requires native Windows")
  interrupt <- case kind of
    "interrupt" -> pure True
    "terminate" -> pure False
    _ -> die "unknown console signal"
  environment <- getEnvironment
  directory <- getCurrentDirectory
  paths <- either (die . show) pure (Paths.fromEnvironment True environment)
  code <- ignoreControl
  when (code /= 0) (die ("cannot install fixture console handler: " ++ show code))
  let childEnvironment = ("AGENTCTL_PROTOCOL_VERSION", "1") : filter (\(key, _) -> key `notElem` ["TMUX", "TMUX_PANE", "AGENTCTL_PROTOCOL_VERSION"]) environment
      arguments = ["supervisor", "run", "--poll-seconds", pollSeconds, "--initial-delay-seconds", initialSeconds, "--max-delay-seconds", maximumSeconds, "--jitter-fraction", "0"]
      child =
        if interrupt
          then fmap (\status -> Process.Output status "" "") <$> Process.foreground (Process.Program core arguments directory childEnvironment)
          else Process.run (Process.Invocation core arguments directory childEnvironment 300000000)
  withAsync child $ \worker -> do
    began <- getMonotonicTimeNSec
    let awaitController = do
          holder <- Lock.withLock paths Lock.Supervisor (pure ())
          case holder of
            Left (Lock.NativeFailure (Native.LockBusy (Just value))) -> pure value
            Right () -> do
              now <- getMonotonicTimeNSec
              when (now - began >= 10000000000) (die "console fixture did not find its live controller lock")
              threadDelay 10000 >> awaitController
            _ -> die ("console fixture cannot observe its controller lock: " ++ show holder)
        awaitTrigger = do
          ready <- doesFileExist trigger
          unless ready $ do
            now <- getMonotonicTimeNSec
            when (now - began >= 240000000000) (die "console fixture trigger timed out")
            completed <- poll worker
            case completed of
              Just result -> die ("controller exited before its signal: " ++ show result)
              Nothing -> threadDelay 10000 >> awaitTrigger
    pid <- awaitController
    writeResult (destination ++ ".pid") (object ["nonce" .= nonce, "pid" .= pid])
    awaitTrigger
    signalled <- signalControl (fromInteger pid) (if interrupt then 1 else 0)
    when (signalled /= 0) (die ("cannot signal private console controller: " ++ show signalled))
    completed <- timeout 10000000 (wait worker)
    output <- case completed of
      Nothing -> die "private console controller did not exit after its signal"
      Just result -> either (die . show) pure result
    writeResult destination (object ["nonce" .= nonce, "pid" .= pid, "status" .= Process.exitCode output, "stdout" .= Process.stdoutText output, "stderr" .= Process.stderrText output])
run _ = die "invalid console fixture arguments"

writeResult :: FilePath -> Value -> IO ()
writeResult destination value = withTempFile (takeDirectory destination) "console-result-" $ \temporary handle -> do
  hSetBinaryMode handle True
  Bytes.hPut handle (encode value)
  hClose handle
  renameFile temporary destination
