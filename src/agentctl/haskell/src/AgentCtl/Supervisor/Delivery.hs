-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Supervisor.Delivery (Completion (..), complete) where

import qualified AgentCtl.Recovery.Machine as Machine
import qualified AgentCtl.Supervisor.Log as Log
import qualified AgentCtl.Supervisor.Poll as Poll
import Data.Maybe (isJust)
import qualified Data.Set as Set

data Completion key = Completion
  { completionMemory :: Poll.Memory key,
    completionDecision :: Maybe (Poll.Decision key)
  }
  deriving (Eq, Show)

complete :: (Ord key) => Log.Delivery -> Poll.Memory key -> Poll.Decision key -> Maybe (Poll.Decision key) -> Completion key
complete outcome previous proposed observed = case outcome of
  Log.Sent -> Completion (Poll.decisionMemory proposed) Nothing
  Log.Aborted -> case observed of
    Just fresh ->
      let next = if Machine.SendRecovery `elem` Poll.decisionActions fresh then previous else Poll.decisionMemory fresh
       in Completion next (Just fresh)
    Nothing -> finish identityChanged
  Log.Failed -> finish failed
  where
    state = Poll.memoryMachine previous
    incident = Machine.stateIncident state
    handled = maybe (Machine.stateHandled state) (\open -> Set.insert (Machine.incidentFingerprint open) (Machine.stateHandled state)) incident
    cleared mode revision = Poll.Memory revision (state {Machine.stateMode = mode, Machine.stateIncident = Nothing, Machine.stateHandled = handled})
    notice level message = [Poll.Notification level message [Poll.Stderr, Poll.DecisionLog]]
    identityChanged =
      Poll.Decision
        (cleared Machine.Monitoring 0)
        False
        False
        "identity-changed"
        []
        (if isJust incident then Machine.Ended else Machine.NoIncident)
        (notice Poll.Warning "target identity changed before recovery")
        [Poll.Ended | isJust incident]
    failed =
      Poll.Decision
        (cleared Machine.Escalate (Poll.memoryRevision previous))
        False
        False
        "send-failed"
        []
        Machine.Escalated
        (notice Poll.Error "recovery send failed")
        [Poll.Unresolved | isJust incident]
    finish decision = Completion (Poll.decisionMemory decision) (Just decision)
