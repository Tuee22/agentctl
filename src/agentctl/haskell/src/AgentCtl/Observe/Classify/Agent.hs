-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Observe.Classify.Agent (classify) where

import AgentCtl.Agent (Agent (..))
import AgentCtl.Observe.Capture (Screen)
import AgentCtl.Observe.Classify (Classification)
import qualified AgentCtl.Observe.Classify.Claude as Claude
import qualified AgentCtl.Observe.Classify.Codex as Codex

classify :: Agent -> Screen -> Classification
classify Claude = Claude.classify
classify Codex = Codex.classify
