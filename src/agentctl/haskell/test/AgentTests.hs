-- Copyright (c) 2026 agentctl contributors.
module AgentTests (tests) where

import AgentCtl.Agent (Agent (..), Entry (..), table)
import AgentCtl.Agent.Argv (launchArgv)
import AgentCtl.Mux (Family (..))
import Control.Monad (forM_, replicateM)
import Data.List (isSuffixOf)
import qualified Data.Text as Text
import Test.Tasty (TestTree, testGroup)
import Test.Tasty.HUnit (assertBool, assertEqual, assertFailure, testCase)

tests :: [TestTree]
tests =
  [ testGroup "Argv" [testCase "user-order-and-single-flags" orderAndFlags],
    testGroup "Agent" [testCase "recovery-text-is-plain" plainRecovery]
  ]

orderAndFlags :: IO ()
orderAndFlags = forM_ [Claude, Codex] $ \agent -> do
  let entry = table Linux agent
      flags = mandatoryFlags entry
      removable = flags ++ removableAliases entry
      alphabet = ["", "λ\n日", "x;", "--", "--model", "opus"] ++ removable
      cases = concatMap (`replicateM` alphabet) [0 .. 4]
  forM_ cases $ \arguments -> case launchArgv entry "/tools/agent" arguments of
    executable : actual -> do
      assertEqual "argv lost executable" "/tools/agent" executable
      let (before, after) = break (== "--") actual
          (userBefore, userAfter) = break (== "--") arguments
      assertEqual "positional arguments changed" userAfter after
      assertEqual "user argument order changed" (filter (`notElem` removable) userBefore) (filter (`notElem` removable) before)
      assertBool "mandatory flags are not last" (flags `isSuffixOf` before)
      forM_ flags $ \flag -> assertEqual "mandatory flag repeated or missing" 1 (length (filter (== flag) before))
      forM_ (removableAliases entry) $ \alias -> assertBool "removable alias survived" (alias `notElem` before)
    [] -> assertFailure "argv has no executable"

plainRecovery :: IO ()
plainRecovery = forM_ [Claude, Codex] $ \agent -> do
  let text = recoveryText (table Linux agent)
  assertBool "recovery text is empty" (not (Text.null text))
  assertBool "recovery text is a slash command" (not ("/" `Text.isPrefixOf` text))
  assertBool "recovery text spans lines" (not (Text.any (`elem` ("\r\n" :: String)) text))
  forM_ [Claude, Codex] $ \other ->
    assertBool "recovery text contains login remedy" (not (loginRemedy (table Linux other) `Text.isInfixOf` text))
