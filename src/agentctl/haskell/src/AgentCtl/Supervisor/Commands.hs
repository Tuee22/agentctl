-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Supervisor.Commands (Intent (..), parseIntent, plan) where

import qualified AgentCtl.Agent as Agent
import qualified AgentCtl.Mux as Mux
import qualified AgentCtl.Mux.Command as Command
import Data.Text (Text)

data Intent = Send Mux.Family Agent.Agent Command.Pane | Wait | Notify | Unwatch | Shutdown | Escalate | Exited deriving (Eq, Show)

parseIntent :: Mux.Family -> Agent.Agent -> Command.Pane -> Text -> Maybe Intent
parseIntent family agent pane text = case text of
  "send" -> Just (Send family agent pane)
  "wait" -> Just Wait
  "notify" -> Just Notify
  "unwatch" -> Just Unwatch
  "shutdown" -> Just Shutdown
  "escalate" -> Just Escalate
  "exited" -> Just Exited
  _ -> Nothing

plan :: Intent -> [Command.Command]
plan intent = case intent of
  Send family agent pane -> [Command.SendLiteral pane (Agent.recoveryText (Agent.table family agent)), Command.SendEnter pane]
  Wait -> []
  Notify -> []
  Unwatch -> []
  Shutdown -> []
  Escalate -> []
  Exited -> []
