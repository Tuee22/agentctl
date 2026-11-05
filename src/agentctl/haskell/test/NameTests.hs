-- Copyright (c) 2026 agentctl contributors.
module NameTests (tests) where

import AgentCtl.Agent (Agent (..))
import AgentCtl.Session.Name (Names (..), deriveNames, makeSessionName, sessionNameText)
import Control.Monad (forM_, replicateM)
import Data.Either (isRight)
import qualified Data.Text as Text
import Test.Tasty (TestTree, testGroup)
import Test.Tasty.HUnit (assertBool, testCase)

tests :: [TestTree]
tests = [testGroup "Name" [testCase "always-valid" alwaysValid]]

alwaysValid :: IO ()
alwaysValid = do
  let components = concatMap (`replicateM` ("aZ0-_.:λ日#() " :: String)) [0 .. 4]
  forM_ [False, True] $ \windows ->
    forM_ [Claude, Codex] $ \agent ->
      forM_ components $ \component -> do
        let names = deriveNames windows ("/root/" <> Text.pack component) agent
        forM_ [plainName names, hashedName names] $ \name ->
          assertBool "derived name is invalid" (isRight (makeSessionName (sessionNameText name)))
