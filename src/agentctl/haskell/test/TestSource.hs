-- Copyright (c) 2026 agentctl contributors.
module TestSource (testCase, caseSources) where

import GHC.Stack (HasCallStack, callStack, getCallStack, srcLocFile)
import Test.Tasty (TestTree, localOption)
import qualified Test.Tasty.HUnit as HUnit
import Test.Tasty.Options (IsOption (..), lookupOption)
import Test.Tasty.Runners (TreeFold (..), foldTestTree, trivialFold)

newtype SourcePath = SourcePath FilePath
  deriving (Eq, Show)

instance IsOption SourcePath where
  defaultValue = SourcePath ""
  parseValue = Just . SourcePath
  optionName = pure "agentctl-source-path"
  optionHelp = pure "Source of a native test case"

testCase :: (HasCallStack) => String -> HUnit.Assertion -> TestTree
testCase name action =
  localOption (SourcePath source) (HUnit.testCase name action)
  where
    source = case getCallStack callStack of
      (_, location) : _ -> srcLocFile location
      [] -> ""

caseSources :: TestTree -> [String]
caseSources tree =
  [name ++ "\t" ++ path | (name, path) <- foldTestTree sourceFold mempty tree]
  where
    sourceFold =
      trivialFold
        { foldSingle = \options name _ ->
            let SourcePath path = lookupOption options
             in [(name, path)],
          foldGroup = \_ group children ->
            [(group ++ "." ++ name, path) | (name, path) <- concat children]
        }
