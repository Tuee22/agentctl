-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Observe.Classify.Claude (classify) where

import AgentCtl.Observe.Capture (Screen)
import AgentCtl.Observe.Classify (Classification, Rules (..), classifyWith)

classify :: Screen -> Classification
classify =
  classifyWith
    Rules
      { promptMarker = "❯",
        trustMarkers = ["do you trust the files in this folder", "trust this folder"],
        bypassMarkers = ["bypass permissions", "bypassing permissions"],
        approvalMarkers = ["do you want to proceed", "do you want to make this edit", "this command requires approval"],
        loginMarkers = ["select login method", "how would you like to sign in"],
        overloadMarkers = ["overloaded_error", "temporarily overloaded"],
        usageMarkers = ["rate_limit_error", "usage limit", "you've hit your limit"],
        authMarkers = ["authentication_error", "invalid api key", "authentication failed"],
        contextMarkers = ["prompt is too long", "context window exceeded", "context limit exceeded"]
      }
