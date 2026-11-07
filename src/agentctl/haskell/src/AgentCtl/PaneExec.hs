-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.PaneExec (PaneError (..), run, readStatus) where

import AgentCtl.Native (NativeError (..), snapshot)
import qualified AgentCtl.PaneExec.Spec as Spec
import qualified AgentCtl.Process as Process
import Control.Concurrent (threadDelay)
import Control.Exception (IOException, catch)
import Data.Aeson (eitherDecodeStrict', encode)
import qualified Data.ByteString.Lazy as Bytes
import Data.Either (fromRight)
import qualified Data.Map.Strict as Map
import Data.Text (Text)
import qualified Data.Text as Text
import GHC.Clock (getMonotonicTimeNSec)
import System.Directory (canonicalizePath, removeFile, renameFile)
import System.Environment (getEnvironment)
import System.FilePath (isAbsolute, takeDirectory)
import qualified System.FilePath.Windows as Windows
import System.IO (hClose, hSetBinaryMode)
import System.IO.Temp (withTempFile)
import qualified System.Info as System

data PaneError
  = InvalidSpecPath
  | SpecTimedOut
  | NativeReadFailed NativeError
  | UnsafeSpec
  | InvalidSpec
  | InvalidStatus
  | ProgramFailed Process.ProcessError
  | StateFailed Text
  deriving (Eq, Show)

run :: FilePath -> IO (Either PaneError Int)
run path
  | not (isAbsolute path) || '\0' `elem` path = pure (Left InvalidSpecPath)
  | otherwise = execute `catch` refused
  where
    execute = do
      began <- toInteger <$> getMonotonicTimeNSec
      result <- awaitSpec (began + 30000000000) path
      case result of
        Left failure -> pure (Left failure)
        Right spec -> launch path spec

refused :: IOException -> IO (Either PaneError value)
refused exception = pure (Left (StateFailed (Text.pack (show exception))))

awaitSpec :: Integer -> FilePath -> IO (Either PaneError Spec.Spec)
awaitSpec deadline path = do
  result <- snapshot path
  case result of
    Left (SnapshotFailed code)
      | code == 2 || (System.os == "mingw32" && code == 3) -> do
          now <- toInteger <$> getMonotonicTimeNSec
          if now >= deadline
            then pure (Left SpecTimedOut)
            else threadDelay 10000 >> awaitSpec deadline path
    Left failure -> pure (Left (NativeReadFailed failure))
    Right (access, bytes)
      | not (Spec.accepts access) -> pure (Left UnsafeSpec)
      | otherwise -> pure (either (const (Left InvalidSpec)) Right (Spec.decodeSpec bytes))

launch :: FilePath -> Spec.Spec -> IO (Either PaneError Int)
launch path spec = case Spec.argv spec of
  [] -> pure (Left InvalidSpec)
  executable : arguments
    | not (isAbsolute (Spec.statusPath spec)) || '\0' `elem` Spec.statusPath spec || Spec.statusPath spec == path -> pure (Left InvalidSpec)
    | otherwise -> do
        specDirectory <- canonicalizePath (takeDirectory path)
        statusDirectory <- canonicalizePath (takeDirectory (Spec.statusPath spec))
        specCanonical <- canonicalizePath path
        statusCanonical <- canonicalizePath (Spec.statusPath spec)
        pane <- Map.fromList <$> getEnvironment
        let program = Process.Program executable arguments (Spec.cwd spec) (Map.toList (Spec.paneEnvironment (Spec.environment spec) pane))
        case Process.validateProgram program of
          Just failure -> pure (Left (ProgramFailed failure))
          Nothing
            | not (samePath specDirectory statusDirectory) || samePath specCanonical statusCanonical -> pure (Left InvalidSpec)
            | otherwise -> do
                removeFile path
                if System.os == "mingw32"
                  then do
                    result <- Process.foregroundClient program
                    writeStatus (Spec.statusPath spec) (fromRight 1 result)
                    pure (either (Left . ProgramFailed) Right result)
                  else Left . ProgramFailed <$> Process.replace program

writeStatus :: FilePath -> Int -> IO ()
writeStatus path status =
  withTempFile (takeDirectory path) "agentctl-status-" $ \temporary handle -> do
    hSetBinaryMode handle True
    Bytes.hPut handle (encode status)
    hClose handle
    renameFile temporary path

readStatus :: FilePath -> IO (Either PaneError Int)
readStatus path
  | not (isAbsolute path) || '\0' `elem` path = pure (Left InvalidSpecPath)
  | otherwise = execute `catch` refused
  where
    execute = do
      result <- snapshot path
      pure $ case result of
        Left failure -> Left (NativeReadFailed failure)
        Right (access, bytes)
          | not (Spec.accepts access) -> Left UnsafeSpec
          | otherwise -> case eitherDecodeStrict' bytes of
              Right status | status >= 0 -> Right status
              _ -> Left InvalidStatus

samePath :: FilePath -> FilePath -> Bool
samePath = if System.os == "mingw32" then Windows.equalFilePath else (==)
