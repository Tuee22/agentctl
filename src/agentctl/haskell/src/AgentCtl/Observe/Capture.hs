-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Observe.Capture (Screen (..), Visual (..), validVisual, CaptureError (..), capture) where

import AgentCtl.Mux (Multiplexer)
import AgentCtl.Mux.Command (Command (Capture, CaptureVisual, InspectPane), Pane)
import AgentCtl.Observe.Normalize (normalise, tailLines)
import qualified AgentCtl.Process as Process
import Control.Concurrent (threadDelay)
import Control.Monad.Trans.Class (lift)
import Control.Monad.Trans.Except (ExceptT, runExceptT, throwE)
import Data.Aeson (FromJSON (parseJSON), ToJSON (toJSON), object, withObject, (.:), (.=))
import Data.Text (Text)
import qualified Data.Text as Text
import GHC.Clock (getMonotonicTimeNSec)
import Text.Read (readMaybe)

data Visual = Visual
  { visualCursorX :: Int,
    visualCursorY :: Int,
    visualWidth :: Int,
    visualHeight :: Int,
    visualText :: Text
  }
  deriving (Eq, Show)

validVisual :: Visual -> Bool
validVisual visual = visualWidth visual > 0 && visualHeight visual > 0 && visualCursorX visual >= 0 && visualCursorX visual < visualWidth visual && visualCursorY visual >= 0 && visualCursorY visual < visualHeight visual

instance FromJSON Visual where
  parseJSON = withObject "pane visual facts" $ \fields -> do
    visual <- Visual <$> fields .: "x" <*> fields .: "y" <*> fields .: "width" <*> fields .: "height" <*> fields .: "styled"
    if validVisual visual then pure visual else fail "invalid pane visual geometry"

instance ToJSON Visual where
  toJSON visual = object ["x" .= visualCursorX visual, "y" .= visualCursorY visual, "width" .= visualWidth visual, "height" .= visualHeight visual, "styled" .= visualText visual]

data Screen = Screen
  { screenText :: Text,
    screenDead :: Bool,
    screenVisual :: Maybe Visual
  }
  deriving (Eq, Show)

data CaptureError
  = ProcessFailed Process.ProcessError
  | CommandFailed Int Text
  | InvalidDeadState Text
  | InvalidPaneFacts Text
  deriving (Eq, Show)

data PaneFacts = PaneFacts Bool Int Int Int Int deriving (Eq, Show)

type Effect = ExceptT CaptureError IO

capture :: Multiplexer -> Pane -> Process.CommandContext -> IO (Either CaptureError Screen)
capture mux pane context
  | Process.timeLimitMicros context <= 0 = pure (Left (ProcessFailed Process.InvalidDeadline))
  | otherwise = do
      began <- toInteger <$> getMonotonicTimeNSec
      runExceptT (poll (began + toInteger (Process.timeLimitMicros context) * 1000))
  where
    query :: Integer -> Command -> Effect Text
    query deadline command = do
      now <- toInteger <$> lift getMonotonicTimeNSec
      if now >= deadline
        then throwE (ProcessFailed Process.TimedOut)
        else do
          let remaining = fromInteger (max 1 ((deadline - now) `div` 1000))
          result <- lift (Process.runCommand mux command (context {Process.timeLimitMicros = remaining}))
          output <- either (throwE . ProcessFailed) pure result
          if Process.exitCode output == 0
            then pure (Process.stdoutText output)
            else throwE (CommandFailed (Process.exitCode output) (Process.stderrText output))
    facts deadline = query deadline (InspectPane pane "#{pane_dead}|#{cursor_x}|#{cursor_y}|#{pane_width}|#{pane_height}") >>= either throwE pure . parseFacts
    poll deadline = do
      before <- facts deadline
      text <- query deadline (Capture pane tailLines)
      styled <- query deadline (CaptureVisual pane)
      after <- facts deadline
      if before == after
        then case after of
          PaneFacts dead x y width height -> pure (Screen (normalise text) dead (Just (Visual x y width height styled)))
        else lift (threadDelay 1000) >> poll deadline

parseFacts :: Text -> Either CaptureError PaneFacts
parseFacts supplied = case Text.splitOn "|" (Text.strip supplied) of
  [dead, x, y, width, height] -> do
    ended <- case dead of
      "0" -> Right False
      "1" -> Right True
      _ -> Left (InvalidDeadState dead)
    case traverse (readMaybe . Text.unpack) [x, y, width, height] of
      Just [column, row, columns, rows]
        | validVisual (Visual column row columns rows "") -> Right (PaneFacts ended column row columns rows)
      _ -> Left (InvalidPaneFacts supplied)
  _ -> Left (InvalidPaneFacts supplied)
