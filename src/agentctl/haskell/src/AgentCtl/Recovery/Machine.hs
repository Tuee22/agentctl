-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Recovery.Machine
  ( Mode (..),
    modeText,
    parseMode,
    Observation (..),
    Incident (..),
    State (..),
    initial,
    baseline,
    Action (..),
    Notice (..),
    notifications,
    actionText,
    Event (..),
    eventText,
    Decision (..),
    step,
    blocking,
  )
where

import AgentCtl.Observe.Classify (ScreenClass (..))
import qualified AgentCtl.Recovery.Backoff as Backoff
import Data.List (find, nub)
import Data.Maybe (isNothing, maybeToList)
import Data.Set (Set)
import qualified Data.Set as Set
import Data.Text (Text)
import Data.Word (Word64)

data Mode = Monitoring | SuspectedFailure | ConfirmIdle | Backoff | RecoverySent | Verify | Escalate deriving (Eq, Ord, Enum, Bounded, Show)

modeText :: Mode -> Text
modeText mode = case mode of
  Monitoring -> "MONITORING"
  SuspectedFailure -> "SUSPECTED_FAILURE"
  ConfirmIdle -> "CONFIRM_IDLE"
  Backoff -> "BACKOFF"
  RecoverySent -> "RECOVERY_SENT"
  Verify -> "VERIFY"
  Escalate -> "ESCALATE"

parseMode :: Text -> Maybe Mode
parseMode text = find ((== text) . modeText) [minBound .. maxBound]

data Observation key = Observation
  { observationClass :: ScreenClass,
    observationFingerprint :: Maybe key,
    observationText :: Text
  }
  deriving (Eq, Show)

data Incident key = Incident
  { incidentFingerprint :: key,
    incidentDeadline :: Double,
    sentObservation :: Maybe (Observation key)
  }
  deriving (Eq, Show)

data State key = State
  { stateMode :: Mode,
    stateIncident :: Maybe (Incident key),
    stateHandled :: Set key,
    stateAttempt :: Integer,
    stateSeed :: Word64
  }
  deriving (Eq, Show)

initial :: Word64 -> State key
initial = State Monitoring Nothing Set.empty 1

baseline :: (Ord key) => Observation key -> State key -> State key
baseline observation state = state {stateMode = Monitoring, stateIncident = Nothing, stateHandled = remember (observationFingerprint observation) (stateHandled state)}

data Notice = RetryNotice Backoff.Retry | TerminalNotice ScreenClass | NotAcknowledgedNotice deriving (Eq, Show)

data Action = WaitUntil Double Backoff.Retry | SendRecovery | Notify Notice deriving (Eq, Show)

actionText :: Action -> Text
actionText action = case action of
  WaitUntil _ _ -> "wait"
  SendRecovery -> "send"
  Notify _ -> "notify"

-- A scheduled retry and an explicit confirmation may name the same notice.
-- The interpreter delivers each notice once per decision.
notifications :: [Action] -> [Notice]
notifications = nub . concatMap notices
  where
    notices action = case action of
      WaitUntil _ scheduled -> [RetryNotice scheduled | Backoff.retryNotify scheduled]
      Notify notice -> [notice]
      SendRecovery -> []

data Event = NoIncident | Opened | Continued | Replaced | Ended | Recovered | Escalated | NotAcknowledged deriving (Eq, Show)

eventText :: Event -> Text
eventText event = case event of
  NoIncident -> "none"
  Opened -> "opened"
  Continued -> "continued"
  Replaced -> "replaced"
  Ended -> "ended"
  Recovered -> "recovered"
  Escalated -> "escalated"
  NotAcknowledged -> "not-acknowledged"

data Decision key = Decision
  { decisionState :: State key,
    decisionActions :: [Action],
    decisionEvent :: Event
  }
  deriving (Eq, Show)

remember :: (Ord key) => Maybe key -> Set key -> Set key
remember fingerprint handled = foldr Set.insert handled (maybeToList fingerprint)

blocking :: ScreenClass -> Bool
blocking category = category `elem` [TrustDialog, BypassWarning, ApprovalDialog, PartialInput]

hard :: ScreenClass -> Bool
hard category = category `elem` [UsageLimit, AuthError, ContextExhausted, LoginScreen, Exited]

fresh :: (Ord key) => Maybe key -> State key -> Bool
fresh fingerprint state = maybe False (`Set.notMember` stateHandled state) fingerprint

step :: (Ord key) => Backoff.Policy -> Double -> Observation key -> State key -> Decision key
step settings now observation state
  | stateMode state == Escalate =
      if observationClass observation `elem` [Working, IdlePrompt]
        then Decision (state {stateMode = Monitoring, stateIncident = Nothing}) [] NoIncident
        else Decision state [] NoIncident
  | hard category && (category == Exited || isNothing (observationFingerprint observation) || fresh (observationFingerprint observation) state) =
      Decision (state {stateMode = Escalate, stateIncident = Nothing, stateHandled = remember (observationFingerprint observation) (stateHandled state)}) [Notify (TerminalNotice category)] Escalated
  | otherwise = case stateMode state of
      Monitoring -> case observationFingerprint observation of
        Just fingerprint | category == Overloaded && fresh (Just fingerprint) state -> open fingerprint Opened
        _ -> Decision state [] NoIncident
      SuspectedFailure -> beforeSend (\_ _ -> Decision (state {stateMode = ConfirmIdle}) [] Continued)
      ConfirmIdle -> beforeSend (\_ fingerprint -> schedule (stateAttempt state) fingerprint True)
      Backoff -> beforeSend sendWhenDue
      RecoverySent -> Decision (state {stateMode = Verify}) [] Continued
      Verify -> verify
      Escalate -> Decision state [] NoIncident
  where
    category = observationClass observation
    open fingerprint = Decision (state {stateMode = SuspectedFailure, stateIncident = Just (Incident fingerprint now Nothing), stateAttempt = 1}) []
    finish = Decision (state {stateMode = Monitoring, stateIncident = Nothing, stateHandled = maybe (stateHandled state) (\incident -> Set.insert (incidentFingerprint incident) (stateHandled state)) (stateIncident state)}) []
    schedule attempt fingerprint explicit =
      let scheduled = Backoff.retry settings attempt (stateSeed state)
          deadline = now + Backoff.retryDelay scheduled
          actions = WaitUntil deadline scheduled : [Notify (RetryNotice scheduled) | explicit && Backoff.retryNotify scheduled]
       in Decision (state {stateMode = Backoff, stateIncident = Just (Incident fingerprint deadline Nothing), stateAttempt = attempt, stateSeed = Backoff.retrySeed scheduled}) actions Continued
    beforeSend next = case (stateIncident state, observationFingerprint observation) of
      (Just incident, Just fingerprint)
        | category == Overloaded && fresh (Just fingerprint) state ->
            if fingerprint /= incidentFingerprint incident
              then open fingerprint Replaced
              else next incident fingerprint
      _ -> finish Ended
    sendWhenDue incident fingerprint
      | now >= incidentDeadline incident =
          Decision (state {stateMode = RecoverySent, stateHandled = Set.insert fingerprint (stateHandled state), stateIncident = Just (incident {incidentDeadline = now + Backoff.initialDelay settings, sentObservation = Just observation})}) [SendRecovery] Continued
      | otherwise = Decision state [] Continued
    verify = case stateIncident state of
      Nothing -> finish Ended
      Just incident
        | Just observation == sentObservation incident -> awaitAcknowledgement incident
        | category `elem` [Working, IdlePrompt] -> finish Recovered
        | blocking category -> finish Ended
        | category == Overloaded && fresh (observationFingerprint observation) state -> case observationFingerprint observation of
            Just fingerprint -> schedule (stateAttempt state + 1) fingerprint False
            Nothing -> awaitAcknowledgement incident
        | otherwise -> awaitAcknowledgement incident
    awaitAcknowledgement incident
      | now >= incidentDeadline incident = Decision (state {stateMode = Escalate, stateIncident = Nothing, stateHandled = Set.insert (incidentFingerprint incident) (stateHandled state)}) [Notify NotAcknowledgedNotice] NotAcknowledged
      | otherwise = Decision state [] Continued
