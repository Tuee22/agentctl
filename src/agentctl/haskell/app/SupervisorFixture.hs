-- Copyright (c) 2026 agentctl contributors.
module SupervisorFixture (beforeClient) where

import AgentCtl.Native (processId)
import Control.Concurrent (threadDelay)
import Control.Monad (unless, when)
import Data.Aeson (FromJSON (parseJSON), ToJSON (toJSON), eitherDecodeStrict', encode, object, withObject, (.!=), (.:), (.:?), (.=))
import qualified Data.Aeson.KeyMap as Keys
import qualified Data.ByteString as Bytes
import qualified Data.ByteString.Lazy as Lazy
import Data.List (sort)
import qualified Data.Text as Text
import qualified Data.Text.IO as Text
import GHC.Clock (getMonotonicTimeNSec)
import System.Directory (doesFileExist, renameFile)
import System.Environment (getEnv, lookupEnv)
import System.Exit (die)
import System.FilePath (isAbsolute, takeDirectory, (</>))
import System.IO (hClose, hSetBinaryMode)
import System.IO.Temp (withTempFile)

data Mode = Guard | Fail deriving (Eq)

data Barrier = Barrier Mode String Text.Text Int Int

instance FromJSON Barrier where
  parseJSON = withObject "supervisor barrier" $ \fields -> do
    unless (sort (Keys.keys fields) == ["generation", "mode", "offset", "pane", "target"]) (fail "invalid supervisor barrier fields")
    kind <- fields .: "mode"
    mode <- case (kind :: Text.Text) of
      "guard" -> pure Guard
      "fail" -> pure Fail
      _ -> fail "invalid supervisor barrier mode"
    offset <- fields .: "offset"
    generation <- fields .: "generation"
    when (offset < 0 || generation < 0) (fail "negative supervisor barrier position")
    Barrier mode <$> fields .: "pane" <*> fields .: "target" <*> pure offset <*> pure generation

instance ToJSON Barrier where
  toJSON (Barrier mode pane target offset generation) =
    object ["mode" .= (if mode == Guard then "guard" else "fail" :: Text.Text), "pane" .= pane, "target" .= target, "offset" .= offset, "generation" .= generation]

data Entry = Entry Text.Text Text.Text [Text.Text]

instance FromJSON Entry where
  parseJSON = withObject "observed decision record" $ \fields ->
    Entry <$> fields .: "kind" <*> fields .: "target" <*> (fields .:? "actions" .!= [])

beforeClient :: String -> [String] -> IO Bool
beforeClient nonce arguments = do
  configured <- lookupEnv "AGENTCTL_FAKE_SUPERVISOR_BARRIER"
  case configured of
    Nothing -> pure True
    Just path -> do
      unless (isAbsolute path) (die "supervisor barrier path must be absolute")
      armed <- doesFileExist path
      if not armed
        then pure True
        else do
          barrier@(Barrier mode pane target offset generation) <- Bytes.readFile path >>= either die pure . eitherDecodeStrict'
          if not (matches mode pane arguments)
            then pure True
            else do
              state <- getEnv "AGENTCTL_STATE_DIR"
              history <- Bytes.readFile (state </> "supervisor.jsonl")
              when (offset > Bytes.length history) (die "supervisor history was truncated")
              let complete = fst (Bytes.breakEnd (== 10) (Bytes.drop offset history))
              entries <- traverse (either die pure . eitherDecodeStrict') (filter (not . Bytes.null) (Bytes.split 10 complete))
              if mode == Guard && any (completed target) entries
                then publish path (Barrier mode pane target (Bytes.length history) generation) >> pure True
                else
                  if any (proposed target) entries
                    then intercept path barrier history nonce
                    else pure True
  where
    proposed target (Entry kind selected actions) = kind == "decision" && selected == target && "send" `elem` actions
    completed target (Entry kind selected _) = kind == "attempt" && selected == target
    matches Guard pane argv = argv == ["display-message", "-p", "-t", pane, "#{pane_dead}|#{cursor_x}|#{cursor_y}|#{pane_width}|#{pane_height}"]
    matches Fail pane argv = case argv of
      "send-keys" : "-l" : "-t" : selected : "--" : _ -> selected == pane
      _ -> False

intercept :: FilePath -> Barrier -> Bytes.ByteString -> String -> IO Bool
intercept path (Barrier mode pane target _ generation) history nonce = do
  let directory = takeDirectory path
      blocked = directory </> ("blocked-" ++ show generation ++ ".json")
      release = directory </> ("release-" ++ show generation)
  publish path (Barrier mode pane target (Bytes.length history) (generation + 1))
  pid <- processId
  publish blocked (object ["nonce" .= nonce, "pid" .= pid, "pane" .= pane, "target" .= target, "mode" .= (if mode == Guard then "guard" else "fail" :: Text.Text)])
  if mode == Fail
    then pure False
    else do
      began <- getMonotonicTimeNSec
      let awaitRelease = do
            ready <- doesFileExist release
            if ready
              then Text.readFile release >>= \value -> unless (value == Text.pack nonce) (die "wrong supervisor barrier release nonce")
              else do
                now <- getMonotonicTimeNSec
                when (now - began >= 10000000000) (die "supervisor barrier release timed out")
                threadDelay 10000
                awaitRelease
      awaitRelease
      pure True

publish :: (ToJSON value) => FilePath -> value -> IO ()
publish destination value = withTempFile (takeDirectory destination) "supervisor-event-" $ \temporary handle -> do
  hSetBinaryMode handle True
  Lazy.hPut handle (encode value)
  hClose handle
  renameFile temporary destination
