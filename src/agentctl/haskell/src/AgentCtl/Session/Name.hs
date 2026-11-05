-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Session.Name
  ( SessionName,
    NameError (..),
    makeSessionName,
    sessionNameText,
    Names (..),
    deriveNames,
    Presence (..),
    Decision (..),
    decide,
    decisionText,
    ObservedSession (..),
    Selection (..),
    selectSession,
  )
where

import AgentCtl.Agent.Types (Agent, agentText)
import qualified Crypto.Hash.SHA256 as SHA256
import qualified Data.ByteString as Bytes
import Data.Char (isAlphaNum, isAscii)
import Data.List (find)
import Data.Text (Text)
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Text
import Data.Word (Word8)
import Numeric (showHex)
import qualified System.FilePath.Posix as Posix
import qualified System.FilePath.Windows as Windows

newtype SessionName = SessionName Text deriving (Eq, Ord, Show)

newtype NameError = InvalidSessionName Text deriving (Eq, Show)

makeSessionName :: Text -> Either NameError SessionName
makeSessionName name
  | Text.null name
      || "-" `Text.isPrefixOf` name
      || "__" `Text.isInfixOf` name
      || not (Text.all allowed name) =
      Left (InvalidSessionName name)
  | otherwise = Right (SessionName name)
  where
    allowed character = isAscii character && (isAlphaNum character || character `elem` ['_', '-'])

sessionNameText :: SessionName -> Text
sessionNameText (SessionName name) = name

data Names = Names
  { nameBase :: Text,
    plainName :: SessionName,
    hashedName :: SessionName
  }
  deriving (Eq, Show)

deriveNames :: Bool -> Text -> Agent -> Names
deriveNames windows canonical agent = Names base (SessionName plain) (SessionName hashed)
  where
    path = Text.unpack canonical
    basename = if windows then Windows.takeFileName (Windows.dropTrailingPathSeparator path) else Posix.takeFileName (Posix.dropTrailingPathSeparator path)
    base = sanitise (Text.pack basename)
    hashInput = identity windows canonical
    digest = Text.pack (concatMap byteHex (Bytes.unpack (Bytes.take 4 (SHA256.hash (Text.encodeUtf8 hashInput)))))
    plain = base <> "-" <> agentText agent
    hashed = base <> "-" <> digest <> "-" <> agentText agent

byteHex :: Word8 -> String
byteHex byte = case showHex byte "" of
  [digit] -> ['0', digit]
  digits -> digits

sanitise :: Text -> Text
sanitise = fallback . Text.dropWhile (== '-') . collapse '-' . collapse '_' . Text.map clean
  where
    clean character
      | isAscii character && (isAlphaNum character || character `elem` ['_', '-']) = character
      | otherwise = '-'
    fallback value = if Text.null value then "folder" else value

collapse :: Char -> Text -> Text
collapse separator = Text.concat . map shorten . Text.group
  where
    shorten group = if Text.all (== separator) group then Text.singleton separator else group

identity :: Bool -> Text -> Text
identity True = Text.toCaseFold
identity False = id

data Presence = Absent | Owned | Foreign deriving (Eq, Show)

data Decision = AttachPlain | AttachHashed | CreatePlain | CreateHashed | Refuse deriving (Eq, Show)

decide :: Presence -> Presence -> Decision
decide Owned _ = AttachPlain
decide Absent Owned = AttachHashed
decide Foreign Owned = AttachHashed
decide Absent Absent = CreatePlain
decide Absent Foreign = CreatePlain
decide Foreign Absent = CreateHashed
decide Foreign Foreign = Refuse

decisionText :: Decision -> Text
decisionText AttachPlain = "attach-plain"
decisionText AttachHashed = "attach-hashed"
decisionText CreatePlain = "create-plain"
decisionText CreateHashed = "create-hashed"
decisionText Refuse = "refuse"

data ObservedSession = ObservedSession
  { observedName :: SessionName,
    observedOwner :: Maybe Text,
    observedAgent :: Maybe Agent,
    observedFolder :: Maybe Text
  }
  deriving (Eq, Show)

data Selection = Selection Decision SessionName deriving (Eq, Show)

selectSession :: Bool -> Text -> Agent -> [ObservedSession] -> Selection
selectSession windows canonical agent sessions = Selection decision selected
  where
    names = deriveNames windows canonical agent
    lookupName wanted = find (\session -> identity windows (sessionNameText (observedName session)) == identity windows (sessionNameText wanted)) sessions
    plain = lookupName (plainName names)
    hashed = lookupName (hashedName names)
    presence Nothing = Absent
    presence (Just session)
      | observedOwner session == Just "agentctl"
          && observedAgent session == Just agent
          && fmap (identity windows) (observedFolder session) == Just (identity windows canonical) =
          Owned
      | otherwise = Foreign
    decision = decide (presence plain) (presence hashed)
    actual wanted = maybe wanted observedName (lookupName wanted)
    selected = case decision of
      AttachPlain -> actual (plainName names)
      AttachHashed -> actual (hashedName names)
      CreatePlain -> plainName names
      CreateHashed -> hashedName names
      Refuse -> actual (hashedName names)
