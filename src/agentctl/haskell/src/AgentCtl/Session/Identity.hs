-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Session.Identity (options, encodeText, decodeText) where

import qualified Data.ByteString.Base64.URL as Base64
import qualified Data.Map.Strict as Map
import Data.Text (Text)
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Text

options :: Text -> Map.Map Text Text
options raw = Map.fromList [(key, Text.dropAround (== '"') value) | line <- Text.lines raw, [key, value] <- [Text.words line]]

encodeText :: Text -> Text
encodeText = Text.decodeUtf8 . Base64.encodeUnpadded . Text.encodeUtf8

decodeText :: Text -> Maybe Text
decodeText encoded = do
  bytes <- either (const Nothing) Just (Base64.decodeUnpadded (Text.encodeUtf8 encoded))
  either (const Nothing) Just (Text.decodeUtf8' bytes)
