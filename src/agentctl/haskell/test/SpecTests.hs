-- Copyright (c) 2026 agentctl contributors.
{-# LANGUAGE ForeignFunctionInterface #-}

module SpecTests (tests) where

import AgentCtl.Native (NativeError (..), snapshot)
import qualified AgentCtl.Native as Native
import qualified AgentCtl.PaneExec as PaneExec
import AgentCtl.PaneExec.Spec (Access (..), Spec (..), accepts, decodeSpec, encodeSpec, paneEnvironment)
import Control.Monad (forM_)
import qualified Data.ByteString as Bytes
import qualified Data.Map.Strict as Map
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Text
import Foreign.C.String (CString)
import Foreign.C.Types (CInt (..))
import System.Directory (createDirectory)
import System.FilePath ((</>))
import System.IO (hClose, hSetFileSize, openBinaryTempFile)
import System.IO.Temp (withSystemTempDirectory)
import Test.Tasty (TestTree, testGroup)
import Test.Tasty.HUnit (assertBool, assertFailure, testCase, (@?=))

tests :: [TestTree]
tests =
  [ testGroup
      "PaneExec"
      [ testCase "spec-round-trip" codec,
        testCase "pane-environment" environmentControl
      ],
    testGroup
      "SpecReal"
      [ testCase "snapshot-is-owned-and-private" privateSnapshot,
        testCase "missing-spec-is-refused" missingSnapshot,
        testCase "oversized-spec-is-refused" oversizedSnapshot,
        testCase "status-file-validation" statusControl,
        testCase "state-directory-preparation" stateDirectoryControl
      ]
  ]

codec :: IO ()
codec = do
  let spec =
        Spec
          ["/owned agent/program", "--", "", "x;", "#{pane_id}", "#(id)", "$(id)", "one\ntwo", "λ日"]
          "/owned folder/#project"
          (Map.fromList [("TOKEN", "λ日\n$(id)=value"), ("EMPTY", ""), ("PATH", "/a path/bin:/usr/bin")])
          "/owned folder/launch/status.json"
  assertBool "spec codec dropped environment or argv" (decodeSpec (encodeSpec spec) == Right spec)
  assertBool "invalid spec decoded" (case decodeSpec "{}" of Left _ -> True; Right _ -> False)

environmentControl :: IO ()
environmentControl = do
  let supplied = Map.fromList [("TOKEN", "literal"), ("TERM", "caller"), ("TMUX", "caller-server"), ("TMUX_PANE", "%0")]
      pane = Map.fromList [("TERM", "screen"), ("TMUX", "pane-server"), ("TMUX_PANE", "%12"), ("SERVER_ONLY", "hidden")]
  paneEnvironment supplied pane @?= Map.fromList [("TOKEN", "literal"), ("TERM", "screen"), ("TMUX", "pane-server"), ("TMUX_PANE", "%12")]
  paneEnvironment supplied Map.empty @?= Map.singleton "TOKEN" "literal"

withFixture :: (FilePath -> IO ()) -> IO ()
withFixture action = withSystemTempDirectory "agentctl-spec-" $ \directory -> do
  Native.prepareStateDirectory directory >>= (@?= Right ())
  (path, handle) <- openBinaryTempFile directory "spec-"
  Bytes.hPut handle (Bytes.pack [0, 13, 10, 255])
  hClose handle
  action path

assertPrivate :: FilePath -> IO ()
assertPrivate path = do
  result <- snapshot path
  case result of
    Right (access, bytes) -> do
      assertBool ("native private spec access refused: " ++ show access) (accepts access)
      bytes @?= Bytes.pack [0, 13, 10, 255]
    Left failure -> assertFailure (show failure)

privateSnapshot :: IO ()
privateSnapshot = withFixture $ \path -> do
  assertPrivate path
  invalid <- snapshot (path ++ "\0other")
  invalid @?= Left InvalidPath

missingSnapshot :: IO ()
missingSnapshot = withSystemTempDirectory "agentctl-missing-spec-" $ \directory -> do
  withFixture assertPrivate
  result <- snapshot (directory </> "missing")
  case result of
    Left (SnapshotFailed _) -> pure ()
    _ -> assertFailure (show result)

oversizedSnapshot :: IO ()
oversizedSnapshot = withSystemTempDirectory "agentctl-large-spec-" $ \directory -> do
  Native.prepareStateDirectory directory >>= (@?= Right ())
  withFixture assertPrivate
  (path, handle) <- openBinaryTempFile directory "large-"
  hSetFileSize handle (32 * 1024 * 1024 + 1)
  hClose handle
  result <- snapshot path
  case result of
    Left (SnapshotFailed _) -> pure ()
    _ -> assertFailure (show result)

statusControl :: IO ()
statusControl = withSystemTempDirectory "agentctl-status-" $ \directory -> do
  Native.prepareStateDirectory directory >>= (@?= Right ())
  (path, handle) <- openBinaryTempFile directory "status-"
  hClose handle
  forM_
    [("0", Right 0), ("3", Right 3), ("-1", Left PaneExec.InvalidStatus), ("true", Left PaneExec.InvalidStatus), ("bad-json", Left PaneExec.InvalidStatus)]
    $ \(bytes, expected) -> do
      Bytes.writeFile path bytes
      result <- PaneExec.readStatus path
      result @?= expected
  relative <- PaneExec.readStatus "relative"
  relative @?= Left PaneExec.InvalidSpecPath
  invalidPath <- PaneExec.readStatus (path ++ "\0other")
  invalidPath @?= Left PaneExec.InvalidSpecPath
  missing <- PaneExec.readStatus (directory </> "missing")
  case missing of
    Left (PaneExec.NativeReadFailed (SnapshotFailed _)) -> pure ()
    _ -> assertFailure (show missing)

foreign import ccall safe "agentctl_test_public_state"
  nativePublicState :: CString -> IO CInt

stateDirectoryControl :: IO ()
stateDirectoryControl = withSystemTempDirectory "agentctl-owned-state-" $ \root -> do
  let directory = root </> "state"
  createDirectory directory
  public <- Bytes.useAsCString (Text.encodeUtf8 (Text.pack directory)) nativePublicState
  public @?= 0
  unsafe <- Native.ensurePrivateDirectory directory
  case unsafe of
    Left (DirectoryFailed _) -> pure ()
    _ -> assertFailure (show unsafe)
  (retained, retainedHandle) <- openBinaryTempFile directory "existing-child-"
  Bytes.hPut retainedHandle (Bytes.pack [9, 8, 7])
  hClose retainedHandle
  before <- snapshot retained
  prepared <- Native.prepareStateDirectory directory
  prepared @?= Right ()
  after <- snapshot retained
  case (before, after) of
    (Right (initial, initialBytes), Right (final, finalBytes)) ->
      (fileKind final, fileOwned final, fileMode final, finalBytes) @?= (fileKind initial, fileOwned initial, fileMode initial, initialBytes)
    _ -> assertFailure (show (before, after))
  repeated <- Native.prepareStateDirectory directory
  repeated @?= Right ()
  (path, handle) <- openBinaryTempFile directory "registry-"
  Bytes.hPut handle (Bytes.pack [0, 13, 10, 255])
  hClose handle
  assertPrivate path
  refused <- Native.prepareStateDirectory path
  case refused of
    Left (DirectoryFailed _) -> pure ()
    _ -> assertFailure (show refused)
  assertPrivate path
  invalid <- Native.prepareStateDirectory (directory ++ "\0other")
  invalid @?= Left InvalidPath
