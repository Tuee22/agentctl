-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Supervisor.Poll
  ( Memory (..),
    initial,
    Poll (..),
    Decision (..),
    Outcome (..),
    outcomeText,
    Level (..),
    levelText,
    Sink (..),
    sinkText,
    Notification (..),
    notification,
    step,
  )
where

import qualified AgentCtl.Observe.Classify as Classify
import qualified AgentCtl.Recovery.Backoff as Backoff
import qualified AgentCtl.Recovery.Machine as Machine
import qualified AgentCtl.Supervisor.Watch as Watch
import qualified Data.Set as Set
import Data.Text (Text)
import qualified Data.Text as Text
import Data.Word (Word64)

data Memory key = Memory {memoryRevision :: Integer, memoryMachine :: Machine.State key} deriving (Eq, Show)

initial :: Word64 -> Memory key
initial seed = Memory 0 (Machine.initial seed)

data Poll key = AwaitCapture | Polled (Decision key) deriving (Eq, Show)

data Decision key = Decision
  { decisionMemory :: Memory key,
    decisionCaptured :: Bool,
    decisionStepped :: Bool,
    decisionRule :: Text,
    decisionActions :: [Machine.Action],
    decisionEvent :: Machine.Event,
    decisionNotifications :: [Notification],
    decisionResults :: [Outcome]
  }
  deriving (Eq, Show)

data Outcome = Recovered | Ended | NotAcknowledged | Unresolved | Escalated deriving (Eq, Show)

outcomeText :: Outcome -> Text
outcomeText outcome = case outcome of
  Recovered -> "recovered"
  Ended -> "ended"
  NotAcknowledged -> "not-acknowledged"
  Unresolved -> "unresolved"
  Escalated -> "escalated"

data Level = Info | Warning | Error deriving (Eq, Show)

levelText :: Level -> Text
levelText level = case level of
  Info -> "info"
  Warning -> "warning"
  Error -> "error"

data Sink = Stderr | DecisionLog deriving (Eq, Show)

sinkText :: Sink -> Text
sinkText sink = case sink of
  Stderr -> "stderr"
  DecisionLog -> "log"

data Notification = Notification
  { notificationLevel :: Level,
    notificationMessage :: Text,
    notificationSinks :: [Sink]
  }
  deriving (Eq, Show)

notification :: Machine.Notice -> Notification
notification notice = Notification level message [Stderr, DecisionLog]
  where
    (level, message) = case notice of
      Machine.RetryNotice scheduled ->
        ( case Backoff.retryLevel scheduled of
            Backoff.Info -> Info
            Backoff.Warning -> Warning,
          "retry attempt " <> Text.pack (show (Backoff.retryAttempt scheduled)) <> " in " <> Text.pack (show (Backoff.retryDelay scheduled)) <> " s"
        )
      Machine.TerminalNotice category -> (Error, "requires attention: " <> Classify.classText category)
      Machine.NotAcknowledgedNotice -> (Error, "recovery text was not acknowledged")

step :: (Ord key) => Backoff.Policy -> Double -> Maybe Watch.Entry -> Maybe (Machine.Observation key) -> Memory key -> Poll key
step settings now watched observed memory = case watched of
  Nothing -> closed "unwatched" 0
  Just entry
    | Watch.entryPaused entry -> closed "paused" (Watch.entryRevision entry)
    | otherwise -> case observed of
        Nothing -> AwaitCapture
        Just observation
          | Watch.entryRevision entry /= memoryRevision memory ->
              let next = Machine.baseline observation (dropIncident state)
               in Polled (Decision (Memory (Watch.entryRevision entry) next) True False "baseline" [] closingEvent [] closingResults)
          | otherwise ->
              let decision = Machine.step settings now observation state
                  event = Machine.decisionEvent decision
                  actions = Machine.decisionActions decision
                  rule = "step/" <> Machine.modeText (Machine.stateMode state) <> "/" <> Classify.classText (Machine.observationClass observation) <> "/" <> Machine.eventText event
               in Polled (Decision (memory {memoryMachine = Machine.decisionState decision}) True True rule actions event (map notification (Machine.notifications actions)) (results event))
  where
    state = memoryMachine memory
    closingEvent = maybe Machine.NoIncident (const Machine.Ended) (Machine.stateIncident state)
    closingResults = results closingEvent
    closed rule revision = Polled (Decision (Memory revision (dropIncident state)) False False rule [] closingEvent [] closingResults)

dropIncident :: (Ord key) => Machine.State key -> Machine.State key
dropIncident state =
  state
    { Machine.stateMode = Machine.Monitoring,
      Machine.stateIncident = Nothing,
      Machine.stateHandled = maybe (Machine.stateHandled state) (\incident -> Set.insert (Machine.incidentFingerprint incident) (Machine.stateHandled state)) (Machine.stateIncident state)
    }

results :: Machine.Event -> [Outcome]
results event = case event of
  Machine.NoIncident -> []
  Machine.Opened -> []
  Machine.Continued -> []
  Machine.Replaced -> []
  Machine.Ended -> [Ended]
  Machine.Recovered -> [Recovered]
  Machine.Escalated -> [Escalated]
  Machine.NotAcknowledged -> [NotAcknowledged]
