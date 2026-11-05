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
import qualified RecoveryTests
import qualified SpecTests
import qualified SupervisorTests
import System.Environment (getArgs)
import Test.Tasty (defaultIngredients, defaultMainWithIngredients, testGroup)
import Test.Tasty.HUnit (assertEqual, testCase, (@?=))
import Test.Tasty.Runners.AntXML (antXMLRunner)

main :: IO ()
main = do
  arguments <- getArgs
  case arguments of
    "--process-fixture" : remaining -> MuxTests.fixture remaining
    ["--mux-fixture"] -> MuxFixture.run
    ["--agent-fixture"] -> AgentFixture.run
    "--console-fixture" : remaining -> ConsoleFixture.run remaining
    _ -> runTests

runTests :: IO ()
runTests =
  defaultMainWithIngredients (antXMLRunner : defaultIngredients) $
    testGroup
      "agentctl-core-test"
      ( testGroup
          "Handshake"
          [ testCase "protocol-fields" $
              assertEqual
                "handshake command list differs"
                ( Handshake
                    1
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
              validHandoff (Just "1") @?= True
          ]
          : MuxTests.tests
          ++ SpecTests.tests
          ++ AgentTests.tests
          ++ NameTests.tests
          ++ ObserveTests.tests
          ++ RecoveryTests.tests
          ++ SupervisorTests.tests
      )
