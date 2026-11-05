-- Copyright (c) 2026 agentctl contributors.
{-# LANGUAGE ForeignFunctionInterface #-}

module SupervisorTests (tests) where

import qualified AgentCtl.Native as Native
import qualified AgentCtl.PaneExec.Spec as Spec
import qualified AgentCtl.Paths as Paths
import qualified AgentCtl.Supervisor.Lock as Lock
import qualified AgentCtl.Supervisor.Log as Log
import qualified AgentCtl.Supervisor.Log.File as LogFile
import Data.Aeson (eitherDecodeStrict')
import qualified Data.ByteString.Char8 as Bytes
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Encoding
import Foreign.C.String (CString)
import Foreign.C.Types (CInt (..))
import qualified System.Directory as Directory
import System.FilePath ((</>))
import System.IO.Temp (withSystemTempDirectory)
import qualified System.Info as System
import Test.Tasty (TestTree, testGroup)
import Test.Tasty.HUnit (assertBool, assertFailure, testCase, (@?=))

tests :: [TestTree]
tests =
  [ testGroup
      "SupervisorReal"
      [ testCase "lock-contention-and-release" contention,
        testCase "lock-exception-releases" exceptionRelease,
        testCase "lock-refuses-directory" refusesDirectory,
        testCase "stop-handler-scope-reusable" stopScope,
        testCase "log-owned-append-and-read" appendAndRead,
        testCase "log-refuses-directory" appendDirectory,
        testCase "log-refuses-public-parent" appendPublicParent,
        testCase "log-writer-and-reader-share-history" fileHistory,
        testCase "log-tail-requires-active-writer" fileTail
      ]
  ]

withPaths :: (Paths.Paths -> IO ()) -> IO ()
withPaths action = withSystemTempDirectory "agentctl-supervisor-" $ \directory -> do
  canonical <- Directory.canonicalizePath directory
  case Paths.makePaths (System.os == "mingw32") (canonical </> "cache") (canonical </> "data") (canonical </> "state") of
    Left failure -> assertFailure (show failure)
    Right paths -> action paths

contention :: IO ()
contention = withPaths $ \paths -> do
  pid <- Native.processId
  first <- Lock.withLock paths Lock.Supervisor $ do
    second <- Lock.withLock paths Lock.Supervisor (pure False)
    second @?= Left (Lock.NativeFailure (Native.LockBusy (Just pid)))
    distinct <- Lock.withLock paths Lock.WatchRegistry (pure True)
    distinct @?= Right True
    stillHeld <- Lock.withLock paths Lock.Supervisor (pure False)
    stillHeld @?= Left (Lock.NativeFailure (Native.LockBusy (Just pid)))
  first @?= Right ()
  record <- Native.snapshot (Lock.lockPath paths Lock.Supervisor)
  case record of
    Left failure -> assertFailure (show failure)
    Right (access, bytes) -> do
      assertBool "lock record is not private" (Spec.accepts access)
      bytes @?= Bytes.pack ("\n" ++ show pid ++ "\n")
  third <- Lock.withLock paths Lock.Supervisor (pure True)
  third @?= Right True

exceptionRelease :: IO ()
exceptionRelease = withPaths $ \paths -> do
  failed <- Lock.withLock paths Lock.Supervisor (ioError (userError "owned exception control") :: IO ())
  case failed of
    Left (Lock.LockIO _) -> pure ()
    _ -> assertFailure "lock callback exception was not reported"
  next <- Lock.withLock paths Lock.Supervisor (pure True)
  next @?= Right True

refusesDirectory :: IO ()
refusesDirectory = withPaths $ \paths -> do
  initial <- Lock.withLock paths Lock.Supervisor (pure ())
  initial @?= Right ()
  let path = Lock.lockPath paths Lock.Supervisor
  Directory.removeFile path
  Directory.createDirectory path
  refused <- Lock.withLock paths Lock.Supervisor (pure True)
  case refused of
    Left (Lock.NativeFailure (Native.LockFailed code)) -> assertBool "missing native refusal code" (code > 0)
    _ -> assertFailure "directory was accepted as a lock file"
  Directory.doesDirectoryExist path >>= (@?= True)
  Directory.removeDirectory path
  next <- Lock.withLock paths Lock.Supervisor (pure True)
  next @?= Right True

stopScope :: IO ()
stopScope = do
  first <- Native.withStopRequests $ \requested -> do
    requested >>= (@?= False)
    nested <- Native.withStopRequests (\_ -> pure ())
    case nested of
      Left (Native.SignalFailed code) -> assertBool "missing nested-scope refusal code" (code > 0)
      _ -> assertFailure "nested stop handlers were accepted"
    requested >>= (@?= False)
  first @?= Right ()
  next <- Native.withStopRequests id
  next @?= Right False

appendAndRead :: IO ()
appendAndRead = withPaths $ \paths -> do
  Native.prepareStateDirectory (Paths.stateDirectory paths) >>= (@?= Right ())
  let path = Paths.stateDirectory paths </> "supervisor.jsonl"
      first = "{\"record\":1}\n"
      second = "{\"record\":2}\n"
  Native.appendLog path first >>= (@?= Right ())
  Native.appendLog path second >>= (@?= Right ())
  readBack path (first <> second)
  let large = Bytes.replicate (33 * 1024 * 1024) 'x'
  Native.appendLog path large >>= (@?= Right ())
  bounded <- Native.snapshot path
  case bounded of
    Left (Native.SnapshotFailed code) -> assertBool "missing spec size refusal code" (code > 0)
    _ -> assertFailure "launch-spec snapshot lost its size bound"
  readBack path (first <> second <> large)
  where
    readBack path expected = do
      observed <- Native.logSnapshot path
      case observed of
        Left failure -> assertFailure (show failure)
        Right (access, bytes) -> do
          assertBool "appended log is not private" (Spec.accepts access)
          assertBool "log append changed or truncated bytes" (bytes == expected)

appendDirectory :: IO ()
appendDirectory = withPaths $ \paths -> do
  Native.prepareStateDirectory (Paths.stateDirectory paths) >>= (@?= Right ())
  let path = Paths.stateDirectory paths </> "supervisor.jsonl"
  Directory.createDirectory path
  refused <- Native.appendLog path "refused\n"
  case refused of
    Left (Native.AppendFailed code) -> assertBool "missing native append refusal code" (code > 0)
    _ -> assertFailure "directory was accepted as a log"
  Directory.doesDirectoryExist path >>= (@?= True)
  Directory.removeDirectory path
  Native.appendLog path "accepted\n" >>= (@?= Right ())

foreign import ccall safe "agentctl_test_public_state"
  publicState :: CString -> IO CInt

appendPublicParent :: IO ()
appendPublicParent = withPaths $ \paths -> do
  let state = Paths.stateDirectory paths
      path = state </> "supervisor.jsonl"
  Native.prepareStateDirectory state >>= (@?= Right ())
  Native.appendLog path "private\n" >>= (@?= Right ())
  code <- Bytes.useAsCString (Encoding.encodeUtf8 (Text.pack state)) publicState
  code @?= 0
  refused <- Native.appendLog path "must not append\n"
  case refused of
    Left (Native.AppendFailed failure) -> assertBool "missing unsafe-parent refusal code" (failure > 0)
    _ -> assertFailure "log appended under a public parent"
  observed <- Native.logSnapshot path
  case observed of
    Left failure -> assertFailure (show failure)
    Right (access, bytes) -> do
      assertBool "public parent negative control was not constructed" (not (Spec.accepts access))
      bytes @?= "private\n"

withRecord :: (Log.Record -> IO ()) -> IO ()
withRecord action = case eitherDecodeStrict' "{\"time\":\"2026-11-04T00:00:00Z\",\"run\":\"native-owned\",\"target\":\"api-claude\",\"agent\":\"claude\",\"kind\":\"notify\",\"level\":\"info\",\"message\":\"native record control\"}" of
  Left failure -> assertFailure failure
  Right record -> action record

fileHistory :: IO ()
fileHistory = withPaths $ \paths -> withRecord $ \record -> do
  LogFile.load paths >>= (@?= Right [])
  written <- LogFile.withWriter paths $ \writer -> do
    LogFile.append writer [record] >>= (@?= Right ())
    LogFile.load paths >>= (@?= Right [record])
    LogFile.append writer [record] >>= (@?= Right ())
    LogFile.load paths >>= (@?= Right [record, record])
    pure (Right ())
  written @?= Right ()
  LogFile.load paths >>= (@?= Right [record, record])

fileTail :: IO ()
fileTail = withPaths $ \paths -> withRecord $ \record -> do
  written <- LogFile.withWriter paths $ \writer -> do
    LogFile.append writer [record] >>= (@?= Right ())
    Native.appendLog (LogFile.logPath paths) "{\"time\":" >>= (@?= Right ())
    LogFile.load paths >>= (@?= Right [record])
    pure (Right ())
  written @?= Right ()
  LogFile.load paths >>= (@?= Left (LogFile.InvalidLog "invalid decision log"))
  refused <- LogFile.withWriter paths (\_ -> pure (Right False))
  refused @?= Left (LogFile.InvalidLog "invalid decision log")
