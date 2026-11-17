-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Protocol
  ( Handshake (..),
    commandList,
    handshake,
    protocolVersion,
    validHandoff,
  )
where

import AgentCtl.Bootstrap.Protocol (Handshake (..), protocolVersion)

commandList :: [String]
commandList =
  [ "claude",
    "codex",
    "list",
    "status",
    "attach",
    "stop",
    "adopt",
    "watch",
    "unwatch",
    "pause",
    "resume-watch",
    "logs",
    "supervisor"
  ]

handshake :: Handshake
handshake = Handshake protocolVersion commandList

validHandoff :: Maybe String -> Bool
validHandoff supplied = supplied == Just (show protocolVersion)
