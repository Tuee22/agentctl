-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Supervisor.Watch
  ( Operation (..),
    parseOperation,
    TargetKind (..),
    parseKind,
    Entry (..),
    Registry (..),
    empty,
    Notice (..),
    noticeText,
    Decision (..),
    transition,
    RegistryError (..),
    registryPath,
    load,
    save,
    columns,
  )
where

import qualified AgentCtl.Mux.Command as Command
import qualified AgentCtl.Mux.Tmux as Tmux
import qualified AgentCtl.Native as Native
import qualified AgentCtl.PaneExec.Spec as Spec
import qualified AgentCtl.Paths as Paths
import qualified AgentCtl.Session.Name as Name
import qualified AgentCtl.Supervisor.Commands as Commands
import Control.Exception (IOException, catch)
import Control.Monad (unless)
import Data.Aeson (FromJSON (parseJSON), ToJSON (toJSON), eitherDecodeStrict', encode, object, withObject, (.:), (.=))
import qualified Data.Aeson.KeyMap as Keys
import qualified Data.ByteString as Bytes
import qualified Data.ByteString.Lazy as Lazy
import Data.Either (isRight)
import Data.List (sort)
import Data.Map.Strict (Map)
import qualified Data.Map.Strict as Map
import Data.Maybe (isJust)
import Data.Text (Text)
import qualified Data.Text as Text
import qualified System.Directory as Directory
import System.FilePath (takeDirectory, (</>))
import System.IO (hClose, hSetBinaryMode)
import System.IO.Temp (withTempFile)

data Operation = Watch | Unwatch | Pause | ResumeWatch deriving (Eq, Show)

parseOperation :: Text -> Maybe Operation
parseOperation "watch" = Just Watch
parseOperation "unwatch" = Just Unwatch
parseOperation "pause" = Just Pause
parseOperation "resume-watch" = Just ResumeWatch
parseOperation _ = Nothing

data TargetKind = ManagedTarget | AdoptedTarget | ForeignTarget | MissingTarget deriving (Eq, Show)

parseKind :: Text -> Maybe TargetKind
parseKind "managed" = Just ManagedTarget
parseKind "adopted" = Just AdoptedTarget
parseKind "foreign" = Just ForeignTarget
parseKind "missing" = Just MissingTarget
parseKind _ = Nothing

data Entry = Entry {entryPaused :: Bool, entryRevision :: Integer} deriving (Eq, Show)

instance FromJSON Entry where
  parseJSON = withObject "watch entry" $ \fields -> do
    unless (sort (Keys.keys fields) == ["paused", "revision"]) (fail "invalid watch entry fields")
    paused <- fields .: "paused"
    revision <- fields .: "revision"
    if revision <= 0 then fail "invalid watch entry revision" else pure (Entry paused revision)

instance ToJSON Entry where
  toJSON entry = object ["paused" .= entryPaused entry, "revision" .= entryRevision entry]

data Registry = Registry {registryRevision :: Integer, registryEntries :: Map Text Entry} deriving (Eq, Show)

empty :: Registry
empty = Registry 0 Map.empty

instance FromJSON Registry where
  parseJSON = withObject "watch registry" $ \fields -> do
    unless (sort (Keys.keys fields) == ["revision", "watched"]) (fail "invalid watch registry fields")
    revision <- fields .: "revision"
    entries <- fields .: "watched"
    unless (revision >= 0 && all ((<= revision) . entryRevision) (Map.elems entries)) (fail "invalid watch registry revision")
    unless (all validTarget (Map.keys entries)) (fail "invalid watch target")
    pure (Registry revision entries)
    where
      validTarget value = isJust (Command.makePane value) || isRight (Name.makeSessionName value)

instance ToJSON Registry where
  toJSON registry = object ["revision" .= registryRevision registry, "watched" .= registryEntries registry]

data Notice = Watching | AlreadyWatched | Unwatched | NotWatched | Paused | AlreadyPaused | Resumed | RefuseTarget deriving (Eq, Show)

noticeText :: Notice -> Text
noticeText notice = case notice of
  Watching -> "watching"
  AlreadyWatched -> "already-watched"
  Unwatched -> "unwatched"
  NotWatched -> "not-watched"
  Paused -> "paused"
  AlreadyPaused -> "already-paused"
  Resumed -> "resumed"
  RefuseTarget -> "refuse-target"

data Decision = Decision
  { decisionRegistry :: Registry,
    decisionCommands :: [Command.Command],
    decisionExit :: Int,
    decisionNotice :: Notice
  }
  deriving (Eq, Show)

instance ToJSON Decision where
  toJSON decision = object ["registry" .= decisionRegistry decision, "commands" .= map (Command.arguments . Tmux.render) (decisionCommands decision), "exit" .= decisionExit decision, "message" .= noticeText (decisionNotice decision)]

transition :: Operation -> TargetKind -> Text -> Registry -> Decision
transition operation kind target registry
  | operation `elem` [Watch, ResumeWatch] && kind `notElem` [ManagedTarget, AdoptedTarget] = unchanged 1 RefuseTarget
  | otherwise = case operation of
      Watch -> case current of
        Nothing -> update False Watching
        Just _ -> unchanged 0 AlreadyWatched
      Unwatch -> case current of
        Nothing -> unchanged 0 NotWatched
        Just _ -> (changed (Map.delete target entries) Unwatched) {decisionCommands = Commands.plan Commands.Unwatch}
      Pause -> case current of
        Nothing -> unchanged 1 NotWatched
        Just entry -> if entryPaused entry then unchanged 0 AlreadyPaused else update True Paused
      ResumeWatch -> case current of
        Nothing -> unchanged 1 NotWatched
        Just entry -> if entryPaused entry then update False Resumed else unchanged 0 AlreadyWatched
  where
    entries = registryEntries registry
    current = Map.lookup target entries
    revision = registryRevision registry + 1
    unchanged = Decision registry []
    changed next = Decision (Registry revision next) [] 0
    update paused = changed (Map.insert target (Entry paused revision) entries)

columns :: Registry -> Text -> Text
columns registry target = case Map.lookup target (registryEntries registry) of
  Nothing -> "no\tno"
  Just entry -> "yes\t" <> if entryPaused entry then "yes" else "no"

data RegistryError = NativeFailure Native.NativeError | UnsafeRegistry | InvalidRegistry Text | RegistryIO Text deriving (Eq, Show)

registryPath :: Paths.Paths -> FilePath
registryPath paths = Paths.stateDirectory paths </> "watch.json"

load :: Paths.Paths -> IO (Either RegistryError Registry)
load paths = do
  observed <- Native.snapshot (registryPath paths)
  pure $ case observed of
    Left (Native.SnapshotFailed code) | code == 2 || code == 3 -> Right empty
    Left failure -> Left (NativeFailure failure)
    Right (access, bytes)
      | not (Spec.accepts access) -> Left UnsafeRegistry
      | otherwise -> case eitherDecodeStrict' bytes of
          Left failure -> Left (InvalidRegistry (Text.pack failure))
          Right registry -> Right registry

save :: Paths.Paths -> Registry -> IO (Either RegistryError ())
save paths registry = execute `catch` refused
  where
    directory = Paths.stateDirectory paths
    execute = do
      Directory.createDirectoryIfMissing True (takeDirectory directory)
      prepared <- Native.prepareStateDirectory directory
      case prepared of
        Left failure -> pure (Left (NativeFailure failure))
        Right () -> do
          withTempFile directory "watch-" $ \temporary handle -> do
            hSetBinaryMode handle True
            Bytes.hPut handle (Lazy.toStrict (encode registry))
            hClose handle
            Directory.renameFile temporary (registryPath paths)
          pure (Right ())
    refused :: IOException -> IO (Either RegistryError ())
    refused exception = pure (Left (RegistryIO (Text.pack (show exception))))
