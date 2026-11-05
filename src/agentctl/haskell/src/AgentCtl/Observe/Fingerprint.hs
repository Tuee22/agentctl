-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Observe.Fingerprint
  ( ErrorBlock (..),
    Fingerprint,
    fingerprint,
    fingerprintText,
  )
where

import AgentCtl.Observe.Normalize (normalise)
import qualified Crypto.Hash.SHA256 as SHA256
import qualified Data.ByteString as Bytes
import Data.Text (Text)
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Text
import Data.Word (Word8)
import Numeric (showHex)

data ErrorBlock = ErrorBlock
  { precedingText :: Text,
    errorText :: Text,
    followingText :: Text
  }
  deriving (Eq, Show)

newtype Fingerprint = Fingerprint Text deriving (Eq, Ord, Show)

fingerprintText :: Fingerprint -> Text
fingerprintText (Fingerprint value) = value

fingerprint :: ErrorBlock -> Fingerprint
fingerprint block =
  Fingerprint (Text.pack (concatMap byteHex (Bytes.unpack digest)))
  where
    digest = SHA256.hash (Text.encodeUtf8 (normalise (errorText block)))

byteHex :: Word8 -> String
byteHex byte = case showHex byte "" of
  [digit] -> ['0', digit]
  digits -> digits
