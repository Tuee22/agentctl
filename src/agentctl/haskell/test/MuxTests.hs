-- Copyright (c) 2026 agentctl contributors.
module MuxTests (tests) where

import qualified AgentCtl.Mux as Mux
import qualified Data.Text as Text
import System.Directory (canonicalizePath, copyFileWithMetadata, findExecutable, getCurrentDirectory)
import System.Environment (getEnvironment)
import System.FilePath (isAbsolute, (</>))
import System.IO.Temp (withSystemTempDirectory)
import Test.Tasty (TestTree, testGroup)
import Test.Tasty.HUnit (assertBool, assertFailure, (@?=))
import TestSource (testCase)

tests :: [TestTree]
tests =
  [ testGroup
      "MuxReal"
      [ testCase "absent-multiplexer-unavailable" absentMultiplexer,
        testCase "host-multiplexer-meets-floor" hostMultiplexer
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
