-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Observe.Classify.Codex (classify) where

import AgentCtl.Observe.Capture (Screen)
import AgentCtl.Observe.Classify (Classification, Rules (..), classifyWith)

classify :: Screen -> Classification
classify =
  classifyWith
    Rules
      { promptMarker = "›",
        trustMarkers = ["do you trust the contents of this directory", "trust this directory"],
        bypassMarkers = ["bypass approvals warning", "bypassing approvals and sandbox"],
        approvalMarkers = ["would you like to run the following command", "would you like to make the following edits"],
        loginMarkers = ["sign in with chatgpt", "sign in with an api key"],
        overloadMarkers = ["server is overloaded", "server_is_overloaded", "temporarily at capacity"],
        usageMarkers = ["usagelimitexceeded", "usage limit", "insufficient_quota", "rate limit"],
        authMarkers = ["unauthorized", "authentication failed", "token expired"],
        contextMarkers = ["contextwindowexceeded", "context window exceeded", "context limit exceeded"]
      }
