-- Copyright (c) 2026 agentctl contributors.
module MuxTests (tests, fixture) where

import qualified AgentCtl.Mux as Mux
import qualified AgentCtl.Process as Process
import Control.Concurrent (threadDelay)
import Control.Monad (forM_)
import qualified Data.ByteString as Bytes
import Data.Maybe (fromMaybe)
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Encoding
import qualified Data.Text.IO as Text
import GHC.Clock (getMonotonicTimeNSec)
import System.Directory (canonicalizePath, copyFileWithMetadata, doesFileExist, findExecutable, getCurrentDirectory)
import System.Environment (getEnvironment, getExecutablePath, lookupEnv)
import System.Exit (ExitCode (ExitFailure), die, exitSuccess, exitWith)
import System.FilePath (isAbsolute, (</>))
import System.IO (hClose, hSetBinaryMode, hSetEncoding, hSetNewlineMode, noNewlineTranslation, stderr, stdin, stdout, utf8)
import System.IO.Temp (withSystemTempDirectory)
import System.Timeout (timeout)
import Test.Tasty (TestTree, testGroup)
import Test.Tasty.HUnit (assertBool, assertFailure, testCase, (@?=))

tests :: [TestTree]
tests =
  [ testGroup
      "MuxReal"
      [ testCase "absent-multiplexer-unavailable" absentMultiplexer,
        testCase "host-multiplexer-meets-floor" hostMultiplexer
      ],
    testGroup
      "ProcessReal"
      [ testCase "utf8-argv-environment-and-status" unicodeProcess,
        testCase "line-endings-preserved" rawProcess,
        testCase "closed-parent-input" closedInputProcess,
        testCase "missing-and-relative-executables" missingProcess,
        testCase "invalid-utf8-is-refused" invalidUtf8,
        testCase "status-only-ignores-bytes" statusOnly,
        testCase "timeout-cleans-up" (timedProcess "sleep"),
        testCase "timeout-after-streams-close" (timedProcess "closed-sleep"),
        testCase "foreground-exit-status" foregroundProcess
      ]
  ]

nativeFamily :: IO Mux.Family
nativeFamily = case Mux.hostFamily of
  Just family -> pure family
  Nothing -> assertFailure "unsupported native mux host" >> pure Mux.Linux

absentMultiplexer :: IO ()
absentMultiplexer = withSystemTempDirectory "agentctl-mux-" $ \directory -> do
  family <- nativeFamily
  environment <- getEnvironment
  let isolated = ("PATH", directory) : filter (\(key, _) -> Text.toUpper (Text.pack key) /= "PATH") environment
      name = if family == Mux.Windows then "psmux.exe" else "tmux"
  absent <- Mux.resolve family "ubuntu" directory isolated
  absent @?= Left (Mux.Unavailable (if family == Mux.Windows then Mux.Psmux else Mux.Tmux) (Mux.remedy family "ubuntu"))
  original <- findExecutable name
  case original of
    Nothing -> assertFailure "native host multiplexer is unavailable"
    Just path -> do
      copyFileWithMetadata path (directory </> name)
      found <- Mux.resolve family "ubuntu" directory isolated
      case found of
        Left failure -> assertFailure (show failure)
        Right mux -> do
          expected <- canonicalizePath (directory </> name)
          Mux.muxExecutable mux @?= expected
          assertBool "resolved path is not absolute" (isAbsolute (Mux.muxExecutable mux))

hostMultiplexer :: IO ()
hostMultiplexer = do
  family <- nativeFamily
  environment <- getEnvironment
  directory <- getCurrentDirectory
  result <- Mux.resolve family "ubuntu" directory environment
  case result of
    Left failure -> assertFailure (show failure)
    Right mux -> do
      assertBool "host multiplexer path is not absolute" (isAbsolute (Mux.muxExecutable mux))
      case Mux.checkVersion (Mux.muxKind mux) (Mux.muxVersion mux) of
        Left failure -> assertFailure (show failure)
        Right _ -> pure ()

invocation :: FilePath -> [String] -> IO Process.Invocation
invocation directory arguments = do
  path <- getExecutablePath
  environment <- getEnvironment
  pure (Process.Invocation path ("--process-fixture" : arguments) directory environment 5000000)

unicodeProcess :: IO ()
unicodeProcess = withSystemTempDirectory "agentctl-process-" $ \directory -> do
  let forwarded = ["x;", "$(id)", "", "one\ntwo"] :: [String]
  request <- invocation directory ("text" : forwarded)
  cwd <- canonicalizePath directory
  let token = "λ日"
      environment = ("AGENTCTL_PROCESS_TOKEN", token) : filter ((/= "AGENTCTL_PROCESS_TOKEN") . fst) (Process.environment request)
  result <- Process.run request {Process.environment = environment}
  result @?= Right (Process.Output 3 (Text.pack (token ++ "\n" ++ cwd ++ "\n" ++ show forwarded ++ "\n")) "é\n")

rawProcess :: IO ()
rawProcess = withSystemTempDirectory "agentctl-raw-" $ \directory -> do
  request <- invocation directory ["raw"]
  result <- Process.run request
  result @?= Right (Process.Output 0 "A\r\nB\n" "E\r\n")

closedInputProcess :: IO ()
closedInputProcess = withSystemTempDirectory "agentctl-closed-input-" $ \directory -> do
  request <- invocation directory ["closed-input"]
  result <- Process.run request
  result @?= Right (Process.Output 0 "A\r\nB\n" "E\r\n")

missingProcess :: IO ()
missingProcess = withSystemTempDirectory "agentctl-missing-" $ \directory -> do
  request <- invocation directory ["text"]
  relative <- Process.run request {Process.executable = "relative"}
  relative @?= Left (Process.RelativeExecutable "relative")
  deadline <- Process.run request {Process.deadlineMicros = 0}
  deadline @?= Left Process.InvalidDeadline
  absent <- Process.run request {Process.executable = directory </> "absent"}
  case absent of
    Left (Process.SpawnFailed _) -> pure ()
    _ -> assertFailure (show absent)

invalidUtf8 :: IO ()
invalidUtf8 = withSystemTempDirectory "agentctl-invalid-" $ \directory -> do
  request <- invocation directory ["invalid"]
  result <- Process.run request
  case result of
    Left (Process.InvalidUtf8 _) -> pure ()
    _ -> assertFailure (show result)

statusOnly :: IO ()
statusOnly = withSystemTempDirectory "agentctl-status-only-" $ \directory -> do
  forM_ [0, 1, 2] $ \status -> do
    request <- invocation directory ["invalid-status", show (status :: Int)]
    result <- Process.runStatus request
    result @?= Right status
  request <- invocation directory ["sleep", directory </> "started"]
  timed <- Process.runStatus request {Process.deadlineMicros = 1000000}
  timed @?= Left Process.TimedOut
  missing <- Process.runStatus request {Process.executable = directory </> "missing"}
  case missing of
    Left (Process.SpawnFailed _) -> pure ()
    _ -> assertFailure (show missing)

timedProcess :: String -> IO ()
timedProcess mode = withSystemTempDirectory "agentctl-timeout-" $ \directory -> do
  let marker = directory </> "started"
  request <- invocation directory [mode, marker]
  began <- getMonotonicTimeNSec
  result <- timeout 5000000 (Process.run request {Process.deadlineMicros = 1000000})
  ended <- getMonotonicTimeNSec
  assertBool "process wait blocked the deadline" (ended - began < 8000000000)
  result @?= Just (Left Process.TimedOut)
  started <- doesFileExist marker
  assertBool "timeout fixture never started" started

foregroundProcess :: IO ()
foregroundProcess = withSystemTempDirectory "agentctl-foreground-" $ \directory ->
  forM_ [(0, "exit-zero"), (3, "exit-three")] $ \(status, mode) -> do
    let marker = directory </> mode
    request <- invocation directory [mode, marker]
    result <- timeout 5000000 (Process.foreground (Process.Program (Process.executable request) (Process.arguments request) directory (Process.environment request)))
    result @?= Just (Right status)
    started <- readFile marker
    started @?= "started"

fixture :: [String] -> IO ()
fixture ("text" : arguments) = do
  hSetEncoding stdout utf8
  hSetEncoding stderr utf8
  hSetNewlineMode stdout noNewlineTranslation
  hSetNewlineMode stderr noNewlineTranslation
  token <- lookupEnv "AGENTCTL_PROCESS_TOKEN"
  directory <- getCurrentDirectory
  Text.putStrLn (Text.pack (fromMaybe "" token))
  Text.putStrLn (Text.pack directory)
  Text.putStrLn (Text.pack (show arguments))
  Text.hPutStrLn stderr "é"
  exitWith (ExitFailure 3)
fixture ["raw"] = do
  hSetBinaryMode stdout True
  hSetBinaryMode stderr True
  Bytes.hPut stdout (Bytes.pack [65, 13, 10, 66, 10])
  Bytes.hPut stderr (Bytes.pack [69, 13, 10])
fixture ["closed-input"] = do
  hClose stdin
  directory <- getCurrentDirectory
  request <- invocation directory ["raw"]
  result <- Process.run request
  case result of
    Left failure -> die (show failure)
    Right output -> do
      hSetBinaryMode stdout True
      hSetBinaryMode stderr True
      Bytes.hPut stdout (Encoding.encodeUtf8 (Process.stdoutText output))
      Bytes.hPut stderr (Encoding.encodeUtf8 (Process.stderrText output))
      if Process.exitCode output == 0 then exitSuccess else exitWith (ExitFailure (Process.exitCode output))
fixture ["invalid-status", status] = do
  hSetBinaryMode stdout True
  hSetBinaryMode stderr True
  Bytes.hPut stdout (Bytes.pack [255])
  Bytes.hPut stderr (Bytes.pack [254])
  case status of
    "0" -> exitSuccess
    "1" -> exitWith (ExitFailure 1)
    "2" -> exitWith (ExitFailure 2)
    _ -> die "invalid status fixture"
fixture ["invalid"] = hSetBinaryMode stdout True >> Bytes.hPut stdout (Bytes.pack [255])
fixture ["sleep", marker] = writeFile marker "started" >> threadDelay 10000000
fixture ["closed-sleep", marker] = do
  writeFile marker "started"
  hClose stdout
  hClose stderr
  threadDelay 10000000
fixture ["exit-zero", marker] = writeFile marker "started" >> exitSuccess
fixture ["exit-three", marker] = writeFile marker "started" >> exitWith (ExitFailure 3)
fixture _ = exitWith (ExitFailure 2)
