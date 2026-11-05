-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Supervisor.Lock (Kind (..), LockError (..), lockPath, withLock) where

import qualified AgentCtl.Native as Native
import qualified AgentCtl.Paths as Paths
import Control.Concurrent (threadDelay)
import Control.Exception (IOException, catch)
import Data.Text (Text)
import qualified Data.Text as Text
import GHC.Clock (getMonotonicTimeNSec)
import qualified System.Directory as Directory
import System.FilePath (takeDirectory, (</>))

data Kind = Supervisor | WatchRegistry deriving (Eq, Show)

data LockError = NativeFailure Native.NativeError | LockIO Text deriving (Eq, Show)

lockPath :: Paths.Paths -> Kind -> FilePath
lockPath paths kind =
  Paths.stateDirectory paths </> "locks" </> case kind of
    Supervisor -> "supervisor.lock"
    WatchRegistry -> "watch.lock"

withLock :: Paths.Paths -> Kind -> IO value -> IO (Either LockError value)
withLock paths kind action = execute `catch` refused
  where
    state = Paths.stateDirectory paths
    execute = do
      Directory.createDirectoryIfMissing True (takeDirectory state)
      prepared <- Native.prepareStateDirectory state
      case prepared of
        Left failure -> pure (Left (NativeFailure failure))
        Right () -> do
          private <- Native.ensurePrivateDirectory (state </> "locks")
          case private of
            Left failure -> pure (Left (NativeFailure failure))
            Right () -> do
              began <- getMonotonicTimeNSec
              acquire (began + 5000000000)
    acquire deadline = do
      result <- Native.withFileLock (lockPath paths kind) action
      case result of
        Left (Native.LockBusy _) | kind == WatchRegistry -> do
          now <- getMonotonicTimeNSec
          if now < deadline then threadDelay 10000 >> acquire deadline else pure (either (Left . NativeFailure) Right result)
        _ -> pure (either (Left . NativeFailure) Right result)
    refused :: IOException -> IO (Either LockError value)
    refused exception = pure (Left (LockIO (Text.pack (show exception))))
