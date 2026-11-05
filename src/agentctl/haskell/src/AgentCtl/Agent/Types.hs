-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Agent.Types (Agent (..), agentFromText, agentText) where

import Data.Text (Text)

data Agent = Claude | Codex deriving (Eq, Show)

agentFromText :: Text -> Maybe Agent
agentFromText "claude" = Just Claude
agentFromText "codex" = Just Codex
agentFromText _ = Nothing

agentText :: Agent -> Text
agentText Claude = "claude"
agentText Codex = "codex"
