-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Agent.Argv (ArgvError (..), launchArgv, checkedArgv, loginShaped, refusalWarning) where

import AgentCtl.Agent (Agent (..), Entry (..), table)
import AgentCtl.Mux (Family (Linux))
import Data.Char (isSpace)
import Data.List (isInfixOf, stripPrefix)
import qualified Data.Text as Text

launchArgv :: Entry -> FilePath -> [String] -> [String]
launchArgv entry executable arguments =
  executable : retained ++ mandatoryFlags entry ++ positional
  where
    (options, positional) = break (== "--") arguments
    removable = mandatoryFlags entry ++ removableAliases entry
    retained = filter (`notElem` removable) options

newtype ArgvError = LoginRequested Agent deriving (Eq, Show)

checkedArgv :: Agent -> Entry -> FilePath -> [String] -> Either ArgvError [String]
checkedArgv agent entry executable arguments
  | loginShaped agent arguments = Left (LoginRequested agent)
  | otherwise = Right (launchArgv entry executable arguments)

loginShaped :: Agent -> [String] -> Bool
loginShaped agent arguments = case agent of
  Claude -> "setup-token" `elem` options || ["auth", "login"] `isInfixOf` options || any slashLogin arguments
  Codex -> "login" `elem` options
  where
    options = takeWhile (/= "--") arguments
    slashLogin token = case stripPrefix "/login" token of
      Just [] -> True
      Just (next : _) -> isSpace next
      Nothing -> False

refusalWarning :: ArgvError -> (Int, [Text.Text])
refusalWarning (LoginRequested agent) =
  (2, ["agentctl: login commands must be run yourself: " <> loginRemedy (table Linux agent)])
