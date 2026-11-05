-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Supervisor.Log
  ( Context (..),
    Record,
    recordTarget,
    Delivery (..),
    parseDelivery,
    parseOutcome,
    parseLevel,
    pollRecords,
    attemptRecord,
    resultRecord,
    notifyRecord,
    Selection,
    select,
    selectedRecords,
    selectionExit,
    selectionMessage,
    decode,
  )
where

import qualified AgentCtl.Agent as Agent
import qualified AgentCtl.Mux as Mux
import qualified AgentCtl.Mux.Command as Command
import qualified AgentCtl.Observe.Classify as Classify
import qualified AgentCtl.Recovery.Machine as Machine
import qualified AgentCtl.Session.Name as Name
import qualified AgentCtl.Supervisor.Poll as Poll
import Control.Monad (unless, when)
import Data.Aeson (FromJSON (parseJSON), Object, ToJSON (toJSON), eitherDecodeStrict', object, withObject, (.:), (.=))
import qualified Data.Aeson.Key as Key
import qualified Data.Aeson.KeyMap as Keys
import Data.Aeson.Types (Pair, Parser)
import Data.Char (isControl)
import Data.Either (isRight)
import Data.List (sort)
import Data.Maybe (fromMaybe, isJust, isNothing)
import Data.Text (Text)
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Text
import Data.Time (UTCTime)

data Context = Context
  { contextTime :: UTCTime,
    contextRun :: Text,
    contextTarget :: Text,
    contextAgent :: Maybe Agent.Agent
  }
  deriving (Eq, Show)

instance FromJSON Context where
  parseJSON = withObject "log context" $ \fields -> do
    checkFields ["time", "run", "target", "agent"] fields
    parseContext fields

parseContext :: Object -> Parser Context
parseContext fields = do
  time <- fields .: "time"
  run <- fields .: "run"
  target <- fields .: "target"
  agentText <- fields .: "agent"
  agent <- if agentText == "unknown" then pure Nothing else Just <$> maybe (fail "unknown log agent") pure (Agent.agentFromText agentText)
  unless (not (Text.null run) && not (Text.any isControl run)) (fail "invalid log run id")
  unless (isJust (Command.makePane target) || isRight (Name.makeSessionName target)) (fail "invalid log target")
  pure (Context time run target agent)

data Label = Wait | Send | Notify deriving (Eq, Show)

label :: Machine.Action -> Label
label action = case action of
  Machine.WaitUntil _ _ -> Wait
  Machine.SendRecovery -> Send
  Machine.Notify _ -> Notify

labelText :: Label -> Text
labelText value = case value of
  Wait -> "wait"
  Send -> "send"
  Notify -> "notify"

parseLabel :: Text -> Parser Label
parseLabel value = case value of
  "wait" -> pure Wait
  "send" -> pure Send
  "notify" -> pure Notify
  _ -> fail "unknown log action"

data Delivery = Sent | Aborted | Failed deriving (Eq, Show)

deliveryText :: Delivery -> Text
deliveryText delivery = case delivery of
  Sent -> "sent"
  Aborted -> "aborted"
  Failed -> "failed"

parseDelivery :: Text -> Maybe Delivery
parseDelivery value = case value of
  "sent" -> Just Sent
  "aborted" -> Just Aborted
  "failed" -> Just Failed
  _ -> Nothing

parseOutcome :: Text -> Maybe Poll.Outcome
parseOutcome value = case value of
  "recovered" -> Just Poll.Recovered
  "ended" -> Just Poll.Ended
  "not-acknowledged" -> Just Poll.NotAcknowledged
  "unresolved" -> Just Poll.Unresolved
  "escalated" -> Just Poll.Escalated
  _ -> Nothing

parseLevel :: Text -> Maybe Poll.Level
parseLevel value = case value of
  "info" -> Just Poll.Info
  "warning" -> Just Poll.Warning
  "error" -> Just Poll.Error
  _ -> Nothing

data Payload
  = Observed Classify.ScreenClass Text Machine.Mode
  | Decided Machine.Mode Machine.Mode Text [Label]
  | Attempted Text Classify.ScreenClass Text Delivery
  | Resolved Poll.Outcome
  | Notified Poll.Level Text
  deriving (Eq, Show)

data Record = Record Context Payload deriving (Eq, Show)

recordTarget :: Record -> Text
recordTarget (Record context _) = contextTarget context

payloadFields :: Payload -> [Pair]
payloadFields payload = case payload of
  Observed category fingerprint mode -> ["kind" .= ("observation" :: Text), "class" .= Classify.classText category, "fingerprint" .= fingerprint, "state" .= Machine.modeText mode]
  Decided before after rule actions -> ["kind" .= ("decision" :: Text), "from" .= Machine.modeText before, "to" .= Machine.modeText after, "rule" .= rule, "actions" .= map labelText actions]
  Attempted text category fingerprint outcome -> ["kind" .= ("attempt" :: Text), "recovery_text" .= text, "pre_send_class" .= Classify.classText category, "pre_send_fingerprint" .= fingerprint, "outcome" .= deliveryText outcome]
  Resolved outcome -> ["kind" .= ("result" :: Text), "outcome" .= Poll.outcomeText outcome]
  Notified level message -> ["kind" .= ("notify" :: Text), "level" .= Poll.levelText level, "message" .= message]

instance ToJSON Record where
  toJSON (Record context payload) =
    object (["time" .= contextTime context, "run" .= contextRun context, "target" .= contextTarget context, "agent" .= maybe "unknown" Agent.agentText (contextAgent context)] ++ payloadFields payload)

makeRecord :: Context -> Payload -> Either Text Record
makeRecord context payload =
  if isNothing (contextAgent context) && requiresAgent
    then Left "unknown agent is only valid for notifications"
    else Right (Record context payload)
  where
    requiresAgent = case payload of
      Observed {} -> True
      Decided {} -> True
      Attempted {} -> True
      Resolved _ -> True
      Notified _ _ -> False

instance FromJSON Record where
  parseJSON = withObject "decision log record" $ \fields -> do
    context <- parseContext fields
    kind <- fields .: "kind"
    let extra names = checkFields (["time", "run", "target", "agent", "kind"] ++ names) fields
        category key = fields .: key >>= maybe (fail "unknown screen class") pure . Classify.parseClass
        mode key = fields .: key >>= maybe (fail "unknown machine state") pure . Machine.parseMode
    payload <- case (kind :: Text) of
      "observation" -> do
        extra ["class", "fingerprint", "state"]
        Observed <$> category "class" <*> fields .: "fingerprint" <*> mode "state"
      "decision" -> do
        extra ["from", "to", "rule", "actions"]
        Decided <$> mode "from" <*> mode "to" <*> fields .: "rule" <*> (fields .: "actions" >>= mapM parseLabel)
      "attempt" -> do
        extra ["recovery_text", "pre_send_class", "pre_send_fingerprint", "outcome"]
        Attempted <$> fields .: "recovery_text" <*> category "pre_send_class" <*> fields .: "pre_send_fingerprint" <*> (fields .: "outcome" >>= maybe (fail "unknown attempt outcome") pure . parseDelivery)
      "result" -> do
        extra ["outcome"]
        Resolved <$> (fields .: "outcome" >>= maybe (fail "unknown result outcome") pure . parseOutcome)
      "notify" -> do
        extra ["level", "message"]
        Notified <$> (fields .: "level" >>= maybe (fail "unknown notification level") pure . parseLevel) <*> fields .: "message"
      _ -> fail "unknown record kind"
    either (fail . Text.unpack) pure (makeRecord context payload)

checkFields :: [Key.Key] -> Object -> Parser ()
checkFields expected fields = unless (sort (Keys.keys fields) == sort expected) (fail "invalid log fields")

pollRecords :: Context -> Poll.Memory Text -> Maybe (Machine.Observation Text) -> Poll.Decision Text -> Either Text [Record]
pollRecords context previous observed decision = do
  observationRecords <- observations
  traverse (makeRecord context) $
    observationRecords
      ++ [Decided before after (Poll.decisionRule decision) (map label (Poll.decisionActions decision))]
      ++ [Notified (Poll.notificationLevel notice) (Poll.notificationMessage notice) | notice <- Poll.decisionNotifications decision, Poll.DecisionLog `elem` Poll.notificationSinks notice]
      ++ map Resolved (Poll.decisionResults decision)
  where
    before = Machine.stateMode (Poll.memoryMachine previous)
    after = Machine.stateMode (Poll.memoryMachine (Poll.decisionMemory decision))
    observations =
      if Poll.decisionCaptured decision
        then case observed of
          Nothing -> Left "captured poll has no observation"
          Just observation -> Right [Observed (Machine.observationClass observation) (fromMaybe "" (Machine.observationFingerprint observation)) before]
        else Right []

attemptRecord :: Context -> Mux.Family -> Machine.Observation Text -> Delivery -> Either Text Record
attemptRecord context family observation outcome = do
  agent <- maybe (Left "unknown agent cannot attempt recovery") Right (contextAgent context)
  makeRecord context (Attempted (Agent.recoveryText (Agent.table family agent)) (Machine.observationClass observation) (fromMaybe "" (Machine.observationFingerprint observation)) outcome)

resultRecord :: Context -> Poll.Outcome -> Either Text Record
resultRecord context = makeRecord context . Resolved

notifyRecord :: Context -> Poll.Level -> Text -> Record
notifyRecord context level message = Record context (Notified level message)

data Selection = Selection Text [Record] deriving (Eq, Show)

select :: Text -> [Record] -> Selection
select wanted records = Selection wanted (filter ((== wanted) . recordTarget) records)

selectedRecords :: Selection -> [Record]
selectedRecords (Selection _ records) = records

selectionExit :: Selection -> Int
selectionExit selection = if null (selectedRecords selection) then 1 else 0

selectionMessage :: Selection -> Text
selectionMessage selection@(Selection wanted _) = if null (selectedRecords selection) then "agentctl: no supervisor records for " <> wanted <> "." else ""

instance ToJSON Selection where
  toJSON selection = object ["records" .= selectedRecords selection, "exit" .= selectionExit selection, "message" .= selectionMessage selection]

decode :: Bool -> Text -> Either Text [Record]
decode writerActive text = do
  let (prefix, suffix) = Text.breakOnEnd "\n" text
  when (not writerActive && not (Text.null suffix)) (Left "invalid decision log")
  traverse (either (const (Left "invalid decision log")) Right . eitherDecodeStrict' . Text.encodeUtf8) (Text.lines prefix)
