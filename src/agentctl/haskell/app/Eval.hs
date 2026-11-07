-- Copyright (c) 2026 agentctl contributors.
module Main (main) where

import qualified AgentCtl.Adopt as Adopt
import qualified AgentCtl.Agent as Agent
import qualified AgentCtl.Agent.Argv as Argv
import qualified AgentCtl.Agent.Auth as Auth
import qualified AgentCtl.Launch as Launch
import qualified AgentCtl.Mux as Mux
import qualified AgentCtl.Mux.Command as Command
import qualified AgentCtl.Mux.Psmux as Psmux
import qualified AgentCtl.Mux.Tmux as Tmux
import qualified AgentCtl.Observe.Capture as Capture
import qualified AgentCtl.Observe.Classify as Classify
import qualified AgentCtl.Observe.Classify.Claude as Claude
import qualified AgentCtl.Observe.Classify.Codex as Codex
import qualified AgentCtl.Observe.Fingerprint as Fingerprint
import qualified AgentCtl.Observe.Normalize as Normalize
import qualified AgentCtl.PaneExec.Spec as Spec
import qualified AgentCtl.Preflight as Preflight
import qualified AgentCtl.Process as Process
import AgentCtl.Protocol (handshake, validHandoff)
import qualified AgentCtl.Recovery.Backoff as Backoff
import qualified AgentCtl.Recovery.Machine as Machine
import AgentCtl.Session.Name (makeSessionName)
import qualified AgentCtl.Session.Name as Name
import qualified AgentCtl.Sessions as Sessions
import qualified AgentCtl.Supervisor.Commands as SupervisorCommands
import qualified AgentCtl.Supervisor.Delivery as Delivery
import qualified AgentCtl.Supervisor.Guard as Guard
import qualified AgentCtl.Supervisor.Log as Log
import qualified AgentCtl.Supervisor.Poll as Poll
import qualified AgentCtl.Supervisor.Settings as SupervisorSettings
import qualified AgentCtl.Supervisor.Watch as Watch
import Data.Aeson (FromJSON (parseJSON), Object, Value, eitherDecode, encode, object, toJSON, withObject, (.!=), (.:), (.:?), (.=))
import qualified Data.Aeson.KeyMap as Keys
import Data.Aeson.Types (Parser, parseEither)
import qualified Data.ByteString.Lazy.Char8 as Bytes
import Data.Either (isRight)
import Data.Maybe (fromMaybe, isJust)
import qualified Data.Text as Text

evaluate :: Value -> Parser Value
evaluate = withObject "case" $ \fields -> do
  subject <- fields .: "subject"
  case (subject :: Text.Text) of
    "delivery-completion" -> deliveryValue fields
    "record-function" -> recordValue fields
    "log-selection" -> toJSON <$> (Log.select <$> fields .: "target" <*> fields .: "records")
    "log-decoding" -> do
      writer <- fields .: "writer_active"
      input <- fields .: "text"
      pure $ case Log.decode writer input of
        Left failure -> object ["records" .= ([] :: [Log.Record]), "error" .= failure]
        Right records -> object ["records" .= records, "error" .= ("" :: Text.Text)]
    "run-flag-defaults" -> do
      arguments <- fields .: "args"
      pure (either (const (object ["error" .= ("invalid-timing" :: Text.Text)])) toJSON (SupervisorSettings.parseArguments arguments))
    "poll-step" -> pollValue fields
    "command-plan" -> do
      family <- fields .: "family" >>= parseFamily
      agent <- fields .: "agent" >>= parseAgent
      pane <- fields .: "pane" >>= maybe (fail "invalid pane id") pure . Command.makePane
      intent <- fields .: "action" >>= maybe (fail "unknown supervisor command intent") pure . SupervisorCommands.parseIntent family agent pane
      let commands = SupervisorCommands.plan intent
      pure (toJSON (map (Command.arguments . if family == Mux.Windows then Psmux.render else Tmux.render) commands))
    "send-guard" -> do
      decision <- fields .: "decision" >>= parseObservation
      current <- fields .: "current" >>= parseObservation
      pure (toJSON (Guard.unchanged decision current))
    "watch-transition" -> do
      operation <- fields .: "command" >>= maybe (fail "unknown watch command") pure . Watch.parseOperation
      kind <- fields .: "kind" >>= maybe (fail "unknown target kind") pure . Watch.parseKind
      target <- fields .: "target"
      registry <- fields .: "registry"
      pure (toJSON (Watch.transition operation kind target registry))
    "recovery-transition" -> transitionValue False fields
    "recovery-deadline" -> transitionValue True fields
    "backoff" -> do
      settings <- parsePolicy fields
      attempt <- fields .: "attempt"
      seed <- fields .: "seed"
      pure (retryValue (Backoff.retry settings attempt seed))
    "classify-claude" -> do
      screen <- Capture.Screen . Normalize.normalise <$> fields .: "text" <*> fields .: "dead" <*> fields .:? "visual"
      pure (toJSON (Classify.classText (Classify.classificationClass (Claude.classify screen))))
    "classify-codex" -> do
      screen <- Capture.Screen . Normalize.normalise <$> fields .: "text" <*> fields .: "dead" <*> fields .:? "visual"
      pure (toJSON (Classify.classText (Classify.classificationClass (Codex.classify screen))))
    "screen-normalise" -> toJSON . Normalize.normalise <$> fields .: "text"
    "error-fingerprint" -> do
      block <- Fingerprint.ErrorBlock <$> fields .: "before" <*> fields .: "error" <*> fields .: "after"
      pure (toJSON (Fingerprint.fingerprintText (Fingerprint.fingerprint block)))
    "handshake" -> pure (toJSON handshake)
    "handoff" -> do
      supplied <- fields .:? "version"
      pure (toJSON (validHandoff supplied))
    "launch-plan" -> do
      state <- fields .: "state"
      status <- fields .:? "status" .!= 0
      observed <- maybe (fail "unknown launch observation") pure (Launch.observation state status)
      arguments <- fields .: "args"
      tty <- fields .: "tty"
      inside <- fields .: "inside"
      let plan = Launch.launchPlan observed arguments tty inside
      pure (object ["actions" .= map Launch.actionText (Launch.actions plan), "exit" .= Launch.exitCode plan])
    "sessions-list" -> do
      reports <- fields .: "reports" >>= mapM Sessions.parseReport
      pure (toJSON (Sessions.managedRows reports))
    "sessions-status" -> do
      reports <- fields .: "reports" >>= mapM Sessions.parseReport
      windows <- fields .: "windows"
      folder <- fields .: "folder"
      pure (toJSON (Sessions.statusRows windows folder (Sessions.managedRows reports)))
    "sessions-stop" -> do
      reports <- fields .: "reports" >>= mapM Sessions.parseReport
      windows <- fields .: "windows"
      name <- fields .: "name"
      pure $ case Sessions.stopCommand (Sessions.sessionTarget windows name reports) of
        Nothing -> object ["exit" .= (1 :: Int), "argv" .= ([] :: [String])]
        Just command -> object ["exit" .= (0 :: Int), "argv" .= Command.arguments (if windows then Psmux.render command else Tmux.render command)]
    "sessions-attach" -> do
      reports <- fields .: "reports" >>= mapM Sessions.parseReport
      windows <- fields .: "windows"
      name <- fields .: "name"
      terminal <- fields .: "terminal"
      inside <- fields .: "inside"
      pure $ case Sessions.sessionTarget windows name reports of
        Sessions.Managed row ->
          let Sessions.AttachPlan mode command = Sessions.attachPlan terminal inside row
           in object ["exit" .= (0 :: Int), "action" .= Sessions.attachModeText mode, "argv" .= Command.arguments (if windows then Psmux.render command else Tmux.render command)]
        Sessions.Foreign _ -> object ["exit" .= (1 :: Int), "action" .= ("refused" :: Text.Text), "argv" .= ([] :: [String])]
        Sessions.Missing _ -> object ["exit" .= (1 :: Int), "action" .= ("refused" :: Text.Text), "argv" .= ([] :: [String])]
        Sessions.Adopted _ -> object ["exit" .= (1 :: Int), "action" .= ("refused" :: Text.Text), "argv" .= ([] :: [String])]
    "adopt-decision" -> do
      agent <- fields .: "agent" >>= parseAgent
      current <- fields .:? "observation"
      existing <- fields .: "existing"
      pure (toJSON (Adopt.decision agent current existing))
    "adopt-revalidate" -> toJSON <$> (Adopt.revalidate <$> fields .: "entry" <*> fields .:? "observation")
    "adopt-stop" -> do
      entry <- fields .: "entry"
      current <- fields .:? "observation"
      windows <- fields .:? "windows" .!= False
      pure $ case Sessions.stopCommand (Sessions.Adopted (Adopt.View entry current)) of
        Nothing -> object ["exit" .= (0 :: Int), "action" .= ("forget" :: Text.Text), "argv" .= ([] :: [String])]
        Just command -> object ["exit" .= (0 :: Int), "action" .= ("kill" :: Text.Text), "argv" .= Command.arguments (if windows then Psmux.render command else Tmux.render command)]
    "adopt-endpoint" -> do
      family <- fields .: "family" >>= parseFamily
      namespace <- fields .: "namespace"
      session <- fields .: "session"
      pure (toJSON (Adopt.endpointIdentity (if family == Mux.Windows then Mux.Psmux else Mux.Tmux) namespace session))
    "session-name-valid" -> toJSON . isRight . makeSessionName <$> fields .: "name"
    "session-names" -> do
      windows <- fields .: "windows"
      canonical <- fields .: "canonical"
      agent <- fields .: "agent" >>= parseAgent
      let names = Name.deriveNames windows canonical agent
      pure (object ["base" .= Name.nameBase names, "plain" .= Name.sessionNameText (Name.plainName names), "hashed" .= Name.sessionNameText (Name.hashedName names)])
    "session-decision" -> do
      plain <- fields .: "plain" >>= parsePresence
      hashed <- fields .: "hashed" >>= parsePresence
      pure (toJSON (Name.decisionText (Name.decide plain hashed)))
    "session-selection" -> do
      windows <- fields .: "windows"
      canonical <- fields .: "canonical"
      agent <- fields .: "agent" >>= parseAgent
      sessions <- fields .: "sessions" >>= mapM parseObservedSession
      let Name.Selection decision name = Name.selectSession windows canonical agent sessions
      pure (object ["decision" .= Name.decisionText decision, "session" .= Name.sessionNameText name])
    "mux-version" -> do
      family <- fields .: "family" >>= parseFamily
      raw <- fields .: "raw"
      pure (toJSON (isRight (Mux.checkVersion (if family == Mux.Windows then Mux.Psmux else Mux.Tmux) raw)))
    "mux-candidates" -> toJSON . Mux.candidates <$> (fields .: "family" >>= parseFamily)
    "mux-remedy" -> do
      family <- fields .: "family" >>= parseFamily
      distribution <- fields .: "distribution"
      pure (toJSON (Mux.remedy family distribution))
    "mux-render" -> do
      family <- fields .: "family" >>= parseFamily
      command <- Command.parseCommand (toJSON fields)
      let rendered = if family == Mux.Windows then Psmux.render command else Tmux.render command
      pure (object ["executable" .= Command.executable rendered, "argv" .= Command.arguments rendered])
    "mux-process-tree" -> do
      family <- fields .: "family" >>= parseFamily
      command <- Command.parseCommand (toJSON fields)
      pure (toJSON (Command.ownsProcessTree (if family == Mux.Windows then Mux.Psmux else Mux.Tmux) command))
    "mux-pane-target" -> do
      family <- fields .: "family" >>= parseFamily
      name <- fields .: "session" >>= either (fail . show) pure . Name.makeSessionName
      pane <- fields .: "pane" >>= maybe (fail "invalid pane id") pure . Command.makePane
      let selected = Command.inSession (if family == Mux.Windows then Mux.Psmux else Mux.Tmux) name pane
      pure (object ["target" .= Command.paneText selected, "native" .= Command.paneId selected, "session" .= fromMaybe "" (Command.paneSession selected)])
    "mux-pane-valid" -> toJSON . isJust . Command.makePane <$> fields .: "pane"
    "mux-pane-selection" -> do
      panes <- fields .: "panes" >>= mapM (maybe (fail "invalid pane id") pure . Command.makePane)
      pure $ case Command.selectPane panes of
        Left message -> object ["error" .= message]
        Right selected -> object ["target" .= maybe "" Command.paneText selected]
    "mux-invocation" -> do
      family <- fields .: "family" >>= parseFamily
      command <- Command.parseCommand (toJSON fields)
      directory <- fields .: "directory"
      executable <- fields .: "tool"
      let invocation = Process.commandInvocation (if family == Mux.Windows then Mux.Psmux else Mux.Tmux) executable command (Process.CommandContext directory [] 10000000)
      pure (object ["executable" .= Process.executable invocation, "argv" .= Process.arguments invocation, "cwd" .= Process.directory invocation])
    "mux-dead-status" -> do
      family <- fields .: "family" >>= parseFamily
      status <- fields .:? "status"
      signal <- fields .:? "signal"
      fileStatus <- fields .:? "fileStatus"
      pure $ case Command.deadStatus (if family == Mux.Windows then Mux.Psmux else Mux.Tmux) status signal fileStatus of
        Just code -> object ["status" .= code]
        Nothing -> object ["error" .= ("unavailable-status" :: Text.Text)]
    "mux-reap-policy" -> do
      family <- fields .: "family" >>= parseFamily
      dead <- fields .: "dead"
      status <- fields .:? "status"
      pure (toJSON (Command.needsReap (if family == Mux.Windows then Mux.Psmux else Mux.Tmux) dead status))
    "mux-spec-acceptance" -> toJSON . Spec.accepts <$> parseJSON (toJSON fields)
    "agent-resolution" -> do
      agent <- fields .: "agent" >>= parseAgent
      family <- fields .: "family" >>= parseFamily
      cwd <- fields .: "cwd"
      extensions <- fields .:? "pathext" .!= []
      listings <- fields .: "listings"
      pure $ case Agent.selectAgent family agent cwd extensions listings of
        Right path -> object ["path" .= path]
        Left Agent.AgentMissing -> object ["error" .= ("AgentMissing" :: Text.Text)]
        Left (Agent.NativeRequired path) -> object ["error" .= ("NativeRequired" :: Text.Text), "path" .= path]
        Left (Agent.InvalidSearchDirectory _) -> object ["error" .= ("InvalidDirectory" :: Text.Text)]
        Left (Agent.AgentDiscoveryFailed _) -> object ["error" .= ("DiscoveryFailed" :: Text.Text)]
    "preflight-order" -> do
      mux <- fields .: "mux" >>= parseMuxObservation
      agent <- fields .: "agent" >>= parseAgentObservation
      auth <- fields .: "auth" >>= parseAuthState
      let Preflight.Decision checks outcome code = Preflight.decision mux agent auth
      pure (object ["checks" .= checks, "outcome" .= outcome, "exit" .= code])
    "preflight-warning" -> do
      agent <- fields .: "agent" >>= parseAgent
      family <- (fields .:? "family" .!= "Linux") >>= parseFamily
      distribution <- fields .:? "distribution" .!= "ubuntu"
      kind <- fields .: "error"
      path <- fields .:? "path" .!= "/usr/bin/tmux"
      raw <- fields .:? "version" .!= "tmux 3.1c"
      status <- fields .:? "exit" .!= 2
      let muxKind = if family == Mux.Windows then Mux.Psmux else Mux.Tmux
          hint = Mux.remedy family distribution
          muxVersion = case Mux.checkVersion muxKind raw of
            Left failure -> pure (Preflight.MultiplexerFailure (Mux.VersionRejected path failure hint))
            Right _ -> fail "version does not fail"
      failure <- case (kind :: Text.Text) of
        "MuxMissing" -> pure (Preflight.MultiplexerFailure (Mux.Unavailable muxKind hint))
        "MuxOld" -> muxVersion
        "MuxMalformed" -> muxVersion
        "MuxProbeFailed" -> pure (Preflight.MultiplexerFailure (Mux.ProbeFailed Process.TimedOut hint))
        "MuxProbeExit" -> pure (Preflight.MultiplexerFailure (Mux.ProbeExit path status "" hint))
        "MuxDiscoveryFailed" -> pure (Preflight.MultiplexerFailure (Mux.DiscoveryFailed "constructed"))
        "AgentMissing" -> pure (Preflight.AgentFailure Agent.AgentMissing)
        "NativeRequired" -> pure (Preflight.AgentFailure (Agent.NativeRequired path))
        "AgentDiscoveryFailed" -> pure (Preflight.AgentFailure (Agent.AgentDiscoveryFailed "constructed"))
        "InvalidDirectory" -> pure (Preflight.AgentFailure (Agent.InvalidSearchDirectory path))
        "LoggedOut" -> pure (Preflight.AuthenticationFailure (Auth.Exited 1))
        "AuthFailed" -> pure (Preflight.AuthenticationFailure (Auth.Exited status))
        _ -> fail "unknown failure"
      let (code, linesOfWarning) = Preflight.warning family distribution agent failure
      pure (object ["exit" .= code, "lines" .= linesOfWarning])
    "auth-classify" -> toJSON . show . Auth.classifyAuth <$> fields .: "outcome"
    "login-remedy" -> do
      agent <- fields .: "agent" >>= parseAgent
      pure (toJSON (Agent.loginRemedy (Agent.table Mux.Linux agent)))
    "login-shaped" -> do
      agent <- fields .: "agent" >>= parseAgent
      arguments <- fields .: "args"
      pure (toJSON (case Argv.checkedArgv agent (Agent.table Mux.Linux agent) "/tools/agent" arguments of Left _ -> True; Right _ -> False))
    "login-refusal-warning" -> do
      agent <- fields .: "agent" >>= parseAgent
      arguments <- fields .: "args"
      let (code, linesOfWarning) = case Argv.checkedArgv agent (Agent.table Mux.Linux agent) "/tools/agent" arguments of
            Left failure -> Argv.refusalWarning failure
            Right _ -> (0, [])
      pure (object ["exit" .= code, "lines" .= linesOfWarning])
    "auth-warning" -> do
      agent <- fields .: "agent" >>= parseAgent
      outcome <- fields .: "outcome"
      let (code, linesOfWarning) = Auth.warning agent outcome
      pure (object ["exit" .= code, "lines" .= linesOfWarning])
    "agent-table" -> do
      agent <- fields .: "agent" >>= parseAgent
      let entry = Agent.table Mux.Linux agent
      pure (object ["mandatory_flags" .= Agent.mandatoryFlags entry, "auth_args" .= Agent.authArguments entry, "recovery_text" .= Agent.recoveryText entry])
    "agent-details" -> do
      agent <- fields .: "agent" >>= parseAgent
      family <- fields .: "family" >>= parseFamily
      let entry = Agent.table family agent
      pure (object ["executable" .= Agent.executableName entry, "mandatory_flags" .= Agent.mandatoryFlags entry, "aliases" .= Agent.removableAliases entry, "auth_args" .= Agent.authArguments entry, "remedy" .= Agent.loginRemedy entry, "login_variants" .= Agent.loginVariants entry, "install_hint" .= Agent.installHint entry, "recovery_text" .= Agent.recoveryText entry])
    "launch-argv" -> do
      agent <- fields .: "agent" >>= parseAgent
      executable <- fields .: "executable"
      arguments <- fields .: "args"
      pure (toJSON (Argv.launchArgv (Agent.table Mux.Linux agent) executable arguments))
    "launch-final-argv" -> do
      agent <- fields .: "agent" >>= parseAgent
      family <- fields .: "family" >>= parseFamily
      executable <- fields .: "executable"
      arguments <- fields .: "args"
      pure (toJSON (Launch.launchArguments family agent executable arguments))
    "mux-spec-codec" -> do
      spec <- fields .: "spec"
      case Spec.decodeSpec (Spec.encodeSpec spec) of
        Left failure -> fail failure
        Right decoded -> pure (toJSON decoded)
    _ -> fail "unknown subject"

parsePolicy :: Object -> Parser Backoff.Policy
parsePolicy fields = do
  initial <- fields .:? "initial" .!= 30
  multiplier <- fields .:? "multiplier" .!= 2
  maximumWait <- fields .:? "maximum" .!= 900
  jitter <- fields .:? "jitter" .!= 0.2
  either (fail . Text.unpack) pure (Backoff.policy initial multiplier maximumWait jitter)

parseObservation :: Value -> Parser (Machine.Observation Text.Text)
parseObservation = withObject "observation" $ \fields -> do
  category <- fields .: "screen" >>= maybe (fail "unknown screen class") pure . Classify.parseClass
  fingerprint <- fields .: "fingerprint"
  text <- fields .: "text"
  pure (Machine.Observation category (if Text.null fingerprint then Nothing else Just fingerprint) text)

parsePoll :: Object -> Parser (Poll.Memory Text.Text, Maybe (Machine.Observation Text.Text), Poll.Poll Text.Text)
parsePoll fields = do
  settings <- parsePolicy fields
  now <- fields .: "now"
  watched <- fields .: "watched"
  paused <- fields .: "paused"
  revision <- fields .: "revision"
  previousRevision <- fields .: "previous_revision"
  observed <- fields .: "observed"
  observation <- if observed then Just <$> parseObservation (toJSON fields) else pure Nothing
  mode <- fields .: "state" >>= maybe (fail "unknown recovery mode") pure . Machine.parseMode
  incidentFingerprint <- fields .: "incident_fingerprint"
  deadline <- fields .: "deadline"
  handled <- fields .: "handled"
  attempt <- fields .: "attempt"
  seed <- fields .: "seed"
  let sent = if mode `elem` [Machine.RecoverySent, Machine.Verify] then Just (Machine.Observation Classify.Overloaded (Just incidentFingerprint) "sent") else Nothing
      incident = if Text.null incidentFingerprint then Nothing else Just (Machine.Incident incidentFingerprint deadline sent)
      state = Machine.State mode incident handled attempt seed
      entry = if watched then Just (Watch.Entry paused revision) else Nothing
      memory = Poll.Memory previousRevision state
  pure (memory, observation, Poll.step settings now entry observation memory)

pollValue :: Object -> Parser Value
pollValue fields = do
  (_, _, result) <- parsePoll fields
  pure $ case result of
    Poll.AwaitCapture -> object ["capture" .= True]
    Poll.Polled decision -> pollDecisionValue decision

pollDecisionValue :: Poll.Decision Text.Text -> Value
pollDecisionValue decision =
  let nextMemory = Poll.decisionMemory decision
      next = Poll.memoryMachine nextMemory
      notice value = object ["level" .= Poll.levelText (Poll.notificationLevel value), "message" .= Poll.notificationMessage value, "sinks" .= map Poll.sinkText (Poll.notificationSinks value)]
   in object ["capture" .= Poll.decisionCaptured decision, "stepped" .= Poll.decisionStepped decision, "rule" .= Poll.decisionRule decision, "revision" .= Poll.memoryRevision nextMemory, "state" .= Machine.modeText (Machine.stateMode next), "actions" .= map Machine.actionText (Poll.decisionActions decision), "incident" .= Machine.eventText (Poll.decisionEvent decision), "handled" .= Machine.stateHandled next, "attempt" .= Machine.stateAttempt next, "deadline" .= maybe 0 Machine.incidentDeadline (Machine.stateIncident next), "seed" .= Machine.stateSeed next, "notices" .= map notice (Poll.decisionNotifications decision), "results" .= map Poll.outcomeText (Poll.decisionResults decision)]

deliveryValue :: Object -> Parser Value
deliveryValue fields = do
  supplied <- fields .: "poll"
  (previous, _, result) <- parsePoll supplied
  proposed <- case result of
    Poll.AwaitCapture -> fail "delivery has no proposal"
    Poll.Polled decision -> if Machine.SendRecovery `elem` Poll.decisionActions decision then pure decision else fail "delivery needs a send proposal"
  outcome <- fields .: "outcome" >>= maybe (fail "unknown delivery outcome") pure . Log.parseDelivery
  freshFields <- fields .: "fresh" :: Parser Object
  settings <- parsePolicy supplied
  now <- supplied .: "now"
  entry <- Watch.Entry <$> supplied .: "paused" <*> supplied .: "revision"
  observed <-
    if Keys.null freshFields
      then pure Nothing
      else do
        observation <- parseObservation (toJSON freshFields)
        case Poll.step settings now (Just entry) (Just observation) previous of
          Poll.AwaitCapture -> fail "fresh delivery observation did not step"
          Poll.Polled decision -> pure (Just decision)
  let completed = Delivery.complete outcome previous proposed observed
      memory = Delivery.completionMemory completed
      state = Poll.memoryMachine memory
      incident = Machine.stateIncident state
      memoryValue = object ["revision" .= Poll.memoryRevision memory, "state" .= Machine.modeText (Machine.stateMode state), "fingerprint" .= maybe "" Machine.incidentFingerprint incident, "handled" .= Machine.stateHandled state, "attempt" .= Machine.stateAttempt state, "deadline" .= maybe 0 Machine.incidentDeadline incident, "seed" .= Machine.stateSeed state, "sent" .= maybe False (isJust . Machine.sentObservation) incident]
  pure (object ["memory" .= memoryValue, "decision" .= maybe (object []) pollDecisionValue (Delivery.completionDecision completed)])

recordValue :: Object -> Parser Value
recordValue fields = do
  event <- fields .: "event"
  context <- fields .: "context"
  let checked = either (fail . Text.unpack) pure
  case (event :: Text.Text) of
    "poll" -> do
      (previous, observation, result) <- fields .: "poll" >>= withObject "poll input" parsePoll
      case result of
        Poll.AwaitCapture -> pure (toJSON ([] :: [Log.Record]))
        Poll.Polled decision -> toJSON <$> checked (Log.pollRecords context previous observation decision)
    "attempt" -> do
      family <- fields .: "family" >>= parseFamily
      observation <- fields .: "observation" >>= parseObservation
      outcome <- fields .: "outcome" >>= maybe (fail "unknown delivery") pure . Log.parseDelivery
      record <- checked (Log.attemptRecord context family observation outcome)
      pure (toJSON [record])
    "result" -> do
      outcome <- fields .: "outcome" >>= maybe (fail "unknown incident result") pure . Log.parseOutcome
      record <- checked (Log.resultRecord context outcome)
      pure (toJSON [record])
    "notify" -> do
      level <- fields .: "level" >>= maybe (fail "unknown notification level") pure . Log.parseLevel
      message <- fields .: "message"
      pure (toJSON [Log.notifyRecord context level message])
    _ -> fail "unknown record event"

retryValue :: Backoff.Retry -> Value
retryValue scheduled = object ["delay" .= Backoff.retryDelay scheduled, "base" .= Backoff.retryBase scheduled, "level" .= Backoff.levelText (Backoff.retryLevel scheduled), "notify" .= Backoff.retryNotify scheduled, "next_seed" .= Backoff.retrySeed scheduled]

noticeValue :: Machine.Notice -> Value
noticeValue notice = case notice of
  Machine.RetryNotice scheduled -> object ["level" .= Backoff.levelText (Backoff.retryLevel scheduled), "attempt" .= Backoff.retryAttempt scheduled, "delay" .= Backoff.retryDelay scheduled]
  Machine.TerminalNotice category -> object ["level" .= ("error" :: Text.Text), "reason" .= Classify.classText category]
  Machine.NotAcknowledgedNotice -> object ["level" .= ("error" :: Text.Text), "reason" .= ("not-acknowledged" :: Text.Text)]

transitionValue :: Bool -> Object -> Parser Value
transitionValue detailed fields = do
  settings <- parsePolicy fields
  mode <- fields .: "state" >>= maybe (fail "unknown recovery mode") pure . Machine.parseMode
  category <- fields .: "screen" >>= maybe (fail "unknown screen class") pure . Classify.parseClass
  fingerprint <- nonempty <$> fields .: "fingerprint"
  incidentFingerprint <- nonempty <$> fields .: "incident_fingerprint"
  handled <- fields .: "handled"
  attempt <- fields .: "attempt"
  due <- fields .: "deadline_reached"
  deadline <- fields .:? "deadline" .!= if due then 0 else 1
  now <- fields .:? "now" .!= 0
  seed <- fields .:? "seed" .!= 1
  text <- fields .:? "text" .!= "sent"
  let incident = fmap (\key -> Machine.Incident key deadline (Just (Machine.Observation Classify.Overloaded (Just key) "sent"))) incidentFingerprint
      state = Machine.State mode incident handled attempt seed
      decision = Machine.step settings now (Machine.Observation category fingerprint text) state
      next = Machine.decisionState decision
      result = ["state" .= Machine.modeText (Machine.stateMode next), "actions" .= map Machine.actionText (Machine.decisionActions decision), "incident" .= Machine.eventText (Machine.decisionEvent decision), "handled" .= Machine.stateHandled next, "attempt" .= Machine.stateAttempt next]
      timing = ["deadline" .= maybe 0 Machine.incidentDeadline (Machine.stateIncident next), "notices" .= map noticeValue (Machine.notifications (Machine.decisionActions decision))]
  pure (object (result ++ if detailed then timing else []))
  where
    nonempty text = if Text.null text then Nothing else Just text

parsePresence :: Text.Text -> Parser Name.Presence
parsePresence "absent" = pure Name.Absent
parsePresence "owned" = pure Name.Owned
parsePresence "foreign" = pure Name.Foreign
parsePresence _ = fail "unknown session presence"

parseObservedSession :: Value -> Parser Name.ObservedSession
parseObservedSession = withObject "observed session" $ \fields -> do
  name <- fields .: "name" >>= either (fail . show) pure . makeSessionName
  owner <- fields .:? "owner"
  agent <- fields .:? "agent" >>= traverse parseAgent
  folder <- fields .:? "folder"
  pure (Name.ObservedSession name owner agent folder)

parseMuxObservation :: Text.Text -> Parser Preflight.MuxObservation
parseMuxObservation "missing" = pure Preflight.MuxMissing
parseMuxObservation "old" = pure Preflight.MuxOld
parseMuxObservation "ready" = pure Preflight.MuxReady
parseMuxObservation _ = fail "unknown multiplexer observation"

parseAgentObservation :: Text.Text -> Parser Preflight.AgentObservation
parseAgentObservation "missing" = pure Preflight.AgentMissing
parseAgentObservation "shim" = pure Preflight.AgentShim
parseAgentObservation "present" = pure Preflight.AgentPresent
parseAgentObservation _ = fail "unknown agent observation"

parseAuthState :: Text.Text -> Parser Auth.AuthState
parseAuthState "logged-in" = pure Auth.LoggedIn
parseAuthState "logged-out" = pure Auth.LoggedOut
parseAuthState "failed" = pure Auth.CheckFailed
parseAuthState _ = fail "unknown auth observation"

parseAgent :: Text.Text -> Parser Agent.Agent
parseAgent value = maybe (fail "unknown agent") pure (Agent.agentFromText value)

parseFamily :: Text.Text -> Parser Mux.Family
parseFamily value = maybe (fail "unknown family") pure (Mux.familyFromText value)

answer :: Bytes.ByteString -> Bytes.ByteString
answer input =
  case eitherDecode input >>= parseEither evaluate of
    Left _ -> encode (object ["error" .= ("invalid-case" :: Text.Text)])
    Right result -> encode result

answers :: [Bytes.ByteString] -> [Bytes.ByteString]
answers = map answer

main :: IO ()
main = Bytes.getContents >>= mapM_ Bytes.putStrLn . answers . Bytes.lines
