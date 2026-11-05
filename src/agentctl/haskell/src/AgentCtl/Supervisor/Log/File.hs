-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Supervisor.Log.File (Writer, FileError (..), logPath, withWriter, append, load) where

import qualified AgentCtl.Native as Native
import qualified AgentCtl.PaneExec.Spec as Spec
import qualified AgentCtl.Paths as Paths
import qualified AgentCtl.Supervisor.Lock as Lock
import qualified AgentCtl.Supervisor.Log as Log
import Data.Aeson (encode)
import qualified Data.ByteString.Lazy as Bytes
import Data.Text (Text)
import qualified Data.Text.Encoding as Text
import System.FilePath ((</>))

newtype Writer = Writer FilePath

data FileError = NativeFailure Native.NativeError | UnsafeLog | InvalidLog Text | LockFailure Lock.LockError deriving (Eq, Show)

logPath :: Paths.Paths -> FilePath
logPath paths = Paths.stateDirectory paths </> "supervisor.jsonl"

withWriter :: Paths.Paths -> (Writer -> IO (Either FileError value)) -> IO (Either FileError value)
withWriter paths action = do
  result <- Lock.withLock paths Lock.Supervisor $ do
    previous <- snapshot paths False
    case previous of
      Left failure -> pure (Left failure)
      Right _ -> action (Writer (logPath paths))
  pure (either (Left . LockFailure) id result)

append :: Writer -> [Log.Record] -> IO (Either FileError ())
append _ [] = pure (Right ())
append (Writer path) records = do
  written <- Native.appendLog path (Bytes.toStrict (mconcat [encode record <> "\n" | record <- records]))
  pure (either (Left . NativeFailure) Right written)

load :: Paths.Paths -> IO (Either FileError [Log.Record])
load paths = do
  exclusive <- Lock.withLock paths Lock.Supervisor (snapshot paths False)
  case exclusive of
    Right records -> pure records
    Left (Lock.NativeFailure (Native.LockBusy _)) -> do
      observed <- snapshot paths True
      case observed of
        Left failure -> pure (Left failure)
        Right prefix -> do
          finished <- Lock.withLock paths Lock.Supervisor (snapshot paths False)
          pure $ case finished of
            Right records -> records
            Left (Lock.NativeFailure (Native.LockBusy _)) -> Right prefix
            Left failure -> Left (LockFailure failure)
    Left failure -> pure (Left (LockFailure failure))

snapshot :: Paths.Paths -> Bool -> IO (Either FileError [Log.Record])
snapshot paths writerActive = do
  observed <- Native.logSnapshot (logPath paths)
  pure $ case observed of
    Left (Native.SnapshotFailed code) | code == 2 || code == 3 -> Right []
    Left failure -> Left (NativeFailure failure)
    Right (access, bytes)
      | not (Spec.accepts access) -> Left UnsafeLog
      | otherwise -> case Text.decodeUtf8' bytes of
          Left _ -> Left (InvalidLog "invalid UTF-8 decision log")
          Right text -> either (Left . InvalidLog) Right (Log.decode writerActive text)
