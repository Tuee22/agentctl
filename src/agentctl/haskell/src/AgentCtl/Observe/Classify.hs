-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Observe.Classify
  ( ScreenClass (..),
    Classification (..),
    Rules (..),
    classifyWith,
    classText,
    parseClass,
  )
where

import AgentCtl.Observe.Capture (Screen (..))
import AgentCtl.Observe.Classify.Input (logicalInput)
import AgentCtl.Observe.Fingerprint (ErrorBlock (..))
import Data.List (find)
import Data.Text (Text)
import qualified Data.Text as Text

data ScreenClass
  = IdlePrompt
  | Working
  | ApprovalDialog
  | PartialInput
  | TrustDialog
  | BypassWarning
  | LoginScreen
  | Overloaded
  | UsageLimit
  | AuthError
  | ContextExhausted
  | Exited
  | Unknown
  deriving (Eq, Ord, Enum, Bounded, Show)

data Classification = Classification
  { classificationClass :: ScreenClass,
    classificationError :: Maybe ErrorBlock
  }
  deriving (Eq, Show)

data Rules = Rules
  { promptMarker :: Text,
    trustMarkers :: [Text],
    bypassMarkers :: [Text],
    approvalMarkers :: [Text],
    loginMarkers :: [Text],
    overloadMarkers :: [Text],
    usageMarkers :: [Text],
    authMarkers :: [Text],
    contextMarkers :: [Text]
  }
  deriving (Eq, Show)

classText :: ScreenClass -> Text
classText value = case value of
  IdlePrompt -> "IdlePrompt"
  Working -> "Working"
  ApprovalDialog -> "ApprovalDialog"
  PartialInput -> "PartialInput"
  TrustDialog -> "TrustDialog"
  BypassWarning -> "BypassWarning"
  LoginScreen -> "LoginScreen"
  Overloaded -> "Overloaded"
  UsageLimit -> "UsageLimit"
  AuthError -> "AuthError"
  ContextExhausted -> "ContextExhausted"
  Exited -> "Exited"
  Unknown -> "Unknown"

parseClass :: Text -> Maybe ScreenClass
parseClass text = find ((== text) . classText) [minBound .. maxBound]

classifyWith :: Rules -> Screen -> Classification
classifyWith rules screen
  | screenDead screen = result Exited
  | matches (trustMarkers rules) text = result TrustDialog
  | matches (bypassMarkers rules) text && matches ["i accept", "i understand"] text = result BypassWarning
  | matches (approvalMarkers rules) text = result ApprovalDialog
  | matches (loginMarkers rules) text = result LoginScreen
  | otherwise = case currentPrompt (promptMarker rules) screen of
      Just (_, input, _) | not (Text.null input) -> result PartialInput
      _ | matches ["esc to interrupt"] text -> result Working
      Just (before, _, after) -> latestEvent rules before after
      Nothing -> result Unknown
  where
    text = screenText screen

result :: ScreenClass -> Classification
result value = Classification value Nothing

matches :: [Text] -> Text -> Bool
matches markers value = any (`Text.isInfixOf` Text.toCaseFold value) markers

currentPrompt :: Text -> Screen -> Maybe ([Text], Text, [Text])
currentPrompt marker screen = case reverse candidates of
  candidate : _ -> Just candidate
  [] -> Nothing
  where
    linesOfText = Text.lines (screenText screen)
    candidates =
      [ (take index linesOfText, logicalInput marker (Text.strip input) (screenVisual screen), drop (index + 1) linesOfText)
      | (index, line) <- zip [0 ..] linesOfText,
        Just input <- [Text.stripPrefix marker (Text.stripStart line)]
      ]

latestEvent :: Rules -> [Text] -> [Text] -> Classification
latestEvent rules before after = case dropWhile (Text.null . Text.strip) (reverse before) of
  line : preceding -> case errorClass rules line of
    Just value ->
      Classification
        value
        (Just (ErrorBlock (Text.intercalate "\n" (reverse preceding)) line (Text.intercalate "\n" (promptMarker rules : after))))
    Nothing
      | any (`Text.isPrefixOf` Text.toCaseFold (Text.stripStart line)) ["error", "api error", "fatal", "exception"] -> result Unknown
      | otherwise -> result IdlePrompt
  [] -> result IdlePrompt

errorClass :: Rules -> Text -> Maybe ScreenClass
errorClass rules line
  | matches (usageMarkers rules) line = Just UsageLimit
  | matches (authMarkers rules) line = Just AuthError
  | matches (contextMarkers rules) line = Just ContextExhausted
  | matches (overloadMarkers rules) line = Just Overloaded
  | otherwise = Nothing
