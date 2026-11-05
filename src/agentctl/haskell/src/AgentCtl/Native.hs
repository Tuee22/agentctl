-- Copyright (c) 2026 agentctl contributors.
{-# LANGUAGE ForeignFunctionInterface #-}

module AgentCtl.Native (NativeError (..), snapshot, logSnapshot, appendLog, processId, ensurePrivateDirectory, prepareStateDirectory, signalNumber, withFileLock, withStopRequests) where

import AgentCtl.PaneExec.Spec (Access (..))
import Control.Exception (finally, mask, onException)
import Control.Monad (void)
import qualified Data.ByteString as Bytes
import Data.Maybe (fromMaybe)
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Text
import Foreign.C.String (CString)
import Foreign.C.Types (CInt (..), CLLong (..), CSize (..), CUInt (..))
import Foreign.Marshal.Alloc (alloca)
import Foreign.Marshal.Array (allocaArray, peekArray)
import Foreign.Ptr (Ptr, castPtr, nullPtr)
import Foreign.Storable (peek)
import System.FilePath (takeDirectory, takeFileName)

data NativeError = InvalidPath | SnapshotFailed Int | InvalidSnapshot | DirectoryFailed Int | LockBusy (Maybe Integer) | LockFailed Int | SignalFailed Int | AppendFailed Int deriving (Eq, Show)

foreign import ccall safe "agentctl_lock_take"
  nativeLockTake :: CString -> CString -> Ptr CLLong -> Ptr CInt -> IO (Ptr ())

foreign import ccall safe "agentctl_lock_release"
  nativeLockRelease :: Ptr () -> IO ()

withFileLock :: FilePath -> IO value -> IO (Either NativeError value)
withFileLock path action
  | '\0' `elem` path = pure (Left InvalidPath)
  | otherwise =
      withUtf8 (takeDirectory path) $ \directory ->
        withUtf8 (takeFileName path) $ \name ->
          alloca $ \ownerPointer ->
            alloca $ \errorPointer -> mask $ \restore -> do
              pointer <- nativeLockTake directory name ownerPointer errorPointer
              if pointer == nullPtr
                then do
                  code <- peek errorPointer
                  owner <- peek ownerPointer
                  pure (Left (if code == -1 then LockBusy (if owner > 0 then Just (fromIntegral owner) else Nothing) else LockFailed (fromIntegral code)))
                else Right <$> restore action `finally` nativeLockRelease pointer

foreign import ccall unsafe "agentctl_stop_begin"
  nativeStopBegin :: IO CInt

foreign import ccall unsafe "agentctl_stop_requested"
  nativeStopRequested :: IO CInt

foreign import ccall unsafe "agentctl_stop_end"
  nativeStopEnd :: IO CInt

withStopRequests :: (IO Bool -> IO value) -> IO (Either NativeError value)
withStopRequests action = mask $ \restore -> do
  began <- nativeStopBegin
  if began /= 0
    then pure (Left (SignalFailed (fromIntegral began)))
    else do
      value <- restore (action ((/= 0) <$> nativeStopRequested)) `onException` void nativeStopEnd
      ended <- nativeStopEnd
      pure (if ended == 0 then Right value else Left (SignalFailed (fromIntegral ended)))

foreign import ccall safe "agentctl_spec_snapshot"
  nativeSnapshot :: CString -> CString -> Ptr CUInt -> Ptr CSize -> Ptr CInt -> IO (Ptr ())

foreign import ccall safe "agentctl_log_snapshot"
  nativeLogSnapshot :: CString -> CString -> Ptr CUInt -> Ptr CSize -> Ptr CInt -> IO (Ptr ())

foreign import ccall safe "agentctl_log_append"
  nativeLogAppend :: CString -> CString -> CString -> CSize -> IO CInt

appendLog :: FilePath -> Bytes.ByteString -> IO (Either NativeError ())
appendLog path bytes
  | '\0' `elem` path = pure (Left InvalidPath)
  | otherwise =
      withUtf8 (takeDirectory path) $ \directory ->
        withUtf8 (takeFileName path) $ \name ->
          Bytes.useAsCStringLen bytes $ \(pointer, lengthValue) -> do
            code <- nativeLogAppend directory name pointer (fromIntegral lengthValue)
            pure (if code == 0 then Right () else Left (AppendFailed (fromIntegral code)))

foreign import ccall unsafe "agentctl_free"
  nativeFree :: Ptr () -> IO ()

foreign import ccall unsafe "agentctl_pid"
  nativePid :: IO CLLong

foreign import ccall safe "agentctl_private_directory"
  nativePrivateDirectory :: CString -> IO CInt

foreign import ccall safe "agentctl_state_directory"
  nativeStateDirectory :: CString -> IO CInt

ensurePrivateDirectory :: FilePath -> IO (Either NativeError ())
ensurePrivateDirectory = directoryCall nativePrivateDirectory

prepareStateDirectory :: FilePath -> IO (Either NativeError ())
prepareStateDirectory = directoryCall nativeStateDirectory

directoryCall :: (CString -> IO CInt) -> FilePath -> IO (Either NativeError ())
directoryCall operation path
  | '\0' `elem` path = pure (Left InvalidPath)
  | otherwise = withUtf8 path $ \pointer -> do
      code <- operation pointer
      pure (if code == 0 then Right () else Left (DirectoryFailed (fromIntegral code)))

foreign import ccall unsafe "agentctl_signal_number"
  nativeSignalNumber :: CString -> IO CInt

signalNumber :: Text.Text -> IO (Maybe Int)
signalNumber name = withUtf8 (Text.unpack normalised) $ \pointer -> do
  code <- nativeSignalNumber pointer
  pure (if code > 0 then Just (fromIntegral code) else Nothing)
  where
    upper = Text.toUpper name
    normalised = fromMaybe upper (Text.stripPrefix "SIG" upper)

processId :: IO Integer
processId = fromIntegral <$> nativePid

snapshot :: FilePath -> IO (Either NativeError (Access, Bytes.ByteString))
snapshot = snapshotWith nativeSnapshot

logSnapshot :: FilePath -> IO (Either NativeError (Access, Bytes.ByteString))
logSnapshot = snapshotWith nativeLogSnapshot

snapshotWith :: (CString -> CString -> Ptr CUInt -> Ptr CSize -> Ptr CInt -> IO (Ptr ())) -> FilePath -> IO (Either NativeError (Access, Bytes.ByteString))
snapshotWith operation path
  | '\0' `elem` path = pure (Left InvalidPath)
  | otherwise =
      withUtf8 (takeDirectory path) $ \directory ->
        withUtf8 (takeFileName path) $ \name ->
          allocaArray 6 $ \facts ->
            alloca $ \lengthPointer ->
              alloca $ \errorPointer -> mask $ \restore -> do
                pointer <- operation directory name facts lengthPointer errorPointer
                if pointer == nullPtr
                  then Left . SnapshotFailed . fromIntegral <$> peek errorPointer
                  else restore (copySnapshot pointer facts lengthPointer) `finally` nativeFree pointer

copySnapshot :: Ptr () -> Ptr CUInt -> Ptr CSize -> IO (Either NativeError (Access, Bytes.ByteString))
copySnapshot pointer facts lengthPointer = do
  values <- peekArray 6 facts
  lengthValue <- peek lengthPointer
  bytes <- Bytes.packCStringLen (castPtr pointer, fromIntegral lengthValue)
  pure $ case values of
    [kindValue, ownedValue, modeValue, parentKind, parentOwned, parentMode] ->
      Right (Access (kindValue /= 0) (ownedValue /= 0) (fromIntegral modeValue) (parentKind /= 0) (parentOwned /= 0) (fromIntegral parentMode), bytes)
    _ -> Left InvalidSnapshot

withUtf8 :: String -> (CString -> IO value) -> IO value
withUtf8 value = Bytes.useAsCString (Text.encodeUtf8 (Text.pack value))
