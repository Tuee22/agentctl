-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.PaneExec.Spec
  ( Spec (..),
    Access (..),
    decodeSpec,
    encodeSpec,
    accepts,
    paneEnvironment,
  )
where

import Data.Aeson (FromJSON (parseJSON), ToJSON (toJSON), eitherDecodeStrict', encode, object, withObject, (.:), (.=))
import Data.Bits (complement, (.&.))
import qualified Data.ByteString as Bytes
import qualified Data.ByteString.Lazy as Lazy
import qualified Data.Map.Strict as Map

data Spec = Spec
  { argv :: [String],
    cwd :: FilePath,
    environment :: Map.Map String String,
    statusPath :: FilePath
  }
  deriving (Eq)

instance FromJSON Spec where
  parseJSON = withObject "pane spec" $ \fields ->
    Spec <$> fields .: "argv" <*> fields .: "cwd" <*> fields .: "env" <*> fields .: "status"

instance ToJSON Spec where
  toJSON spec =
    object
      [ "argv" .= argv spec,
        "cwd" .= cwd spec,
        "env" .= environment spec,
        "status" .= statusPath spec
      ]

decodeSpec :: Bytes.ByteString -> Either String Spec
decodeSpec = eitherDecodeStrict'

encodeSpec :: Spec -> Bytes.ByteString
encodeSpec = Lazy.toStrict . encode

data Access = Access
  { fileKind :: Bool,
    fileOwned :: Bool,
    fileMode :: Int,
    directoryKind :: Bool,
    directoryOwned :: Bool,
    directoryMode :: Int
  }
  deriving (Eq, Show)

instance FromJSON Access where
  parseJSON = withObject "spec access" $ \fields ->
    Access
      <$> fields .: "fileKind"
      <*> fields .: "fileOwned"
      <*> fields .: "fileMode"
      <*> fields .: "directoryKind"
      <*> fields .: "directoryOwned"
      <*> fields .: "directoryMode"

accepts :: Access -> Bool
accepts access =
  fileKind access
    && fileOwned access
    && directoryKind access
    && directoryOwned access
    && fileMode access >= 0
    && directoryMode access >= 0
    && fileMode access .&. complement 0o600 == 0
    && directoryMode access .&. complement 0o700 == 0

paneEnvironment :: Map.Map String String -> Map.Map String String -> Map.Map String String
paneEnvironment supplied pane =
  Map.union
    (Map.filterWithKey (\key _ -> key `elem` ["TERM", "TMUX", "TMUX_PANE"]) pane)
    (foldr Map.delete supplied ["TERM", "TMUX", "TMUX_PANE"])
