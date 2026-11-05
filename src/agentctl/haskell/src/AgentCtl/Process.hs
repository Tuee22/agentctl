-- Copyright (c) 2026 agentctl contributors.
{-# LANGUAGE ForeignFunctionInterface #-}

module AgentCtl.Process
  ( Invocation (..),
    Program (..),
    CommandContext (..),
    Output (..),
    ProcessError (..),
    run,
    runStatus,
    runCommand,
    commandInvocation,
    foreground,
    foregroundCommand,
    replace,
    requestReap,
    validateProgram,
  )
where

import qualified AgentCtl.Mux.Command as Command
import qualified AgentCtl.Mux.Psmux as Psmux
import qualified AgentCtl.Mux.Tmux as Tmux
import AgentCtl.Mux.Types (Kind (..), Multiplexer, muxExecutable, muxKind)
import Control.Concurrent (threadDelay)
import Control.Concurrent.Async (concurrently)
import Control.Exception (IOException, catch)
import qualified Data.ByteString as Bytes
import Data.Char (isAscii, isDigit)
import Data.List (nub)
import Data.Maybe (fromMaybe)
import Data.Text (Text)
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Text
import Foreign.C.String (CString)
import Foreign.C.Types (CInt (..), CLLong (..))
import Foreign.Marshal.Array (withArray0)
import Foreign.Marshal.Utils (withMany)
import Foreign.Ptr (Ptr, nullPtr)
import GHC.Clock (getMonotonicTimeNSec)
import System.Exit (ExitCode (..))
import System.FilePath (isAbsolute)
import System.IO (IOMode (ReadMode), hFlush, hSetBinaryMode, stderr, stdout, withBinaryFile)
import qualified System.Info as System
import qualified System.Process as Native
import System.Timeout (timeout)
import Text.Read (readMaybe)

data Invocation = Invocation
  { executable :: FilePath,
    arguments :: [String],
    directory :: FilePath,
    environment :: [(String, String)],
    deadlineMicros :: Int
  }

data Program = Program FilePath [String] FilePath [(String, String)]

data CommandContext = CommandContext
  { workingDirectory :: FilePath,
    variables :: [(String, String)],
    timeLimitMicros :: Int
  }

data Output = Output
  { exitCode :: Int,
    stdoutText :: Text,
    stderrText :: Text
  }
  deriving (Eq, Show)

data ProcessError
  = RelativeExecutable FilePath
  | RelativeDirectory FilePath
  | InvalidProgram
  | InvalidDeadline
  | TimedOut
  | SpawnFailed Text
  | InvalidUtf8 Text
  | MissingOutputPipes
  | ExecFailed Int
  | ReadinessFailed Int Text
  | InvalidServerIdentity
  | ReapFailed Int
  deriving (Eq, Show)

run :: Invocation -> IO (Either ProcessError Output)
run = runWith decodeOutput

runStatus :: Invocation -> IO (Either ProcessError Int)
runStatus = runWith (\status _ _ -> Right status)

decodeOutput :: Int -> Bytes.ByteString -> Bytes.ByteString -> Either ProcessError Output
decodeOutput status outBytes errBytes =
  case (Text.decodeUtf8' outBytes, Text.decodeUtf8' errBytes) of
    (Right outText, Right errText) -> Right (Output status outText errText)
    (Left exception, _) -> Left (InvalidUtf8 (Text.pack (show exception)))
    (_, Left exception) -> Left (InvalidUtf8 (Text.pack (show exception)))

runWith :: (Int -> Bytes.ByteString -> Bytes.ByteString -> Either ProcessError value) -> Invocation -> IO (Either ProcessError value)
runWith summarize invocation
  | not (isAbsolute (executable invocation)) = pure (Left (RelativeExecutable (executable invocation)))
  | deadlineMicros invocation <= 0 = pure (Left InvalidDeadline)
  | otherwise = execute `catch` refused
  where
    refused :: IOException -> IO (Either ProcessError value)
    refused exception = pure (Left (SpawnFailed (Text.pack (show exception))))
    execute = withBinaryFile (if System.os == "mingw32" then "NUL" else "/dev/null") ReadMode $ \input -> do
      result <- timeout (deadlineMicros invocation) $
        Native.withCreateProcess (command input) $ \_ output errors process ->
          case (output, errors) of
            (Just out, Just err) -> do
              hSetBinaryMode out True
              hSetBinaryMode err True
              (outBytes, errBytes) <- concurrently (Bytes.hGetContents out) (Bytes.hGetContents err)
              status <- Native.waitForProcess process
              pure (summarize (statusCode status) outBytes errBytes)
            _ -> pure (Left MissingOutputPipes)
      pure (fromMaybe (Left TimedOut) result)
    command input =
      (Native.proc (executable invocation) (arguments invocation))
        { Native.cwd = Just (directory invocation),
          Native.env = Just (environment invocation),
          Native.std_in = Native.UseHandle input,
          Native.std_out = Native.CreatePipe,
          Native.std_err = Native.CreatePipe,
          Native.create_group = True,
          Native.use_process_jobs = True
        }

statusCode :: ExitCode -> Int
statusCode ExitSuccess = 0
statusCode (ExitFailure code) = code

renderCommand :: Kind -> Command.Command -> Command.Rendered
renderCommand kind = if kind == Psmux then Psmux.render else Tmux.render

commandInvocation :: Kind -> FilePath -> Command.Command -> CommandContext -> Invocation
commandInvocation kind executablePath command context =
  Invocation
    executablePath
    (Command.arguments (renderCommand kind command))
    (workingDirectory context)
    (variables context)
    (timeLimitMicros context)

runCommand :: Multiplexer -> Command.Command -> CommandContext -> IO (Either ProcessError Output)
runCommand mux command context
  | timeLimitMicros context <= 0 = pure (Left InvalidDeadline)
  | otherwise = do
      began <- toInteger <$> getMonotonicTimeNSec
      let deadline = began + toInteger (timeLimitMicros context) * 1000
          execute action = do
            now <- toInteger <$> getMonotonicTimeNSec
            if now >= deadline
              then pure (Left TimedOut)
              else
                run
                  ( commandInvocation
                      (muxKind mux)
                      (muxExecutable mux)
                      action
                      (context {timeLimitMicros = fromInteger (max 1 ((deadline - now) `div` 1000))})
                  )
          ready name original = do
            result <- execute (Command.HasSession name)
            case result of
              Right output
                | exitCode output == 0 -> pure (Right original)
                | exitCode output == 1 -> threadDelay 10000 >> ready name original
                | otherwise -> pure (Left (ReadinessFailed (exitCode output) (stderrText output)))
              Left failure -> pure (Left failure)
      result <- execute command
      case (command, result) of
        (Command.Create name _ _, Right output)
          | muxKind mux == Psmux && exitCode output == 0 -> ready name output
        _ -> pure result

foregroundCommand :: Multiplexer -> Command.Command -> CommandContext -> IO (Either ProcessError Int)
foregroundCommand mux command context =
  let invocation = commandInvocation (muxKind mux) (muxExecutable mux) command context
   in foreground (Program (executable invocation) (arguments invocation) (directory invocation) (environment invocation))

validateProgram :: Program -> Maybe ProcessError
validateProgram (Program path programArguments programDirectory programEnvironment)
  | not (isAbsolute path) = Just (RelativeExecutable path)
  | not (isAbsolute programDirectory) = Just (RelativeDirectory programDirectory)
  | any (elem '\0') (path : programDirectory : programArguments)
      || any (\(key, value) -> not (validKey key) || '\0' `elem` key || '\0' `elem` value) programEnvironment =
      Just InvalidProgram
  | otherwise = Nothing
  where
    validKey key = not (null key) && ('=' `notElem` key || (System.os == "mingw32" && driveKey key))
    driveKey ['=', drive, ':'] = drive `elem` ['A' .. 'Z'] || drive `elem` ['a' .. 'z']
    driveKey _ = False

foreground :: Program -> IO (Either ProcessError Int)
foreground program@(Program path programArguments programDirectory programEnvironment) = case validateProgram program of
  Just failure -> pure (Left failure)
  Nothing -> execute `catch` refused
  where
    refused :: IOException -> IO (Either ProcessError Int)
    refused exception = pure (Left (SpawnFailed (Text.pack (show exception))))
    execute =
      Native.withCreateProcess
        ( (Native.proc path programArguments)
            { Native.cwd = Just programDirectory,
              Native.env = Just programEnvironment,
              Native.std_in = Native.Inherit,
              Native.std_out = Native.Inherit,
              Native.std_err = Native.Inherit,
              Native.close_fds = True,
              Native.use_process_jobs = True,
              Native.delegate_ctlc = True
            }
        )
        (\_ _ _ process -> Right . statusCode <$> Native.waitForProcess process)

foreign import ccall safe "agentctl_exec"
  nativeExec :: CString -> CString -> Ptr CString -> Ptr CString -> IO CInt

foreign import ccall unsafe "agentctl_request_reap"
  nativeRequestReap :: CLLong -> IO CInt

requestReap :: Multiplexer -> CommandContext -> IO (Either ProcessError ())
requestReap mux context
  | muxKind mux == Psmux = pure (Right ())
  | otherwise = do
      observed <- runCommand mux (Command.ListSessions "#{pid}") context
      case observed of
        Left failure -> pure (Left failure)
        Right output
          | exitCode output /= 0 -> pure (Left (ReadinessFailed (exitCode output) (stderrText output)))
          | otherwise -> case nub (Text.words (stdoutText output)) of
              [raw] | Text.all (\character -> isAscii character && isDigit character) raw ->
                case (readMaybe (Text.unpack raw) :: Maybe Integer) of
                  Just pid | pid > 0 && pid <= toInteger (maxBound :: CInt) -> do
                    code <- nativeRequestReap (fromInteger pid)
                    pure (if code == 0 then Right () else Left (ReapFailed (fromIntegral code)))
                  _ -> pure (Left InvalidServerIdentity)
              _ -> pure (Left InvalidServerIdentity)

replace :: Program -> IO ProcessError
replace program@(Program path programArguments programDirectory programEnvironment) = case validateProgram program of
  Just failure -> pure failure
  Nothing -> execute `catch` refused
  where
    refused :: IOException -> IO ProcessError
    refused exception = pure (SpawnFailed (Text.pack (show exception)))
    execute = do
      hFlush stdout
      hFlush stderr
      withUtf8 path $ \executablePointer ->
        withUtf8 programDirectory $ \programDirectoryPointer ->
          withMany withUtf8 (path : programArguments) $ \argumentPointers ->
            withMany withUtf8 [key ++ "=" ++ value | (key, value) <- programEnvironment] $ \programEnvironmentPointers ->
              withArray0 nullPtr argumentPointers $ \argv ->
                withArray0 nullPtr programEnvironmentPointers $
                  fmap (ExecFailed . fromIntegral) . nativeExec executablePointer programDirectoryPointer argv

withUtf8 :: String -> (CString -> IO value) -> IO value
withUtf8 value = Bytes.useAsCString (Text.encodeUtf8 (Text.pack value))
