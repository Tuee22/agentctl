-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Mux
  ( Family (..),
    Kind (..),
    Multiplexer,
    MuxError (..),
    VersionError (..),
    familyFromText,
    hostFamily,
    candidates,
    remedy,
    checkVersion,
    resolve,
    muxExecutable,
    muxKind,
    muxVersion,
  )
where

import AgentCtl.Mux.Types (Family (..), Kind (..), Multiplexer (..), muxExecutable, muxKind, muxVersion)
import qualified AgentCtl.Process as Process
import Control.Exception (IOException, catch)
import Data.Char (isAsciiLower, isDigit)
import Data.Text (Text)
import qualified Data.Text as Text
import System.Directory (canonicalizePath, executable, findFilesWith, getPermissions)
import System.FilePath (isAbsolute, normalise, splitSearchPath, (</>))
import qualified System.Info as System
import Text.Read (readMaybe)

type Version = (Integer, Integer, Integer)

data VersionError = MalformedVersion Text | BelowFloor Text Version deriving (Eq, Show)

data MuxError
  = Unavailable Kind Text
  | VersionRejected FilePath VersionError Text
  | ProbeFailed Process.ProcessError Text
  | ProbeExit FilePath Int Text Text
  | DiscoveryFailed Text
  deriving (Eq, Show)

familyFromText :: Text -> Maybe Family
familyFromText "Linux" = Just Linux
familyFromText "Darwin" = Just Darwin
familyFromText "Windows" = Just Windows
familyFromText _ = Nothing

hostFamily :: Maybe Family
hostFamily = case System.os of
  "linux" -> Just Linux
  "darwin" -> Just Darwin
  "mingw32" -> Just Windows
  _ -> Nothing

candidates :: Family -> [FilePath]
candidates Windows = ["psmux.exe"]
candidates _ = ["tmux"]

remedy :: Family -> Text -> Text
remedy Darwin _ = "brew install tmux"
remedy Windows _ = "winget install psmux"
remedy Linux distribution
  | distribution `elem` ["debian", "ubuntu"] = "sudo apt install tmux"
  | distribution `elem` ["fedora", "rhel", "centos", "rocky", "almalinux"] = "sudo dnf install tmux"
  | distribution `elem` ["arch", "manjaro"] = "sudo pacman -S tmux"
  | otherwise = "Install tmux 3.2 or later with your OS package manager"

checkVersion :: Kind -> Text -> Either VersionError Version
checkVersion kind raw = case parseVersion kind (Text.words raw) of
  Nothing -> Left (MalformedVersion raw)
  Just version
    | version >= floorVersion kind -> Right version
    | otherwise -> Left (BelowFloor raw (floorVersion kind))

floorVersion :: Kind -> Version
floorVersion Tmux = (3, 2, 0)
floorVersion Psmux = (3, 4, 0)

parseVersion :: Kind -> [Text] -> Maybe Version
parseVersion Tmux ["tmux", release] = case Text.splitOn "." release of
  [major, minorAndSuffix] -> do
    let (minor, suffix) = Text.span isDigit minorAndSuffix
    if validSuffix suffix
      then (,,) <$> decimal major <*> decimal minor <*> pure 0
      else Nothing
  _ -> Nothing
parseVersion Psmux ("psmux" : release : metadata)
  | null metadata || validMetadata (Text.unwords metadata) = case Text.splitOn "." release of
      [major, minor, patch] -> (,,) <$> decimal major <*> decimal minor <*> decimal patch
      _ -> Nothing
parseVersion _ _ = Nothing

validSuffix :: Text -> Bool
validSuffix suffix = Text.null suffix || (Text.length suffix == 1 && Text.all isAsciiLower suffix)

validMetadata :: Text -> Bool
validMetadata value = "(" `Text.isPrefixOf` value && ")" `Text.isSuffixOf` value

decimal :: Text -> Maybe Integer
decimal value
  | not (Text.null value) && Text.all isDigit value = readMaybe (Text.unpack value)
  | otherwise = Nothing

resolve :: Family -> Text -> FilePath -> [(String, String)] -> IO (Either MuxError Multiplexer)
resolve family distribution directory environment = discover `catch` refused
  where
    refused :: IOException -> IO (Either MuxError Multiplexer)
    refused exception = pure (Left (DiscoveryFailed (Text.pack (show exception))))
    kind = if family == Windows then Psmux else Tmux
    instruction = remedy family distribution
    search = maybe [] splitSearchPath (lookupPath environment)
    paths = map (\path -> normalise (if isAbsolute path then path else directory </> path)) search
    lookupPath values =
      lookup "PATH" $
        if family == Windows
          then [(Text.unpack (Text.toUpper (Text.pack key)), value) | (key, value) <- values]
          else values
    discover = do
      found <- concat <$> mapM (findFilesWith isExecutable paths) (candidates family)
      case found of
        [] -> pure (Left (Unavailable kind instruction))
        first : _ -> do
          path <- canonicalizePath first
          result <- Process.run (Process.Invocation path ["-V"] directory environment 10000000)
          pure $ case result of
            Left failure -> Left (ProbeFailed failure instruction)
            Right output
              | Process.exitCode output /= 0 -> Left (ProbeExit path (Process.exitCode output) (Process.stderrText output) instruction)
              | otherwise -> case checkVersion kind (Process.stdoutText output) of
                  Left failure -> Left (VersionRejected path failure instruction)
                  Right _ -> Right (Multiplexer kind path (Text.strip (Process.stdoutText output)))
    isExecutable path = executable <$> getPermissions path
