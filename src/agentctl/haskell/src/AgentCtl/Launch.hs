-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Launch
  ( Observation (..),
    Action (..),
    Plan (..),
    launchPlan,
    launchArguments,
    actionText,
    observation,
    Request (..),
    run,
    startupWindowMicros,
  )
where

import qualified AgentCtl.Agent as Agent
import qualified AgentCtl.Agent.Argv as Argv
import qualified AgentCtl.Mux as Mux
import qualified AgentCtl.Mux.Command as Command
import qualified AgentCtl.Native as Native
import qualified AgentCtl.PaneExec as PaneExec
import qualified AgentCtl.PaneExec.Spec as Spec
import qualified AgentCtl.Paths as Paths
import qualified AgentCtl.Preflight as Preflight
import qualified AgentCtl.Process as Process
import qualified AgentCtl.Session.Identity as Identity
import qualified AgentCtl.Session.Name as Name
import Control.Concurrent (threadDelay)
import Control.Exception (IOException, catch, onException)
import Control.Monad (forM, forM_, unless, when)
import Control.Monad.IO.Class (liftIO)
import Control.Monad.Trans.Except (ExceptT (..), runExceptT, throwE)
import qualified Data.ByteString as Bytes
import qualified Data.Map.Strict as Map
import Data.Maybe (isJust)
import Data.Text (Text)
import qualified Data.Text as Text
import qualified Data.Text.IO as Text
import GHC.Clock (getMonotonicTimeNSec)
import qualified System.Directory as Directory
import System.FilePath ((</>))
import System.IO (hClose, hSetBinaryMode, stderr)
import System.IO.Temp (createTempDirectory, withTempFile)
import Text.Read (readMaybe)

data Observation
  = Refused Int
  | PreflightFailed Int
  | Fresh
  | DeadLeftover
  | Reattach
  | Exited Int
  | Alive
  deriving (Eq, Show)

data Action
  = CheckPreflight
  | CreateSession
  | KillSession
  | CaptureOutput
  | ReportFailure
  | ReportExit
  | ReleasePane
  | NoticeIgnored
  | PrintAttach
  | AttachClient
  | SwitchClient
  deriving (Eq, Show)

data Plan = Plan
  { actions :: [Action],
    exitCode :: Int
  }
  deriving (Eq, Show)

launchPlan :: Observation -> Bool -> Bool -> Bool -> Plan
launchPlan observed hasArguments tty inside = case observed of
  Refused status -> failure status
  PreflightFailed status -> failure status
  Fresh -> Plan [CheckPreflight, CreateSession] 0
  DeadLeftover -> Plan [KillSession, CheckPreflight, CreateSession] 0
  Reattach -> Plan ([NoticeIgnored | hasArguments] ++ [handover tty inside]) 0
  Exited status -> Plan [CaptureOutput, KillSession, ReportExit] status
  Alive -> Plan [ReleasePane, handover tty inside] 0
  where
    failure status = Plan [ReportFailure] (max 1 status)

handover :: Bool -> Bool -> Action
handover False _ = PrintAttach
handover True False = AttachClient
handover True True = SwitchClient

actionText :: Action -> Text
actionText CheckPreflight = "preflight"
actionText CreateSession = "create"
actionText KillSession = "kill"
actionText CaptureOutput = "capture"
actionText ReportFailure = "warn-failure"
actionText ReportExit = "warn-exit"
actionText ReleasePane = "release"
actionText NoticeIgnored = "notice"
actionText PrintAttach = "print-attach"
actionText AttachClient = "attach"
actionText SwitchClient = "switch"

observation :: Text -> Int -> Maybe Observation
observation "refused" status = Just (Refused status)
observation "preflight-failed" status = Just (PreflightFailed status)
observation "fresh" _ = Just Fresh
observation "dead-leftover" _ = Just DeadLeftover
observation "reattach" _ = Just Reattach
observation "exited" status = Just (Exited status)
observation "alive" _ = Just Alive
observation _ _ = Nothing

data Request = Request
  { requestFamily :: Mux.Family,
    requestDistribution :: Text,
    requestAgent :: Agent.Agent,
    requestDirectory :: FilePath,
    requestArguments :: [String],
    requestEnvironment :: [(String, String)],
    requestPaths :: Paths.Paths,
    requestBinary :: FilePath,
    requestTerminal :: Bool
  }

data Failure
  = Rejected Int [Text]
  | StateFailure Text
  | CommandFailure Text
  | InvalidResponse Text
  | InvalidPlan
  deriving (Eq, Show)

type Effect = ExceptT Failure IO

data Runtime = Runtime
  { request :: Request,
    multiplexer :: Mux.Multiplexer,
    session :: Name.SessionName,
    canonicalFolder :: FilePath,
    agentPane :: Maybe Command.Pane,
    statusFile :: Maybe FilePath
  }

data Scope = Scope
  { scopeDirectory :: FilePath,
    scopeSpec :: FilePath,
    scopeStatus :: FilePath
  }

data Outcome = Outcome Int Bool

startupWindowMicros :: Int
startupWindowMicros = 2000000

queryMicros :: Int
queryMicros = 10000000

run :: Request -> IO Int
run supplied = do
  result <- runExceptT (launch supplied)
  case result of
    Right (Outcome code _) -> pure code
    Left (Rejected code linesOfWarning) -> mapM_ (Text.hPutStrLn stderr) linesOfWarning >> pure code
    Left failure -> Text.hPutStrLn stderr ("agentctl: launch failed: " <> failureText failure) >> pure 1

failureText :: Failure -> Text
failureText (Rejected _ linesOfWarning) = Text.intercalate "\n" linesOfWarning
failureText (StateFailure message) = message
failureText (CommandFailure message) = message
failureText (InvalidResponse message) = message
failureText InvalidPlan = "invalid launch action sequence"

io :: IO value -> Effect value
io action = ExceptT ((Right <$> action) `catch` refused)
  where
    refused :: IOException -> IO (Either Failure value)
    refused exception = pure (Left (StateFailure (Text.pack (show exception))))

reject :: Observation -> [Text] -> Effect value
reject observed linesOfWarning = throwE (Rejected (exitCode (launchPlan observed False False False)) linesOfWarning)

launch :: Request -> Effect Outcome
launch supplied
  | Argv.loginShaped (requestAgent supplied) (requestArguments supplied) =
      let (code, linesOfWarning) = Argv.refusalWarning (Argv.LoginRequested (requestAgent supplied))
       in reject (Refused code) linesOfWarning
  | otherwise = do
      canonical <- io (Directory.canonicalizePath (requestDirectory supplied))
      resolved <- io (Mux.resolve (requestFamily supplied) (requestDistribution supplied) canonical (requestEnvironment supplied))
      mux <- case resolved of
        Left failure -> preflightRefusal supplied (Preflight.MultiplexerFailure failure)
        Right found -> pure found
      let names = Name.deriveNames (requestFamily supplied == Mux.Windows) (Text.pack canonical) (requestAgent supplied)
          initial = Runtime supplied mux (Name.plainName names) canonical Nothing Nothing
      observed <- discoverSessions initial names
      let Name.Selection decision selected = Name.selectSession (requestFamily supplied == Mux.Windows) (Text.pack canonical) (requestAgent supplied) observed
          runtime = initial {session = selected}
      case decision of
        Name.Refuse -> throwE (Rejected 9 ["agentctl: another session holds " <> Name.sessionNameText selected <> "; no session was started."])
        Name.CreatePlain -> execute runtime Fresh
        Name.CreateHashed -> execute runtime Fresh
        Name.AttachPlain -> reuse runtime
        Name.AttachHashed -> reuse runtime

preflightRefusal :: Request -> Preflight.Failure -> Effect value
preflightRefusal supplied failure =
  let (code, linesOfWarning) = Preflight.warning (requestFamily supplied) (requestDistribution supplied) (requestAgent supplied) failure
   in reject (PreflightFailed code) linesOfWarning

commandContext :: Runtime -> Process.CommandContext
commandContext runtime = Process.CommandContext (canonicalFolder runtime) (requestEnvironment (request runtime)) queryMicros

rawCommand :: Runtime -> Command.Command -> Effect Process.Output
rawCommand runtime command = do
  result <- io (Process.runCommand (multiplexer runtime) command (commandContext runtime))
  either (throwE . CommandFailure . Text.pack . show) pure result

checkedCommand :: Runtime -> Command.Command -> Effect Process.Output
checkedCommand runtime command = do
  output <- rawCommand runtime command
  if Process.exitCode output == 0
    then pure output
    else throwE (CommandFailure ("multiplexer exited " <> Text.pack (show (Process.exitCode output)) <> ": " <> Process.stderrText output))

hasSession :: Runtime -> Name.SessionName -> Effect Bool
hasSession runtime name = do
  output <- rawCommand runtime (Command.HasSession name)
  case Process.exitCode output of
    0 -> pure True
    1 -> pure False
    _ -> throwE (CommandFailure (Process.stderrText output))

inspectSession :: Runtime -> Name.SessionName -> Effect [Name.ObservedSession]
inspectSession runtime name = do
  found <- hasSession runtime name
  if not found
    then pure []
    else do
      output <- checkedCommand runtime (Command.ShowOptions name)
      let options = Identity.options (Process.stdoutText output)
          folder = Map.lookup "@agentctl_folder" options >>= Identity.decodeText
      pure [Name.ObservedSession name (Map.lookup "@agentctl_owner" options) (Map.lookup "@agentctl_agent" options >>= Agent.agentFromText) folder]

discoverSessions :: Runtime -> Name.Names -> Effect [Name.ObservedSession]
discoverSessions runtime names = do
  output <- rawCommand runtime (Command.ListSessions "#{session_name}")
  case Process.exitCode output of
    1 -> pure []
    0 -> do
      let identity = if requestFamily (request runtime) == Mux.Windows then Text.toCaseFold else id
          wanted = map (identity . Name.sessionNameText) [Name.plainName names, Name.hashedName names]
          matching = [name | line <- Text.lines (Process.stdoutText output), identity line `elem` wanted, Right name <- [Name.makeSessionName line]]
      concat <$> mapM (inspectSession runtime) matching
    _ -> throwE (CommandFailure (Process.stderrText output))

reuse :: Runtime -> Effect Outcome
reuse runtime = do
  output <- checkedCommand runtime (Command.ListPanes (session runtime) "#{pane_id} #{pane_dead}")
  panes <- forM (Text.lines (Process.stdoutText output)) $ \line -> case Text.words line of
    [identifier, dead] | dead == "0" || dead == "1" -> do
      pane <- maybe (throwE (InvalidResponse "invalid session pane id")) pure (Command.makePane identifier)
      pure (Command.inSession (Mux.muxKind (multiplexer runtime)) (session runtime) pane, dead == "1")
    _ -> throwE (InvalidResponse "invalid session pane state")
  when (null panes) (throwE (InvalidResponse "session contains no panes"))
  case [pane | (pane, False) <- panes] of
    pane : _ -> execute (runtime {agentPane = Just pane}) Reattach
    [] -> execute runtime DeadLeftover

execute :: Runtime -> Observation -> Effect Outcome
execute runtime observed = go Nothing (actions plan)
  where
    supplied = request runtime
    inside = maybe False (not . null) (lookup "TMUX" (requestEnvironment supplied))
    plan = launchPlan observed (not (null (requestArguments supplied))) (requestTerminal supplied) inside
    go _ [] = pure (Outcome (exitCode plan) (isJust (statusFile runtime) && KillSession `notElem` actions plan))
    go ready (action : remaining) = case action of
      CheckPreflight -> do
        result <- io (Preflight.preflightWithMux (multiplexer runtime) (requestFamily supplied) (requestDistribution supplied) (requestAgent supplied) (canonicalFolder runtime) (requestEnvironment supplied))
        either (preflightRefusal supplied) (\verified -> go (Just verified) remaining) result
      CreateSession -> case (ready, remaining) of
        (Just verified, []) -> fresh runtime verified
        _ -> throwE InvalidPlan
      KillSession -> endSession runtime >> go ready remaining
      CaptureOutput -> do
        pane <- requirePane runtime
        output <- checkedCommand runtime (Command.Capture pane 100)
        relay runtime (Process.stdoutText output)
        go ready remaining
      ReportExit -> do
        io (Text.hPutStrLn stderr ("agentctl: " <> Agent.agentText (requestAgent supplied) <> " exited with status " <> Text.pack (show (exitCode plan)) <> " during startup; its session was closed."))
        go ready remaining
      ReleasePane -> do
        pane <- requirePane runtime
        _ <- checkedCommand runtime (Command.RemainOnExit (session runtime) pane False)
        go ready remaining
      NoticeIgnored -> do
        io (Text.hPutStrLn stderr ("agentctl: " <> Name.sessionNameText (session runtime) <> " is already running; the arguments given were not applied."))
        go ready remaining
      PrintAttach -> do
        let name = if Mux.muxKind (multiplexer runtime) == Mux.Psmux then "psmux" else "tmux"
        io (Text.putStrLn (name <> " attach-session -t =" <> Name.sessionNameText (session runtime)))
        go ready remaining
      AttachClient -> do
        status <- io (Process.foregroundCommand (multiplexer runtime) (Command.Attach (session runtime)) (commandContext runtime))
        code <- either (throwE . CommandFailure . Text.pack . show) pure status
        unless (code == 0) (throwE (CommandFailure "could not attach to the session"))
        go ready remaining
      SwitchClient -> checkedCommand runtime (Command.Switch (session runtime)) >> go ready remaining
      ReportFailure -> throwE InvalidPlan

requirePane :: Runtime -> Effect Command.Pane
requirePane runtime = maybe (throwE InvalidPlan) pure (agentPane runtime)

relay :: Runtime -> Text -> Effect ()
relay _ captured = io (Text.hPutStr stderr captured)

endSession :: Runtime -> Effect ()
endSession runtime = do
  output <- rawCommand runtime (Command.Kill (session runtime))
  unless (Process.exitCode output == 0) $ do
    present <- hasSession runtime (session runtime)
    when present (throwE (CommandFailure "could not close the failed launch"))

reserve :: Runtime -> Effect Scope
reserve runtime = do
  let paths = requestPaths (request runtime)
      directory = Paths.launchDirectory paths
      prefix = Text.unpack (Name.sessionNameText (session runtime)) ++ ".launch-"
  io (Directory.createDirectoryIfMissing True (Paths.stateDirectory paths))
  private <- io (Native.ensurePrivateDirectory directory)
  either (throwE . StateFailure . Text.pack . show) pure private
  tidyCompleted (requestFamily (request runtime) == Mux.Windows) directory prefix
  owned <- io (createTempDirectory directory prefix)
  pure (Scope owned (owned </> "spec.json") (owned </> "status.json"))

tidyCompleted :: Bool -> FilePath -> String -> Effect ()
tidyCompleted windows directory prefix = do
  entries <- io (Directory.listDirectory directory)
  forM_ [directory </> name | name <- entries, Text.pack prefix `Text.isPrefixOf` Text.pack name] $ \owned -> do
    let status = owned </> "status.json"
    result <- io (Native.snapshot status)
    case result of
      Right (access, _) | Spec.accepts access -> do
        files <- io (Directory.listDirectory owned)
        when (files == ["status.json"]) (io (Directory.removeFile status >> Directory.removeDirectory owned))
      _ -> unless windows $ do
        private <- io (Native.ensurePrivateDirectory owned)
        case private of
          Right () -> do
            files <- io (Directory.listDirectory owned)
            when (null files) (io (Directory.removeDirectory owned))
          Left _ -> pure ()

publish :: Runtime -> Preflight.Ready -> Scope -> Effect ()
publish runtime verified owned = do
  let supplied = request runtime
      arguments = launchArguments (requestFamily supplied) (requestAgent supplied) (Preflight.readyExecutable verified) (requestArguments supplied)
      spec = Spec.Spec arguments (canonicalFolder runtime) (Map.fromList (requestEnvironment supplied)) (scopeStatus owned)
  io $ withTempFile (scopeDirectory owned) "pending-" $ \temporary handle -> do
    hSetBinaryMode handle True
    Bytes.hPut handle (Spec.encodeSpec spec)
    hClose handle
    Directory.renameFile temporary (scopeSpec owned)

launchArguments :: Mux.Family -> Agent.Agent -> FilePath -> [String] -> [String]
launchArguments family agent = Argv.launchArgv (Agent.table family agent)

cleanScope :: Scope -> Bool -> Effect ()
cleanScope _ True = pure ()
cleanScope owned False = do
  removeOwned (scopeSpec owned)
  removeOwned (scopeStatus owned)
  io (Directory.removeDirectory (scopeDirectory owned))
  where
    removeOwned path = do
      exists <- io (Directory.doesFileExist path)
      when exists (io (Directory.removeFile path))

fresh :: Runtime -> Preflight.Ready -> Effect Outcome
fresh runtime verified = do
  owned <- reserve runtime
  created <- liftIO (runExceptT (checkedCommand runtime (Command.Create (session runtime) (requestBinary (request runtime)) (scopeSpec owned))))
  output <- case created of
    Left failure -> cleanScope owned False >> throwE failure
    Right value -> pure value
  let initialise = do
        nativePane <- maybe (throwE (InvalidResponse "create did not return one pane id")) pure (Command.makePane (Text.strip (Process.stdoutText output)))
        let pane = Command.inSession (Mux.muxKind (multiplexer runtime)) (session runtime) nativePane
        let running = runtime {agentPane = Just pane, statusFile = Just (scopeStatus owned)}
            identities = [(Command.Owner, "agentctl"), (Command.Agent, Agent.agentText (requestAgent (request runtime))), (Command.Folder, Identity.encodeText (Text.pack (canonicalFolder runtime))), (Command.AgentPane, Command.paneId pane), (Command.StatusFile, Identity.encodeText (Text.pack (scopeStatus owned)))]
        _ <- checkedCommand running (Command.RemainOnExit (session runtime) pane True)
        forM_ identities $ \(key, value) -> do
          valid <- maybe (throwE (InvalidResponse "invalid session identity value")) pure (Command.makeOptionValue value)
          _ <- checkedCommand running (Command.SetIdentity (session runtime) key valid)
          pure ()
        publish running verified owned
        observed <- observeStartup running
        execute running observed
      abort = runExceptT (endSession runtime >> cleanScope owned False)
  result <- liftIO (runExceptT initialise `onException` abort)
  case result of
    Left failure -> do
      _ <- ExceptT abort
      throwE failure
    Right outcome@(Outcome _ keep) -> do
      cleanScope owned keep
      pure outcome

observeStartup :: Runtime -> Effect Observation
observeStartup runtime = do
  began <- io getMonotonicTimeNSec
  poll (toInteger began + toInteger startupWindowMicros * 1000)
  where
    poll deadline = do
      (dead, status) <- paneState runtime
      if dead
        then case status of
          Just code -> pure (Exited code)
          Nothing -> do
            began <- io getMonotonicTimeNSec
            awaitStatus (toInteger began + toInteger queryMicros * 1000)
        else do
          now <- io getMonotonicTimeNSec
          if toInteger now >= deadline then pure Alive else io (threadDelay 10000) >> poll deadline
    awaitStatus deadline = do
      (_, status) <- paneState runtime
      case status of
        Just code -> pure (Exited code)
        Nothing -> do
          now <- io getMonotonicTimeNSec
          if toInteger now >= deadline
            then throwE (InvalidResponse "dead pane did not publish its exit status")
            else io (threadDelay 10000) >> awaitStatus deadline

paneState :: Runtime -> Effect (Bool, Maybe Int)
paneState runtime = do
  pane <- requirePane runtime
  output <- checkedCommand runtime (Command.PaneState pane)
  case Text.splitOn " " (Text.stripEnd (Process.stdoutText output)) of
    _pid : dead : remaining | dead == "0" || dead == "1" -> do
      let (status, terminated) = case remaining of
            value : cause : _ -> (number value, cause)
            [value] -> (number value, "")
            [] -> (Nothing, "")
      signal <- case number terminated of
        Just code -> pure (Just code)
        Nothing -> io (Native.signalNumber terminated)
      fileStatus <-
        if dead == "1" && Mux.muxKind (multiplexer runtime) == Mux.Psmux
          then case statusFile runtime of
            Nothing -> throwE InvalidPlan
            Just path -> do
              result <- io (PaneExec.readStatus path)
              case result of
                Right code -> pure (Just code)
                Left (PaneExec.NativeReadFailed (Native.SnapshotFailed code)) | code == 2 || code == 3 -> pure Nothing
                Left failure -> throwE (StateFailure (Text.pack (show failure)))
          else pure Nothing
      let actual = Command.deadStatus (Mux.muxKind (multiplexer runtime)) status signal fileStatus
      when (Command.needsReap (Mux.muxKind (multiplexer runtime)) (dead == "1") actual) $ do
        reaped <- io (Process.requestReap (multiplexer runtime) (commandContext runtime))
        either (throwE . CommandFailure . Text.pack . show) pure reaped
      pure (dead == "1", actual)
    _ -> throwE (InvalidResponse "invalid startup pane state")
  where
    number value = readMaybe (Text.unpack value)
