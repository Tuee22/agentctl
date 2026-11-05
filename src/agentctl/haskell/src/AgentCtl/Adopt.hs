-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Adopt
  ( Entry (..),
    Observation (..),
    View (..),
    Decision (..),
    decision,
    revalidate,
    viewCurrent,
    viewSessionName,
    endpointIdentity,
    registryPath,
    RegistryError (..),
    load,
    save,
  )
where

import qualified AgentCtl.Agent as Agent
import AgentCtl.Mux (Kind (..))
import qualified AgentCtl.Mux.Command as Command
import qualified AgentCtl.Native as Native
import qualified AgentCtl.PaneExec.Spec as Spec
import qualified AgentCtl.Paths as Paths
import Control.Exception (IOException, catch)
import Control.Monad (unless)
import Data.Aeson (FromJSON (parseJSON), ToJSON (toJSON), eitherDecodeStrict', encode, object, withObject, (.:), (.:?), (.=))
import qualified Data.Aeson.KeyMap as Keys
import Data.Aeson.Types (Parser)
import qualified Data.ByteString as Bytes
import qualified Data.ByteString.Lazy as Lazy
import Data.List (nub, sort)
import Data.Text (Text)
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Text
import qualified System.Directory as Directory
import System.FilePath (takeDirectory, (</>))
import System.IO (hClose, hSetBinaryMode)
import System.IO.Temp (withTempFile)

data Entry = Entry
  { entrySocket :: Text,
    entryPane :: Command.Pane,
    entryPid :: Integer,
    entryAgent :: Agent.Agent
  }
  deriving (Eq, Show)

instance ToJSON Entry where
  toJSON entry = object ["socket" .= entrySocket entry, "pane" .= Command.paneText (entryPane entry), "pid" .= entryPid entry, "agent" .= Agent.agentText (entryAgent entry)]

instance FromJSON Entry where
  parseJSON = withObject "adopted pane" $ \fields -> do
    unless (sort (Keys.keys fields) == ["agent", "pane", "pid", "socket"]) (fail "invalid adopted entry fields")
    socket <- fields .: "socket" >>= checkedEndpoint
    pane <- fields .: "pane" >>= checkedPane
    pid <- fields .: "pid" >>= checkedPid
    agent <- fields .: "agent" >>= maybe (fail "invalid adopted agent") pure . Agent.agentFromText
    pure (Entry socket pane pid agent)

data Observation = Observation
  { observationSocket :: Text,
    observationPane :: Command.Pane,
    observationPid :: Integer,
    observationSession :: Text,
    observationCommand :: Text,
    observationDead :: Bool,
    observationOwned :: Bool,
    observationAttached :: Int,
    observationExit :: Maybe Int
  }
  deriving (Eq, Show)

instance FromJSON Observation where
  parseJSON = withObject "observed pane" $ \fields -> do
    socket <- fields .: "socket" >>= checkedEndpoint
    pane <- fields .: "pane" >>= checkedPane
    pid <- fields .: "pid" >>= checkedPid
    session <- fields .: "session"
    command <- fields .: "command"
    dead <- fields .: "dead"
    owned <- fields .: "owned"
    attached <- fields .: "attached"
    status <- fields .:? "exit"
    if attached < 0 || maybe False (< 0) status
      then fail "invalid pane state"
      else pure (Observation socket pane pid session command dead owned attached status)

checkedEndpoint :: Text -> Parser Text
checkedEndpoint value
  | Text.null value || Text.any (== '\0') value = fail "invalid server endpoint"
  | otherwise = pure value

checkedPane :: Text -> Parser Command.Pane
checkedPane = maybe (fail "invalid adopted pane id") pure . Command.makePane

checkedPid :: Integer -> Parser Integer
checkedPid value = if value > 0 then pure value else fail "invalid adopted pid"

data View = View
  { viewEntry :: Entry,
    viewObservation :: Maybe Observation
  }
  deriving (Eq, Show)

data Decision = Register Entry | RefuseMissing | RefuseManaged | RefuseDead | RefuseExisting deriving (Eq, Show)

instance ToJSON Decision where
  toJSON (Register entry) = object ["decision" .= ("register" :: Text), "entry" .= entry]
  toJSON RefuseMissing = object ["decision" .= ("refuse-missing" :: Text)]
  toJSON RefuseManaged = object ["decision" .= ("refuse-managed" :: Text)]
  toJSON RefuseDead = object ["decision" .= ("refuse-dead" :: Text)]
  toJSON RefuseExisting = object ["decision" .= ("refuse-existing" :: Text)]

decision :: Agent.Agent -> Maybe Observation -> Bool -> Decision
decision _ Nothing _ = RefuseMissing
decision agent (Just observed) existing
  | observationOwned observed = RefuseManaged
  | observationDead observed = RefuseDead
  | existing = RefuseExisting
  | otherwise = Register (Entry (observationSocket observed) (observationPane observed) (observationPid observed) agent)

revalidate :: Entry -> Maybe Observation -> Bool
revalidate _ Nothing = False
revalidate entry (Just observed) =
  entrySocket entry == observationSocket observed
    && entryPane entry == observationPane observed
    && entryPid entry == observationPid observed

viewSessionName :: View -> Maybe Text
viewSessionName = fmap observationSession . viewCurrent

viewCurrent :: View -> Maybe Observation
viewCurrent (View entry current) = if revalidate entry current then current else Nothing

endpointIdentity :: Kind -> Text -> Text -> Text
endpointIdentity Tmux namespace _ = namespace
endpointIdentity Psmux namespace session = Text.decodeUtf8 (Lazy.toStrict (encode (["psmux", namespace, session] :: [Text])))

newtype Registry = Registry [Entry]

instance FromJSON Registry where
  parseJSON = withObject "adopted registry" $ \fields -> do
    unless (Keys.keys fields == ["panes"]) (fail "invalid adopted registry fields")
    entries <- fields .: "panes"
    let panes = map entryPane entries
    if length (nub panes) /= length panes then fail "duplicate adopted pane id" else pure (Registry entries)

instance ToJSON Registry where
  toJSON (Registry entries) = object ["panes" .= entries]

data RegistryError = NativeFailure Native.NativeError | UnsafeRegistry | InvalidRegistry Text | RegistryIO Text deriving (Eq, Show)

registryPath :: Paths.Paths -> FilePath
registryPath paths = Paths.stateDirectory paths </> "adopted.json"

load :: Paths.Paths -> IO (Either RegistryError [Entry])
load paths = do
  observed <- Native.snapshot (registryPath paths)
  pure $ case observed of
    Left (Native.SnapshotFailed code) | code == 2 || code == 3 -> Right []
    Left failure -> Left (NativeFailure failure)
    Right (access, bytes)
      | not (Spec.accepts access) -> Left UnsafeRegistry
      | otherwise -> case eitherDecodeStrict' bytes of
          Left failure -> Left (InvalidRegistry (Text.pack failure))
          Right (Registry entries) -> Right entries

save :: Paths.Paths -> [Entry] -> IO (Either RegistryError ())
save paths entries = execute `catch` refused
  where
    directory = Paths.stateDirectory paths
    execute = do
      Directory.createDirectoryIfMissing True (takeDirectory directory)
      prepared <- Native.prepareStateDirectory directory
      case prepared of
        Left failure -> pure (Left (NativeFailure failure))
        Right () -> do
          withTempFile directory "adopted-" $ \temporary handle -> do
            hSetBinaryMode handle True
            Bytes.hPut handle (Lazy.toStrict (encode (Registry entries)))
            hClose handle
            Directory.renameFile temporary (registryPath paths)
          pure (Right ())
    refused :: IOException -> IO (Either RegistryError ())
    refused exception = pure (Left (RegistryIO (Text.pack (show exception))))
