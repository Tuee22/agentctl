-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Supervisor.Runtime (Failure (..), run) where

import qualified AgentCtl.Adopt as Adopt
import qualified AgentCtl.Agent as Agent
import qualified AgentCtl.Mux as Mux
import qualified AgentCtl.Mux.Command as Command
import qualified AgentCtl.Observe.Capture as Capture
import qualified AgentCtl.Observe.Classify as Classify
import qualified AgentCtl.Observe.Classify.Agent as Classifier
import qualified AgentCtl.Observe.Fingerprint as Fingerprint
import qualified AgentCtl.Process as Process
import qualified AgentCtl.Recovery.Machine as Machine
import qualified AgentCtl.Session.Name as Name
import qualified AgentCtl.Sessions as Sessions
import qualified AgentCtl.Supervisor.Commands as Commands
import qualified AgentCtl.Supervisor.Delivery as Delivery
import qualified AgentCtl.Supervisor.Guard as Guard
import qualified AgentCtl.Supervisor.Lock as Lock
import qualified AgentCtl.Supervisor.Log as Log
import qualified AgentCtl.Supervisor.Log.File as LogFile
import qualified AgentCtl.Supervisor.Poll as Poll
import qualified AgentCtl.Supervisor.Settings as Settings
import qualified AgentCtl.Supervisor.Watch as Watch
import Control.Concurrent (threadDelay)
import Control.Monad (foldM, forM_, unless, void, when)
import Control.Monad.Trans.Class (lift)
import Control.Monad.Trans.Except (ExceptT (..), runExceptT, throwE)
import Data.Char (ord)
import Data.List (find)
import Data.Map.Strict (Map)
import qualified Data.Map.Strict as Map
import Data.Maybe (fromMaybe, isJust)
import Data.Text (Text)
import qualified Data.Text as Text
import qualified Data.Text.IO as Text
import Data.Time (UTCTime, getCurrentTime)
import Data.Word (Word64)
import GHC.Clock (getMonotonicTimeNSec)
import System.IO (stderr)

data Failure
  = QueryFailure Sessions.QueryError
  | RegistryFailure Watch.RegistryError
  | LockFailure Lock.LockError
  | LogFailure LogFile.FileError
  | CaptureFailure Capture.CaptureError
  | CommandFailure Text
  | InvariantFailure Text
  deriving (Eq, Show)

data Target = Target Agent.Agent Command.Pane Integer (Maybe Adopt.Entry) deriving (Eq, Show)

data Tracked = Tracked (Maybe Target) (Poll.Memory Text)

data Environment = Environment Sessions.Request Settings.Settings Sessions.Query LogFile.Writer (IO Bool) Text Word64

type Effect = ExceptT Failure IO

run :: Sessions.Request -> Settings.Settings -> Sessions.Query -> LogFile.Writer -> IO Bool -> Text -> Word64 -> IO (Either Failure ())
run request settings query writer stopped identifier seed = runExceptT (loop environment Map.empty)
  where
    environment = Environment request settings query writer stopped identifier seed

loop :: Environment -> Map Text Tracked -> Effect ()
loop environment@(Environment _ settings query _ stopped _ _) tracked = do
  ending <- lift stopped
  if ending
    then shutdown environment tracked
    else do
      began <- lift getMonotonicTimeNSec
      (registry, targets) <- withWatch environment $ do
        registry <- loadWatch environment
        targets <- checked QueryFailure (Sessions.queryTargets query)
        pure (registry, targets)
      let selected = Map.keys (Watch.registryEntries registry) ++ [name | (name, Tracked _ memory) <- Map.toList tracked, Map.notMember name (Watch.registryEntries registry), Poll.memoryRevision memory /= 0]
      next <- foldM (pollTarget environment targets) tracked selected
      sleepUntil stopped began (Settings.pollSeconds settings)
      loop environment next

pollTarget :: Environment -> [Sessions.Target] -> Map Text Tracked -> Text -> Effect (Map Text Tracked)
pollTarget environment@(Environment request _ _ _ stopped _ seed) targets tracked name = do
  ending <- lift stopped
  if ending
    then pure tracked
    else withWatch environment $ do
      registry <- loadWatch environment
      let entry = Map.lookup name (Watch.registryEntries registry)
          original@(Tracked oldTarget oldMemory) = fromMaybe (Tracked Nothing (Poll.initial (Text.foldl' (\value character -> value * 1099511628211 + fromIntegral (ord character)) seed name))) (Map.lookup name tracked)
          (agent, current) = resolve (Sessions.requestFamily request == Mux.Windows) name targets
          knownAgent = agent `orElse` fmap targetAgent oldTarget
          memory = if isJust oldTarget && isJust current && oldTarget /= current then oldMemory {Poll.memoryRevision = 0} else oldMemory
      next <- case entry of
        Just active | not (Watch.entryPaused active) -> case current of
          Nothing -> vanished environment name knownAgent original registry
          Just target -> observeTarget environment name active target memory
        Nothing -> suspended environment name knownAgent oldTarget oldMemory Nothing
        Just paused -> suspended environment name knownAgent oldTarget oldMemory (Just paused)
      pure (Map.insert name next tracked)
  where
    orElse (Just value) _ = Just value
    orElse Nothing other = other

observeTarget :: Environment -> Text -> Watch.Entry -> Target -> Poll.Memory Text -> Effect Tracked
observeTarget environment@(Environment request settings query _ stopped _ _) name entry target memory = do
  ending <- lift stopped
  if ending
    then pure (Tracked (Just target) memory)
    else do
      captured <- lift (capture environment target)
      case captured of
        Left failure -> do
          endingAfterFailure <- lift stopped
          if endingAfterFailure
            then pure (Tracked (Just target) memory)
            else do
              current <- checked QueryFailure (Sessions.queryTargets query)
              let (_, resolved) = resolve (Sessions.requestFamily request == Mux.Windows) name current
              case resolved of
                Nothing -> loadWatch environment >>= vanished environment name (Just (targetAgent target)) (Tracked (Just target) memory)
                Just _ -> throwE (CaptureFailure failure)
        Right observed -> do
          stamp <- lift getCurrentTime
          now <- clock
          let result = Poll.step (Settings.backoffPolicy settings) now (Just entry) (Just observed) memory
          decision <- polled result
          traceDecisionAt environment stamp name (Just (targetAgent target)) memory (Just observed) decision
          endingAfterCapture <- lift stopped
          let sends = Machine.SendRecovery `elem` Poll.decisionActions decision
              committed = if sends then memory else Poll.decisionMemory decision
          if endingAfterCapture
            then pure (Tracked (Just target) committed)
            else do
              forM_ (Poll.decisionActions decision) (passive environment)
              if sends
                then deliver environment name entry target memory observed decision
                else pure (Tracked (Just target) committed)

suspended :: Environment -> Text -> Maybe Agent.Agent -> Maybe Target -> Poll.Memory Text -> Maybe Watch.Entry -> Effect Tracked
suspended environment@(Environment _ settings _ _ _ _ _) name agent target memory entry = do
  now <- clock
  decision <- polled (Poll.step (Settings.backoffPolicy settings) now entry Nothing memory)
  traceDecision environment name agent memory Nothing decision
  pure (Tracked target (Poll.decisionMemory decision))

vanished :: Environment -> Text -> Maybe Agent.Agent -> Tracked -> Watch.Registry -> Effect Tracked
vanished environment@(Environment request _ _ _ _ _ _) name agent (Tracked target memory) registry = do
  next <- suspended environment name agent target memory Nothing
  notify environment name agent Poll.Warning "watched target disappeared"
  let decision = Watch.transition Watch.Unwatch Watch.MissingTarget name registry
  checked RegistryFailure (Watch.save (Sessions.requestPaths request) (Watch.decisionRegistry decision))
  commands environment (Watch.decisionCommands decision)
  pure next

deliver :: Environment -> Text -> Watch.Entry -> Target -> Poll.Memory Text -> Machine.Observation Text -> Poll.Decision Text -> Effect Tracked
deliver environment@(Environment request settings query _ stopped _ _) name entry target memory observed proposed = do
  registry <- loadWatch environment
  ending <- lift stopped
  if ending
    then pure (Tracked (Just target) memory)
    else
      if Map.lookup name (Watch.registryEntries registry) /= Just entry
        then suspended environment name (Just (targetAgent target)) (Just target) memory (Map.lookup name (Watch.registryEntries registry))
        else do
          current <- checked QueryFailure (Sessions.queryTargets query)
          let (_, resolved) = resolve (Sessions.requestFamily request == Mux.Windows) name current
          revalidated <- case target of
            Target _ _ _ Nothing -> pure (resolved == Just target)
            Target _ _ _ (Just adopted) ->
              if resolved == Just target then isJust <$> checked QueryFailure (Sessions.queryAdopted query adopted) else pure False
          if not revalidated
            then finish Log.Aborted Nothing Nothing
            else do
              captured <- lift (capture environment target)
              case captured of
                Left _ -> finish Log.Failed Nothing Nothing
                Right fresh ->
                  if Guard.unchanged observed fresh
                    then do
                      sent <- send environment (Commands.plan (Commands.Send (Sessions.requestFamily request) (targetAgent target) (targetPane target)))
                      finish (if sent then Log.Sent else Log.Failed) (Just fresh) Nothing
                    else do
                      now <- clock
                      freshDecision <- polled (Poll.step (Settings.backoffPolicy settings) now (Just entry) (Just fresh) memory)
                      finish Log.Aborted (Just fresh) (Just freshDecision)
  where
    finish outcome beforeSend freshDecision = do
      context <- logContext environment name (Just (targetAgent target))
      record <- either (throwE . InvariantFailure) pure (Log.attemptRecord context (Sessions.requestFamily request) (fromMaybe (Machine.Observation Classify.Unknown Nothing "") beforeSend) outcome)
      append environment [record]
      let completion = Delivery.complete outcome memory proposed freshDecision
      forM_ (Delivery.completionDecision completion) (traceDecision environment name (Just (targetAgent target)) memory beforeSend)
      pure (Tracked (Just target) (Delivery.completionMemory completion))

send :: Environment -> [Command.Command] -> Effect Bool
send _ [] = pure True
send environment@(Environment _ _ query _ stopped _ _) (command : remaining) = do
  ending <- lift stopped
  if ending
    then pure False
    else do
      result <- lift (Process.runCommand (Sessions.queryMultiplexer query) command (Sessions.queryContext query))
      case result of
        Right output | Process.exitCode output == 0 -> send environment remaining
        Right _ -> pure False
        Left _ -> pure False

capture :: Environment -> Target -> IO (Either Capture.CaptureError (Machine.Observation Text))
capture (Environment _ _ query _ _ _ _) target = do
  observed <- Capture.capture (Sessions.queryMultiplexer query) (targetPane target) (Sessions.queryContext query)
  pure $ fmap classify observed
  where
    classify screen =
      let classified = Classifier.classify (targetAgent target) screen
          fingerprint = Fingerprint.fingerprintText . Fingerprint.fingerprint <$> Classify.classificationError classified
       in Machine.Observation (Classify.classificationClass classified) fingerprint (Capture.screenText screen)

traceDecision :: Environment -> Text -> Maybe Agent.Agent -> Poll.Memory Text -> Maybe (Machine.Observation Text) -> Poll.Decision Text -> Effect ()
traceDecision environment name agent previous observed decision = do
  stamp <- lift getCurrentTime
  traceDecisionAt environment stamp name agent previous observed decision

traceDecisionAt :: Environment -> UTCTime -> Text -> Maybe Agent.Agent -> Poll.Memory Text -> Maybe (Machine.Observation Text) -> Poll.Decision Text -> Effect ()
traceDecisionAt environment@(Environment _ _ _ _ _ identifier _) stamp name agent previous observed decision = case agent of
  Nothing -> when (Poll.decisionCaptured decision || Poll.decisionStepped decision || not (null (Poll.decisionResults decision))) (throwE (InvariantFailure "unresolved target produced a machine decision"))
  Just known -> do
    let context = Log.Context stamp identifier name (Just known)
    records <- either (throwE . InvariantFailure) pure (Log.pollRecords context previous observed decision)
    append environment records
    forM_ (Poll.decisionNotifications decision) $ \notice -> when (Poll.Stderr `elem` Poll.notificationSinks notice) (lift (Text.hPutStrLn stderr ("agentctl: " <> name <> ": " <> Poll.notificationMessage notice)))

notify :: Environment -> Text -> Maybe Agent.Agent -> Poll.Level -> Text -> Effect ()
notify environment name agent level message = do
  context <- logContext environment name agent
  append environment [Log.notifyRecord context level message]
  lift (Text.hPutStrLn stderr ("agentctl: " <> name <> ": " <> message))

logContext :: Environment -> Text -> Maybe Agent.Agent -> Effect Log.Context
logContext (Environment _ _ _ _ _ identifier _) name agent = do
  time <- lift getCurrentTime
  pure (Log.Context time identifier name agent)

append :: Environment -> [Log.Record] -> Effect ()
append (Environment _ _ _ writer _ _ _) records = checked LogFailure (LogFile.append writer records)

loadWatch :: Environment -> Effect Watch.Registry
loadWatch (Environment request _ _ _ _ _ _) = checked RegistryFailure (Watch.load (Sessions.requestPaths request))

withWatch :: Environment -> Effect value -> Effect value
withWatch (Environment request _ _ _ _ _ _) action = do
  result <- lift (Lock.withLock (Sessions.requestPaths request) Lock.WatchRegistry (runExceptT action))
  -- External watch writers retry every ten milliseconds; leave them a turn.
  lift (threadDelay 20000)
  either (throwE . LockFailure) (either throwE pure) result

commands :: Environment -> [Command.Command] -> Effect ()
commands (Environment _ _ query _ _ _ _) planned = forM_ planned $ \command -> do
  output <- checked (CommandFailure . Text.pack . show) (Process.runCommand (Sessions.queryMultiplexer query) command (Sessions.queryContext query))
  when (Process.exitCode output /= 0) (throwE (CommandFailure (Process.stderrText output)))

shutdown :: Environment -> Map Text Tracked -> Effect ()
shutdown environment tracked = do
  forM_ (Map.toList tracked) $ \(name, Tracked target memory) -> when (isJust (Machine.stateIncident (Poll.memoryMachine memory))) $ void (suspended environment name (targetAgent <$> target) target memory Nothing)
  commands environment (Commands.plan Commands.Shutdown)

noticeIntent :: Machine.Notice -> Commands.Intent
noticeIntent notice = case notice of
  Machine.RetryNotice _ -> Commands.Notify
  Machine.TerminalNotice Classify.Exited -> Commands.Exited
  Machine.TerminalNotice _ -> Commands.Escalate
  Machine.NotAcknowledgedNotice -> Commands.Escalate

passive :: Environment -> Machine.Action -> Effect ()
passive environment action = case action of
  Machine.WaitUntil _ _ -> commands environment (Commands.plan Commands.Wait)
  Machine.Notify notice -> commands environment (Commands.plan (noticeIntent notice))
  Machine.SendRecovery -> pure ()

resolve :: Bool -> Text -> [Sessions.Target] -> (Maybe Agent.Agent, Maybe Target)
resolve windows name targets = case find ((== identity name) . identity . targetName) targets of
  Nothing -> (Nothing, Nothing)
  Just (Sessions.Managed row) -> (Just (Sessions.rowAgent row), Just (Target (Sessions.rowAgent row) (Sessions.rowPane row) (Sessions.rowPid row) Nothing))
  Just (Sessions.Adopted view) ->
    let entry = Adopt.viewEntry view
     in (Just (Adopt.entryAgent entry), if isJust (Adopt.viewCurrent view) then Just (Target (Adopt.entryAgent entry) (Adopt.entryPane entry) (Adopt.entryPid entry) (Just entry)) else Nothing)
  Just (Sessions.Foreign _) -> (Nothing, Nothing)
  Just (Sessions.Missing _) -> (Nothing, Nothing)
  where
    identity = if windows then Text.toCaseFold else id
    targetName target = case target of
      Sessions.Managed row -> Name.sessionNameText (Sessions.rowName row)
      Sessions.Adopted view -> Command.paneText (Adopt.entryPane (Adopt.viewEntry view))
      Sessions.Foreign nameValue -> Name.sessionNameText nameValue
      Sessions.Missing nameValue -> nameValue

targetAgent :: Target -> Agent.Agent
targetAgent (Target agent _ _ _) = agent

targetPane :: Target -> Command.Pane
targetPane (Target _ pane _ _) = pane

checked :: (failure -> Failure) -> IO (Either failure value) -> Effect value
checked convert action = ExceptT (either (Left . convert) Right <$> action)

polled :: Poll.Poll Text -> Effect (Poll.Decision Text)
polled Poll.AwaitCapture = throwE (InvariantFailure "capture did not produce a poll decision")
polled (Poll.Polled decision) = pure decision

clock :: Effect Double
clock = (/ 1000000000) . fromIntegral <$> lift getMonotonicTimeNSec

sleepUntil :: IO Bool -> Word64 -> Double -> Effect ()
sleepUntil stopped began interval = do
  ending <- lift stopped
  now <- lift getMonotonicTimeNSec
  let remaining = interval - fromIntegral (now - began) / 1000000000
  unless (ending || remaining <= 0) $ do
    lift (threadDelay (max 1 (ceiling (min 0.05 remaining * 1000000))))
    sleepUntil stopped began interval
