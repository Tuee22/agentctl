-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Supervisor.Settings (Settings, Values, parser, validate, parseArguments, pollSeconds, backoffPolicy) where

import qualified AgentCtl.Recovery.Backoff as Backoff
import Data.Aeson (ToJSON (toJSON), object, (.=))
import Data.Text (Text)
import qualified Options.Applicative as Options

data Values = Values Double Double Double Double Double deriving (Eq, Show)

data Settings = Settings Values Backoff.Policy deriving (Eq, Show)

pollSeconds :: Settings -> Double
pollSeconds (Settings (Values poll _ _ _ _) _) = poll

backoffPolicy :: Settings -> Backoff.Policy
backoffPolicy (Settings _ policy) = policy

instance ToJSON Settings where
  toJSON (Settings (Values poll initial maximumWait growth jitter) _) =
    object ["poll" .= poll, "initial" .= initial, "maximum" .= maximumWait, "multiplier" .= growth, "jitter" .= jitter]

parser :: Options.Parser Values
parser =
  Values
    <$> number "poll-seconds" 5 "Seconds between target polls."
    <*> number "initial-delay-seconds" 30 "Initial recovery backoff in seconds."
    <*> number "max-delay-seconds" 900 "Maximum recovery backoff in seconds."
    <*> number "multiplier" 2 "Exponential backoff multiplier."
    <*> number "jitter-fraction" 0.2 "Backoff jitter fraction."
  where
    number name initial description = Options.option Options.auto (Options.long name <> Options.value initial <> Options.showDefault <> Options.metavar "NUMBER" <> Options.help description)

validate :: Values -> Either Text Settings
validate values@(Values poll initial maximumWait growth jitter)
  | isNaN poll || isInfinite poll || poll <= 0 = Left "poll seconds must be finite and positive"
  | otherwise = Settings values <$> Backoff.policy initial growth maximumWait jitter

parseArguments :: [String] -> Either Text Settings
parseArguments arguments = case Options.execParserPure Options.defaultPrefs (Options.info parser mempty) arguments of
  Options.Success values -> validate values
  Options.Failure _ -> Left "invalid supervisor timing options"
  Options.CompletionInvoked _ -> Left "invalid supervisor timing options"
