-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Sessions
  ( PaneReport (..),
    Report (..),
    Row (..),
    managedRows,
    statusRows,
    parseReport,
    Target (..),
    sessionTarget,
    stopCommand,
    AttachMode (..),
    AttachPlan (..),
    attachPlan,
    attachModeText,
    Operation (..),
    Request (..),
    Query,
    QueryError (..),
    openQuery,
    queryTargets,
    queryAdopted,
    queryMultiplexer,
    queryContext,
    run,
  )
where

import qualified AgentCtl.Adopt as Adopt
import qualified AgentCtl.Agent as Agent
import qualified AgentCtl.Mux as Mux
import qualified AgentCtl.Mux.Command as Command
import qualified AgentCtl.Mux.Psmux as Psmux
import qualified AgentCtl.Mux.Tmux as Tmux
import qualified AgentCtl.Native as Native
import qualified AgentCtl.Observe.Capture as Capture
import qualified AgentCtl.Observe.Classify as Classify
import qualified AgentCtl.Observe.Classify.Agent as ClassifyAgent
import qualified AgentCtl.PaneExec as PaneExec
import qualified AgentCtl.Paths as Paths
import qualified AgentCtl.Preflight as Preflight
import qualified AgentCtl.Process as Process
import qualified AgentCtl.Session.Identity as Identity
import qualified AgentCtl.Session.Name as Name
import qualified AgentCtl.Supervisor.Lock as Lock
import qualified AgentCtl.Supervisor.Watch as Watch
import Control.Concurrent (threadDelay)
import Control.Exception (IOException, catch)
import Control.Monad (forM, void, when)
import Control.Monad.Trans.Except (ExceptT (..), runExceptT, throwE)
import Data.Aeson (ToJSON (toJSON), Value, encode, object, withObject, (.:), (.:?), (.=))
import Data.Aeson.Types (Parser)
import qualified Data.ByteString.Lazy as Bytes
import Data.List (find)
import qualified Data.Map.Strict as Map
import Data.Maybe (fromMaybe, isJust, isNothing, mapMaybe)
import Data.Text (Text)
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Text
import qualified Data.Text.IO as Text
import GHC.Clock (getMonotonicTimeNSec)
import qualified System.Directory as Directory
import System.IO (stderr)
import Text.Read (readMaybe)

data PaneReport = PaneReport
  { paneId :: Command.Pane,
    panePid :: Integer,
    paneDead :: Bool,
    paneExit :: Maybe Int
  }
  deriving (Eq, Show)

data Report = Report
  { reportName :: Name.SessionName,
    reportOwner :: Maybe Text,
    reportAgent :: Maybe Agent.Agent,
    reportFolder :: Maybe Text,
    reportPane :: Maybe Command.Pane,
    reportAttached :: Int,
    reportPanes :: [PaneReport]
  }
  deriving (Eq, Show)

data Row = Row
  { rowName :: Name.SessionName,
    rowAgent :: Agent.Agent,
    rowFolder :: Text,
    rowPane :: Command.Pane,
    rowPid :: Integer,
    rowDead :: Bool,
    rowExit :: Maybe Int,
    rowAttached :: Int
  }
  deriving (Eq, Show)

instance ToJSON Row where
  toJSON row =
    object
      ( [ "name" .= Name.sessionNameText (rowName row),
          "agent" .= Agent.agentText (rowAgent row),
          "folder" .= rowFolder row,
          "pane" .= Command.paneText (rowPane row),
          "pid" .= rowPid row,
          "state" .= (if rowDead row then "dead" else "alive" :: Text),
          "attached" .= rowAttached row,
          "kind" .= ("managed" :: Text)
        ]
          ++ maybe [] (\code -> ["exit" .= code]) (rowExit row)
      )

managedRows :: [Report] -> [Row]
managedRows = mapMaybe managed
  where
    managed report
      | reportOwner report == Just "agentctl" = do
          agent <- reportAgent report
          folder <- reportFolder report
          identifier <- reportPane report
          pane <- find ((== identifier) . paneId) (reportPanes report)
          pure (Row (reportName report) agent folder identifier (panePid pane) (paneDead pane) (paneExit pane) (reportAttached report))
      | otherwise = Nothing

statusRows :: Bool -> Text -> [Row] -> [Row]
statusRows windows folder = filter (\row -> identity windows (rowFolder row) == identity windows folder)

identity :: Bool -> Text -> Text
identity True = Text.toCaseFold
identity False = id

parseReport :: Value -> Parser Report
parseReport = withObject "session report" $ \fields -> do
  name <- fields .: "name" >>= either (fail . show) pure . Name.makeSessionName
  owner <- fields .:? "owner"
  agent <- fmap (>>= Agent.agentFromText) (fields .:? "agent")
  folder <- fields .:? "folder"
  pane <- fields .:? "pane" >>= traverse checkedPane
  attached <- fields .: "attached"
  panes <- fields .: "panes" >>= mapM parsePane
  if attached < 0 then fail "negative attached-client count" else pure (Report name owner agent folder pane attached panes)
  where
    parsePane = withObject "pane report" $ \fields -> do
      pane <- fields .: "pane" >>= checkedPane
      pid <- fields .: "pid"
      dead <- fields .: "dead"
      status <- fields .:? "exit"
      if pid <= 0 || maybe False (< 0) status then fail "invalid pane process facts" else pure (PaneReport pane pid dead status)
    checkedPane = maybe (fail "invalid pane id") pure . Command.makePane

data Target = Managed Row | Adopted Adopt.View | Foreign Name.SessionName | Missing Text deriving (Eq, Show)

sessionTarget :: Bool -> Text -> [Report] -> Target
sessionTarget windows name reports = case find (\report -> identity windows (Name.sessionNameText (reportName report)) == identity windows name) reports of
  Nothing -> Missing name
  Just report -> case managedRows [report] of
    [row] -> Managed row
    _ -> Foreign (reportName report)

stopCommand :: Target -> Maybe Command.Command
stopCommand (Managed row) = Just (Command.Kill (rowName row))
stopCommand (Adopted _) = Nothing
stopCommand (Foreign _) = Nothing
stopCommand (Missing _) = Nothing

data AttachMode = PrintAttach | AttachClient | SwitchClient deriving (Eq, Show)

data AttachPlan = AttachPlan AttachMode Command.Command deriving (Eq, Show)

attachPlan :: Bool -> Bool -> Row -> AttachPlan
attachPlan terminal inside row = AttachPlan mode command
  where
    selected = rowName row
    mode
      | not terminal = PrintAttach
      | inside = SwitchClient
      | otherwise = AttachClient
    command = case mode of
      PrintAttach -> Command.Attach selected
      AttachClient -> Command.Attach selected
      SwitchClient -> Command.Switch selected

attachModeText :: AttachMode -> Text
attachModeText PrintAttach = "print"
attachModeText AttachClient = "attach"
attachModeText SwitchClient = "switch"

data Operation = List | Status (Maybe Text) | Attach Text | Stop Text | Adopt Command.Pane Agent.Agent | WatchTarget Watch.Operation Text deriving (Eq, Show)

data Request = Request
  { requestFamily :: Mux.Family,
    requestDistribution :: Text,
    requestDirectory :: FilePath,
    requestEnvironment :: [(String, String)],
    requestPaths :: Paths.Paths,
    requestTerminal :: Bool
  }

data Failure = StateFailure Text | CommandFailure Text | MuxFailure Mux.MuxError | ObservationFailure Capture.CaptureError | InvalidResponse Text | MissingTarget Text | RefusedStop Text | RefusedAdoption Text deriving (Eq, Show)

type Effect = ExceptT Failure IO

data Runtime = Runtime Request Mux.Multiplexer FilePath

newtype Query = Query Runtime

data QueryError = QueryMuxError Mux.MuxError | QueryFailure Text deriving (Eq, Show)

openQuery :: Request -> IO (Either QueryError Query)
openQuery supplied = queryEffect $ do
  canonical <- io (Directory.canonicalizePath (requestDirectory supplied))
  resolved <- io (Mux.resolve (requestFamily supplied) (requestDistribution supplied) canonical (requestEnvironment supplied))
  mux <- either (throwE . MuxFailure) pure resolved
  pure (Query (Runtime supplied mux canonical))

queryTargets :: Query -> IO (Either QueryError [Target])
queryTargets (Query runtime@(Runtime supplied _ _)) = queryEffect $ do
  reports <- readReports runtime IdentityOnly
  registry <- io (Adopt.load (requestPaths supplied)) >>= either (throwE . StateFailure . Text.pack . show) pure
  adopted <- forM registry $ \entry -> Adopted . Adopt.View entry <$> observePane runtime (Adopt.entryPane entry)
  pure (map Managed (managedRows reports) ++ adopted)

queryAdopted :: Query -> Adopt.Entry -> IO (Either QueryError (Maybe Adopt.Observation))
queryAdopted (Query runtime) entry = queryEffect $ do
  observed <- observePane runtime (Adopt.entryPane entry)
  pure (Adopt.viewCurrent (Adopt.View entry observed))

queryMultiplexer :: Query -> Mux.Multiplexer
queryMultiplexer (Query (Runtime _ mux _)) = mux

queryContext :: Query -> Process.CommandContext
queryContext (Query runtime) = context runtime

queryEffect :: Effect value -> IO (Either QueryError value)
queryEffect action = do
  result <- runExceptT action
  pure $ case result of
    Left (MuxFailure failure) -> Left (QueryMuxError failure)
    Left failure -> Left (QueryFailure (failureText failure))
    Right value -> Right value

run :: Request -> Operation -> IO Int
run supplied operation = do
  result <- runExceptT $ do
    canonical <- io (Directory.canonicalizePath (requestDirectory supplied))
    resolved <- io (Mux.resolve (requestFamily supplied) (requestDistribution supplied) canonical (requestEnvironment supplied))
    mux <- either (throwE . MuxFailure) pure resolved
    let runtime = Runtime supplied mux canonical
    registry <- withWatchLock runtime (loadRegistry runtime)
    reports <- case operation of
      List -> loadReports runtime
      Status _ -> loadReports runtime
      Attach _ -> readReports runtime IdentityOnly
      Stop _ -> readReports runtime IdentityOnly
      Adopt _ _ -> readReports runtime IdentityOnly
      WatchTarget _ _ -> readReports runtime IdentityOnly
    adopted <- forM registry $ \entry -> Adopt.View entry <$> observePane runtime (Adopt.entryPane entry)
    let rows = managedRows reports
        target name = case find ((== name) . Command.paneText . Adopt.entryPane . Adopt.viewEntry) adopted of
          Just view -> Adopted view
          Nothing -> sessionTarget (requestFamily supplied == Mux.Windows) name reports
        managed name = case target name of
          Managed row -> pure row
          Adopted _ -> throwE (MissingTarget name)
          Foreign _ -> throwE (MissingTarget name)
          Missing _ -> throwE (MissingTarget name)
    watched <- case operation of
      List -> withWatchLock runtime (loadWatch runtime)
      Status _ -> withWatchLock runtime (loadWatch runtime)
      WatchTarget _ _ -> pure Watch.empty
      Attach _ -> pure Watch.empty
      Stop _ -> pure Watch.empty
      Adopt _ _ -> pure Watch.empty
    case operation of
      List -> printRows watched rows adopted
      Status Nothing -> printStatus runtime watched (statusRows (requestFamily supplied == Mux.Windows) (Text.pack canonical) rows) []
      Status (Just name) -> case target name of
        Adopted view -> printStatus runtime watched [] [view]
        Managed row -> printStatus runtime watched [row] []
        Foreign _ -> throwE (MissingTarget name)
        Missing _ -> throwE (MissingTarget name)
      Attach name -> managed name >>= handover runtime
      Stop name -> case stopCommand (target name) of
        Nothing -> case target name of
          Adopted view -> withWatchLock runtime $ do
            currentRegistry <- loadRegistry runtime
            saveRegistry runtime (filter ((/= Adopt.entryPane (Adopt.viewEntry view)) . Adopt.entryPane) currentRegistry)
            io (Text.putStrLn ("agentctl: " <> name <> " is adopted, not owned. Registration removed; agentctl did not end the pane."))
          Managed _ -> throwE (RefusedStop name)
          Foreign _ -> throwE (RefusedStop name)
          Missing _ -> throwE (RefusedStop name)
        Just command -> void (checkedCommand runtime command)
      Adopt pane agent -> withWatchLock runtime $ do
        currentRegistry <- loadRegistry runtime
        current <- observePane runtime pane
        let selectedPane = maybe pane Adopt.observationPane current
            existing = any ((== selectedPane) . Adopt.entryPane) currentRegistry
        case Adopt.decision agent current existing of
          Adopt.Register entry -> saveRegistry runtime (currentRegistry ++ [entry])
          Adopt.RefuseMissing -> throwE (RefusedAdoption "the pane does not exist")
          Adopt.RefuseManaged -> throwE (RefusedAdoption "the pane belongs to a managed session")
          Adopt.RefuseDead -> throwE (RefusedAdoption "the pane is not alive")
          Adopt.RefuseExisting -> throwE (RefusedAdoption "the pane is already adopted")
      WatchTarget command name -> withWatchLock runtime $ do
        currentWatch <- loadWatch runtime
        let selected = target name
            kind = case selected of
              Managed _ -> Watch.ManagedTarget
              Adopted view -> if isNothing (Adopt.viewCurrent view) then Watch.MissingTarget else Watch.AdoptedTarget
              Foreign _ -> Watch.ForeignTarget
              Missing _ -> Watch.MissingTarget
            canonicalTarget = case selected of
              Managed row -> Name.sessionNameText (rowName row)
              Adopted view -> Command.paneText (Adopt.entryPane (Adopt.viewEntry view))
              Foreign _ -> registeredName currentWatch name
              Missing _ -> registeredName currentWatch name
            decision = Watch.transition command kind canonicalTarget currentWatch
        when (Watch.decisionRegistry decision /= currentWatch) $ do
          saved <- io (Watch.save (requestPaths supplied) (Watch.decisionRegistry decision))
          either (throwE . StateFailure . Text.pack . show) pure saved
        mapM_ (checkedCommand runtime) (Watch.decisionCommands decision)
        let message = watchMessage canonicalTarget (Watch.decisionNotice decision)
        if Watch.decisionExit decision == 0 then io (Text.putStrLn message) else throwE (StateFailure message)
  case result of
    Right () -> pure 0
    Left (MuxFailure failure) -> do
      let (code, messages) = Preflight.multiplexerWarning (requestFamily supplied) (requestDistribution supplied) failure
      mapM_ (Text.hPutStrLn stderr) messages
      pure code
    Left (MissingTarget name) -> Text.hPutStrLn stderr ("agentctl: " <> name <> " is not a session agentctl manages.") >> pure 1
    Left (RefusedStop name) -> Text.hPutStrLn stderr ("agentctl: " <> name <> " is not a session agentctl manages; nothing was stopped.") >> pure 1
    Left (RefusedAdoption message) -> Text.hPutStrLn stderr ("agentctl: " <> message <> "; nothing was adopted.") >> pure 1
    Left failure -> Text.hPutStrLn stderr ("agentctl: session command failed: " <> failureText failure) >> pure 1
  where
    registeredName registry wanted = fromMaybe wanted (find ((== identity windows wanted) . identity windows) (Map.keys (Watch.registryEntries registry)))
    windows = requestFamily supplied == Mux.Windows

watchMessage :: Text -> Watch.Notice -> Text
watchMessage target notice =
  "agentctl: " <> case notice of
    Watch.Watching -> "watching " <> target <> "."
    Watch.AlreadyWatched -> target <> " already has watch intent; use resume-watch to clear a pause."
    Watch.Unwatched -> "unwatched " <> target <> "; the session was left running."
    Watch.NotWatched -> target <> " is not watched."
    Watch.Paused -> "paused supervision of " <> target <> "."
    Watch.AlreadyPaused -> target <> " is already paused."
    Watch.Resumed -> "resumed supervision of " <> target <> "."
    Watch.RefuseTarget -> target <> " is not a current managed session or adopted pane; watch intent was unchanged."

loadWatch :: Runtime -> Effect Watch.Registry
loadWatch (Runtime supplied _ _) = do
  loaded <- io (Watch.load (requestPaths supplied))
  either (throwE . StateFailure . Text.pack . show) pure loaded

withWatchLock :: Runtime -> Effect value -> Effect value
withWatchLock (Runtime supplied _ _) action = do
  result <- io (Lock.withLock (requestPaths supplied) Lock.WatchRegistry (runExceptT action))
  either (throwE . StateFailure . Text.pack . show) (either throwE pure) result

failureText :: Failure -> Text
failureText (StateFailure message) = message
failureText (CommandFailure message) = message
failureText (MuxFailure failure) = Text.pack (show failure)
failureText (ObservationFailure failure) = Text.pack (show failure)
failureText (InvalidResponse message) = message
failureText (MissingTarget name) = name
failureText (RefusedStop name) = name
failureText (RefusedAdoption message) = message

printRows :: Watch.Registry -> [Row] -> [Adopt.View] -> Effect ()
printRows watched rows adopted = io $ do
  Text.putStrLn "NAME\tAGENT\tFOLDER\tSTATE\tEXIT\tCLIENTS\tPANE\tPID\tKIND\tSESSION\tCOMMAND\tWATCHED\tPAUSED"
  mapM_ (\row -> Text.putStrLn (renderRow row <> "\t" <> Watch.columns watched (Name.sessionNameText (rowName row)))) rows
  mapM_ (\view -> Text.putStrLn (renderAdopted view <> "\t" <> Watch.columns watched (Command.paneText (Adopt.entryPane (Adopt.viewEntry view))))) adopted

printStatus :: Runtime -> Watch.Registry -> [Row] -> [Adopt.View] -> Effect ()
printStatus runtime watched rows adopted = do
  managed <- forM rows $ \row -> do
    screen <- screenClass runtime (rowAgent row) (rowPane row)
    pure (renderRow row <> "\t" <> screen <> "\t" <> Watch.columns watched (Name.sessionNameText (rowName row)))
  registered <- forM adopted $ \view -> do
    let entry = Adopt.viewEntry view
    screen <- case Adopt.viewCurrent view of
      Nothing -> pure (Classify.classText Classify.Unknown)
      Just _ -> screenClass runtime (Adopt.entryAgent entry) (Adopt.entryPane entry)
    pure (renderAdopted view <> "\t" <> screen <> "\t" <> Watch.columns watched (Command.paneText (Adopt.entryPane entry)))
  io $ do
    Text.putStrLn "NAME\tAGENT\tFOLDER\tSTATE\tEXIT\tCLIENTS\tPANE\tPID\tKIND\tSESSION\tCOMMAND\tSCREEN\tWATCHED\tPAUSED"
    mapM_ Text.putStrLn (managed ++ registered)

screenClass :: Runtime -> Agent.Agent -> Command.Pane -> Effect Text
screenClass runtime@(Runtime _ mux _) agent pane = do
  observed <- io (Capture.capture mux pane (context runtime))
  screen <- either (throwE . ObservationFailure) pure observed
  let selectedScreen = screen
  pure (Classify.classText (Classify.classificationClass (ClassifyAgent.classify agent selectedScreen)))

saveRegistry :: Runtime -> [Adopt.Entry] -> Effect ()
saveRegistry (Runtime supplied _ _) entries = do
  result <- io (Adopt.save (requestPaths supplied) entries)
  either (throwE . StateFailure . Text.pack . show) pure result

loadRegistry :: Runtime -> Effect [Adopt.Entry]
loadRegistry (Runtime supplied _ _) = do
  loaded <- io (Adopt.load (requestPaths supplied))
  either (throwE . StateFailure . Text.pack . show) pure loaded

handover :: Runtime -> Row -> Effect ()
handover runtime@(Runtime supplied mux _) row = do
  let inside = maybe False (not . null) (lookup "TMUX" (requestEnvironment supplied))
      AttachPlan mode command = attachPlan (requestTerminal supplied) inside row
  case mode of
    PrintAttach -> do
      let rendered = if Mux.muxKind mux == Mux.Psmux then Psmux.render command else Tmux.render command
          executable = if Mux.muxKind mux == Mux.Psmux then "psmux" else "tmux"
      io (Text.putStrLn (Text.unwords (executable : map Text.pack (Command.arguments rendered))))
    AttachClient -> do
      result <- io (Process.foregroundCommand mux command (context runtime))
      code <- either (throwE . CommandFailure . Text.pack . show) pure result
      when (code /= 0) (throwE (CommandFailure "could not attach to the session"))
    SwitchClient -> void (checkedCommand runtime command)

renderRow :: Row -> Text
renderRow row = Text.intercalate "\t" [Name.sessionNameText (rowName row), Agent.agentText (rowAgent row), jsonString (rowFolder row), if rowDead row then "dead" else "alive", maybe "-" (Text.pack . show) (rowExit row), Text.pack (show (rowAttached row)), Command.paneText (rowPane row), Text.pack (show (rowPid row)), "managed", jsonString (Name.sessionNameText (rowName row)), jsonString ""]

renderAdopted :: Adopt.View -> Text
renderAdopted view = Text.intercalate "\t" [Command.paneText (Adopt.entryPane entry), Agent.agentText (Adopt.entryAgent entry), jsonString "", state, maybe "-" (Text.pack . show) (current >>= Adopt.observationExit), Text.pack (show (maybe 0 Adopt.observationAttached current)), Command.paneText (Adopt.entryPane entry), Text.pack (show (Adopt.entryPid entry)), "adopted", jsonString (maybe "" Adopt.observationSession current), jsonString (maybe "" Adopt.observationCommand current)]
  where
    entry = Adopt.viewEntry view
    current = Adopt.viewCurrent view
    state = case current of
      Nothing -> "stale"
      Just observed -> if Adopt.observationDead observed then "dead" else "alive"

jsonString :: Text -> Text
jsonString = Text.decodeUtf8 . Bytes.toStrict . encode

observePane :: Runtime -> Command.Pane -> Effect (Maybe Adopt.Observation)
observePane runtime wanted = do
  selected <- resolvePane runtime wanted
  maybe (pure Nothing) (observeResolvedPane runtime) selected

resolvePane :: Runtime -> Command.Pane -> Effect (Maybe Command.Pane)
resolvePane runtime@(Runtime _ mux _) wanted
  | Mux.muxKind mux /= Mux.Psmux || isJust (Command.paneSession wanted) = pure (Just wanted)
  | otherwise = do
      output <- rawCommand runtime (Command.ListSessions "#{session_name}")
      case Process.exitCode output of
        1 -> pure Nothing
        0 -> do
          matches <- fmap concat $ forM (Text.lines (Process.stdoutText output)) $ \rawName -> case Name.makeSessionName rawName of
            Left _ -> pure []
            Right name -> do
              panes <- checkedCommand runtime (Command.ListPanes name "#{pane_id}")
              pure [Command.inSession Mux.Psmux name wanted | Command.paneId wanted `elem` Text.lines (Process.stdoutText panes)]
          either (throwE . InvalidResponse) pure (Command.selectPane matches)
        _ -> throwE (CommandFailure (Process.stderrText output))

observeResolvedPane :: Runtime -> Command.Pane -> Effect (Maybe Adopt.Observation)
observeResolvedPane runtime@(Runtime _ mux _) wanted = do
  output <- rawCommand runtime (Command.InspectPane wanted "#{pane_id}\t#{pane_pid}\t#{pane_dead}\t#{?#{==:#{@agentctl_owner},agentctl},1,0}\t#{session_attached}\t#{pane_dead_status}\t#{pane_dead_signal}\t#{session_id}\t#{socket_path}")
  case Process.exitCode output of
    1 -> pure Nothing
    0 -> case Text.splitOn "\t" (trimLine (Process.stdoutText output)) of
      identifier : rawPid : dead : owned : rawAttached : rawStatus : rawSignal : session : namespaceParts
        | not (null namespaceParts) && dead `elem` ["0", "1"] && owned `elem` ["0", "1"] -> do
            pane <- maybe (throwE (InvalidResponse "invalid adopted pane id")) pure (Command.makePane identifier)
            when (Command.paneId pane /= Command.paneId wanted) (throwE (InvalidResponse "pane query returned another target"))
            pid <- case readMaybe (Text.unpack rawPid) of
              Just value | value > 0 -> pure value
              _ -> throwE (InvalidResponse "invalid adopted pane pid")
            attached <- nonnegative rawAttached
            let namespace = Text.intercalate "\t" namespaceParts
            when (Text.null namespace || Text.null session) (throwE (InvalidResponse "missing server endpoint identity"))
            signal <- case readMaybe (Text.unpack rawSignal) of
              Just code -> pure (Just code)
              Nothing -> io (Native.signalNumber rawSignal)
            sessionName <- trimLine . Process.stdoutText <$> checkedCommand runtime (Command.InspectPane wanted "#{session_name}")
            command <- trimLine . Process.stdoutText <$> checkedCommand runtime (Command.InspectPane wanted "#{pane_current_command}")
            let status = if dead == "1" then Command.deadStatus (Mux.muxKind mux) (readMaybe (Text.unpack rawStatus)) signal Nothing else Nothing
            pure (Just (Adopt.Observation (Adopt.endpointIdentity (Mux.muxKind mux) namespace session) wanted pid sessionName command (dead == "1") (owned == "1") attached status))
      _ -> throwE (InvalidResponse "invalid adopted pane observation")
    _ -> throwE (CommandFailure (Process.stderrText output))

trimLine :: Text -> Text
trimLine text = case Text.stripSuffix "\r\n" text of
  Just trimmed -> trimmed
  Nothing -> fromMaybe text (Text.stripSuffix "\n" text)

io :: IO value -> Effect value
io action = ExceptT ((Right <$> action) `catch` refused)
  where
    refused :: IOException -> IO (Either Failure value)
    refused exception = pure (Left (StateFailure (Text.pack (show exception))))

context :: Runtime -> Process.CommandContext
context (Runtime supplied _ directory) = Process.CommandContext directory (requestEnvironment supplied) 10000000

rawCommand :: Runtime -> Command.Command -> Effect Process.Output
rawCommand runtime@(Runtime _ mux _) command = do
  result <- io (Process.runCommand mux command (context runtime))
  either (throwE . CommandFailure . Text.pack . show) pure result

checkedCommand :: Runtime -> Command.Command -> Effect Process.Output
checkedCommand runtime command = do
  output <- rawCommand runtime command
  if Process.exitCode output == 0 then pure output else throwE (CommandFailure (Process.stderrText output))

loadReports :: Runtime -> Effect [Report]
loadReports runtime@(Runtime _ mux _) = do
  began <- io getMonotonicTimeNSec
  poll (toInteger began + 10000000000)
  where
    poll deadline = do
      reports <- readReports runtime WithStatus
      let rows = managedRows reports
      if any (\row -> rowDead row && isNothing (rowExit row)) rows
        then do
          now <- io getMonotonicTimeNSec
          when (toInteger now >= deadline) (throwE (InvalidResponse "dead pane did not publish its exit status"))
          reaped <- io (Process.requestReap mux (context runtime))
          either (throwE . CommandFailure . Text.pack . show) pure reaped
          io (threadDelay 10000)
          poll deadline
        else pure reports

data ReadMode = IdentityOnly | WithStatus deriving (Eq, Show)

readReports :: Runtime -> ReadMode -> Effect [Report]
readReports runtime@(Runtime _ mux _) mode = do
  output <- rawCommand runtime (Command.ListSessions "#{session_name}\t#{session_attached}")
  case Process.exitCode output of
    1 -> pure []
    0 -> fmap concat $ forM (Text.lines (Process.stdoutText output)) $ \line -> case Text.splitOn "\t" line of
      [rawName, rawAttached] -> case Name.makeSessionName rawName of
        Left _ -> pure []
        Right name -> do
          attached <- nonnegative rawAttached
          options <- Identity.options . Process.stdoutText <$> checkedCommand runtime (Command.ShowOptions name)
          let owner = Map.lookup "@agentctl_owner" options
              agent = Map.lookup "@agentctl_agent" options >>= Agent.agentFromText
              folder = Map.lookup "@agentctl_folder" options >>= Identity.decodeText
              pane = Command.inSession (Mux.muxKind mux) name <$> (Map.lookup "@agentctl_pane" options >>= Command.makePane)
              status = Map.lookup "@agentctl_status" options >>= Identity.decodeText
          panes <- checkedCommand runtime (Command.ListPanes name "#{pane_id}\t#{pane_pid}\t#{pane_dead}\t#{pane_dead_status}\t#{pane_dead_signal}") >>= mapM (readPane runtime name mode pane status) . Text.lines . Process.stdoutText
          pure [Report name owner agent folder pane attached panes]
      _ -> throwE (InvalidResponse "invalid session list")
    _ -> throwE (CommandFailure (Process.stderrText output))

nonnegative :: Text -> Effect Int
nonnegative value = case readMaybe (Text.unpack value) of
  Just number | number >= 0 -> pure number
  _ -> throwE (InvalidResponse "invalid nonnegative integer")

readPane :: Runtime -> Name.SessionName -> ReadMode -> Maybe Command.Pane -> Maybe Text -> Text -> Effect PaneReport
readPane (Runtime _ mux _) name mode agentPane statusPath line = case Text.splitOn "\t" line of
  [identifier, rawPid, dead, rawStatus, rawSignal] | dead == "0" || dead == "1" -> do
    nativePane <- maybe (throwE (InvalidResponse "invalid pane id")) pure (Command.makePane identifier)
    let pane = Command.inSession (Mux.muxKind mux) name nativePane
    pid <- case readMaybe (Text.unpack rawPid) of
      Just value | value > 0 -> pure value
      _ -> throwE (InvalidResponse "invalid pane pid")
    signal <- case readMaybe (Text.unpack rawSignal) of
      Just code -> pure (Just code)
      Nothing -> io (Native.signalNumber rawSignal)
    fileStatus <-
      if mode == WithStatus && dead == "1" && Mux.muxKind mux == Mux.Psmux && Just pane == agentPane
        then case statusPath of
          Nothing -> pure Nothing
          Just path -> do
            actual <- io (PaneExec.readStatus (Text.unpack path))
            case actual of
              Right code -> pure (Just code)
              Left (PaneExec.NativeReadFailed (Native.SnapshotFailed code)) | code == 2 || code == 3 -> pure Nothing
              Left failure -> throwE (StateFailure (Text.pack (show failure)))
        else pure Nothing
    pure (PaneReport pane pid (dead == "1") (Command.deadStatus (Mux.muxKind mux) (readMaybe (Text.unpack rawStatus)) signal fileStatus))
  _ -> throwE (InvalidResponse "invalid pane report")
