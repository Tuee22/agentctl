-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Mux.Command
  ( Command (..),
    Pane,
    paneText,
    paneId,
    paneSession,
    inSession,
    selectPane,
    makePane,
    Option (..),
    optionName,
    OptionValue,
    makeOptionValue,
    optionValueText,
    Rendered (..),
    parseCommand,
    deadStatus,
    needsReap,
    ownsProcessTree,
  )
where

import AgentCtl.Mux.Types (Kind (..))
import AgentCtl.Session.Name (SessionName, makeSessionName, sessionNameText)
import Data.Aeson (Value, withObject, (.:))
import Data.Aeson.Types (Parser)
import Data.Char (isAlphaNum, isAscii, isControl, isDigit)
import Data.Maybe (fromMaybe, isNothing)
import Data.Text (Text)
import qualified Data.Text as Text

newtype Pane = Pane Text deriving (Eq, Show)

paneText :: Pane -> Text
paneText (Pane value) = value

paneId :: Pane -> Text
paneId (Pane value) =
  let raw = snd (Text.breakOnEnd ":" value)
   in fromMaybe raw (Text.stripPrefix "." raw)

paneSession :: Pane -> Maybe Text
paneSession (Pane value) = case Text.breakOn ":" value of
  (name, suffix) | not (Text.null suffix) -> Just (Text.drop 1 name)
  _ -> Nothing

inSession :: Kind -> SessionName -> Pane -> Pane
inSession Psmux name pane = Pane ("=" <> sessionNameText name <> ":." <> paneId pane)
inSession Tmux _ pane = pane

selectPane :: [Pane] -> Either Text (Maybe Pane)
selectPane [] = Right Nothing
selectPane [pane] = Right (Just pane)
selectPane _ = Left "ambiguous pane id; use SESSION:%id"

makePane :: Text -> Maybe Pane
makePane value = case Text.breakOn ":" value of
  (prefix, suffix)
    | not (Text.null suffix) ->
        let name = fromMaybe prefix (Text.stripPrefix "=" prefix)
            raw = Text.drop 1 suffix
            identifier = fromMaybe raw (Text.stripPrefix "." raw)
         in if not (Text.null name) && Text.all (\character -> character /= ':' && not (isControl character)) name && bare identifier
              then Just (Pane ("=" <> name <> ":." <> identifier))
              else Nothing
  _ -> if bare value then Just (Pane value) else Nothing
  where
    bare raw = case Text.uncons raw of
      Just ('%', rest) -> not (Text.null rest) && Text.all (\character -> isAscii character && isDigit character) rest
      _ -> False

data Option = Owner | Agent | Folder | AgentPane | StatusFile deriving (Eq, Show)

optionName :: Option -> String
optionName Owner = "@agentctl_owner"
optionName Agent = "@agentctl_agent"
optionName Folder = "@agentctl_folder"
optionName AgentPane = "@agentctl_pane"
optionName StatusFile = "@agentctl_status"

newtype OptionValue = OptionValue Text deriving (Eq, Show)

optionValueText :: OptionValue -> Text
optionValueText (OptionValue value) = value

makeOptionValue :: Text -> Maybe OptionValue
makeOptionValue value
  | not (Text.null value) && Text.all safeOption value = Just (OptionValue value)
  | otherwise = Nothing

data Command
  = Create SessionName FilePath FilePath
  | HasSession SessionName
  | ListSessions Text
  | ShowOptions SessionName
  | ListPanes SessionName Text
  | PaneState Pane
  | InspectPane Pane Text
  | SetIdentity SessionName Option OptionValue
  | RemainOnExit SessionName Pane Bool
  | Capture Pane Int
  | CaptureVisual Pane
  | SendLiteral Pane Text
  | SendEnter Pane
  | Attach SessionName
  | Switch SessionName
  | Kill SessionName
  deriving (Eq, Show)

data Rendered = Rendered
  { executable :: FilePath,
    arguments :: [String]
  }
  deriving (Eq, Show)

parseCommand :: Value -> Parser Command
parseCommand = withObject "multiplexer action" $ \fields -> do
  action <- fields .: "action"
  let session = fields .: "session" >>= either (fail . show) pure . makeSessionName
      pane = fields .: "pane" >>= maybe (fail "invalid pane id") pure . makePane
  case (action :: Text) of
    "create" -> Create <$> session <*> fields .: "binary" <*> fields .: "spec"
    "has-session" -> HasSession <$> session
    "list-sessions" -> ListSessions <$> fields .: "format"
    "show-options" -> ShowOptions <$> session
    "list-panes" -> ListPanes <$> session <*> fields .: "format"
    "pane-state" -> PaneState <$> pane
    "inspect-pane" -> InspectPane <$> pane <*> fields .: "format"
    "set-identity" -> do
      key <- fields .: "key" >>= parseOption
      value <- fields .: "value" >>= maybe (fail "invalid identity option value") pure . makeOptionValue
      SetIdentity <$> session <*> pure key <*> pure value
    "remain-on-exit" -> RemainOnExit <$> session <*> pane <*> fields .: "enabled"
    "capture" -> do
      count <- fields .: "lines"
      if count > 0 then Capture <$> pane <*> pure count else fail "invalid capture length"
    "capture-visual" -> CaptureVisual <$> pane
    "send-literal" -> SendLiteral <$> pane <*> fields .: "text"
    "send-enter" -> SendEnter <$> pane
    "attach" -> Attach <$> session
    "switch" -> Switch <$> session
    "kill" -> Kill <$> session
    _ -> fail "unknown multiplexer action"

safeOption :: Char -> Bool
safeOption character = isAscii character && (isAlphaNum character || character `elem` ("_-%" :: String))

parseOption :: Text -> Parser Option
parseOption value = case value of
  "owner" -> pure Owner
  "agent" -> pure Agent
  "folder" -> pure Folder
  "pane" -> pure AgentPane
  "status-file" -> pure StatusFile
  _ -> fail "unknown identity option"

deadStatus :: Kind -> Maybe Int -> Maybe Int -> Maybe Int -> Maybe Int
deadStatus Tmux status signal _ = case signal of
  Just number | number > 0 -> Just (128 + number)
  _ -> nonnegative status
deadStatus Psmux _ _ status = nonnegative status

nonnegative :: Maybe Int -> Maybe Int
nonnegative (Just number) | number >= 0 = Just number
nonnegative _ = Nothing

needsReap :: Kind -> Bool -> Maybe Int -> Bool
needsReap Tmux dead status = dead && isNothing status
needsReap Psmux _ _ = False

ownsProcessTree :: Kind -> Command -> Bool
ownsProcessTree Psmux Create {} = False
ownsProcessTree _ _ = True
