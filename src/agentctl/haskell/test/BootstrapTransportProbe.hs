-- Copyright (c) 2026 agentctl contributors.
module Main (main) where

import AgentCtl.Bootstrap.Protocol (Handshake (..), parseConsent, protocolVersion)
import Data.Aeson (encode, object, (.=))
import qualified Data.ByteString.Lazy.Char8 as Bytes
import System.Environment (getArgs, lookupEnv)

main :: IO ()
main = do
  arguments <- getArgs
  nonce <- lookupEnv "AGENTCTL_TRANSPORT_NONCE"
  consent <- lookupEnv "AGENTCTL_ASSUME_YES"
  Bytes.putStrLn $
    encode $
      object
        [ "handshake" .= Handshake protocolVersion [],
          "arguments" .= arguments,
          "consent" .= parseConsent consent,
          "nonce" .= nonce
        ]
