-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Supervisor.Guard (unchanged) where

import AgentCtl.Observe.Classify (ScreenClass (Overloaded))
import AgentCtl.Observe.Normalize (normalise)
import AgentCtl.Recovery.Machine (Observation (..))
import Data.Maybe (isJust)

unchanged :: (Eq key) => Observation key -> Observation key -> Bool
unchanged decision current =
  observationClass decision == Overloaded
    && observationClass current == observationClass decision
    && isJust (observationFingerprint decision)
    && observationFingerprint current == observationFingerprint decision
    && normalise (observationText decision) == normalise (observationText current)
