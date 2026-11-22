-- Copyright (c) 2026 agentctl contributors.
module Main (main) where

import AgentCtl.Protocol (Handshake (..), handshake, validHandoff)
import qualified AgentFixture
import qualified AgentTests
import qualified ConsoleFixture
import qualified MuxFixture
import qualified MuxTests
import qualified NameTests
import qualified ObserveTests
import qualified ProcessTests
import qualified RecoveryTests
import qualified SpecTests
import qualified SupervisorTests
import System.Environment (getArgs)
import Test.Tasty (TestTree, defaultIngredients, defaultMainWithIngredients, testGroup)
import Test.Tasty.HUnit (assertEqual, (@?=))
import Test.Tasty.Runners.AntXML (antXMLRunner)
import TestSource (testCase)
import qualified TestSource

main :: IO ()
main = do
  arguments <- getArgs
  case arguments of
    "--process-fixture" : remaining -> ProcessTests.fixture remaining
    ["--mux-fixture"] -> MuxFixture.run
    ["--agent-fixture"] -> AgentFixture.run
    ["--agentctl-test-sources"] -> mapM_ putStrLn (TestSource.caseSources suite)
    "--console-fixture" : remaining -> ConsoleFixture.run remaining
    _ -> runTests

runTests :: IO ()
runTests = defaultMainWithIngredients (antXMLRunner : defaultIngredients) suite

suite :: TestTree
suite =
  testGroup
    "agentctl-core-test"
    ( handshakeTests
        : MuxTests.tests
        ++ ProcessTests.tests
        ++ SpecTests.tests
        ++ AgentTests.tests
        ++ NameTests.tests
        ++ ObserveTests.tests
        ++ RecoveryTests.tests
        ++ SupervisorTests.tests
    )

handshakeTests :: TestTree
handshakeTests =
  testGroup
    "Handshake"
    [ testCase "protocol-fields" $
        assertEqual
          "handshake command list differs"
          ( Handshake
              2
              [ "claude",
                "codex",
                "list",
                "status",
                "attach",
                "stop",
                "adopt",
                "watch",
                "unwatch",
                "pause",
                "resume-watch",
                "logs",
                "supervisor"
              ]
          )
          handshake,
      testCase "handoff-required" $ do
        validHandoff Nothing @?= False
        validHandoff (Just "0") @?= False
        validHandoff (Just "1") @?= False
        validHandoff (Just "2") @?= True
    ]
