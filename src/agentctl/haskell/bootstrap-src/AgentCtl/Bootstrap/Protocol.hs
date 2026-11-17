-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Bootstrap.Protocol
  ( Handshake (..),
    parseConsent,
    protocolVersion,
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
protocolVersion = 2

parseConsent :: Maybe String -> Maybe Bool
parseConsent (Just "true") = Just True
parseConsent (Just "false") = Just False
parseConsent _ = Nothing
