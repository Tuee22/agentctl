-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Protocol
  ( Handshake (..),
    commandList,
    handshake,
    protocolVersion,
    validHandoff,
  )
where

import Data.Aeson (ToJSON (toJSON), object, (.=))

data Handshake = Handshake
  { handshakeProtocol :: Int,
    handshakeCommands :: [String]
  }
  deriving (Eq, Show)

instance ToJSON Handshake where
  toJSON (Handshake version commands) =
    object ["protocol" .= version, "commands" .= commands]

protocolVersion :: Int
protocolVersion = 1

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
