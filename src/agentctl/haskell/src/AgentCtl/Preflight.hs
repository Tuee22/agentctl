-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Preflight
  ( Ready,
    readyMultiplexer,
    readyAgent,
    readyExecutable,
    readyAuth,
    Failure (..),
    MuxObservation (..),
    AgentObservation (..),
    Decision (..),
    decision,
    preflight,
    preflightWithMux,
    warning,
    multiplexerWarning,
  )
where

import qualified AgentCtl.Agent as Agent
import qualified AgentCtl.Agent.Auth as Auth
import qualified AgentCtl.Mux as Mux
import qualified Data.Text as Text

data Ready = VerifiedReady Mux.Multiplexer Agent.Agent FilePath Auth.AuthState deriving (Eq, Show)

data Failure
  = MultiplexerFailure Mux.MuxError
  | AgentFailure Agent.ResolutionError
  | AuthenticationFailure Auth.ProbeOutcome
  deriving (Eq, Show)

data MuxObservation = MuxMissing | MuxOld | MuxReady deriving (Eq, Show)

data AgentObservation = AgentMissing | AgentShim | AgentPresent deriving (Eq, Show)

data Decision = Decision [Text.Text] Text.Text Int deriving (Eq, Show)

data Program
  = NeedMux (Mux.Multiplexer -> Program)
  | NeedAgent (FilePath -> Program)
  | NeedAuth FilePath (Auth.ProbeOutcome -> Program)
  | Finished (Either Failure Ready)

readyMultiplexer :: Ready -> Mux.Multiplexer
readyMultiplexer (VerifiedReady mux _ _ _) = mux

readyAgent :: Ready -> Agent.Agent
readyAgent (VerifiedReady _ agent _ _) = agent

readyExecutable :: Ready -> FilePath
readyExecutable (VerifiedReady _ _ path _) = path

readyAuth :: Ready -> Auth.AuthState
readyAuth (VerifiedReady _ _ _ state) = state

authAllowed :: Auth.AuthState -> Bool
authAllowed Auth.LoggedIn = True
authAllowed Auth.LoggedOut = False
authAllowed Auth.CheckFailed = False

decision :: MuxObservation -> AgentObservation -> Auth.AuthState -> Decision
decision mux agent auth = case mux of
  MuxMissing -> Decision ["mux"] "MuxMissing" 3
  MuxOld -> Decision ["mux"] "MuxOld" 4
  MuxReady -> case agent of
    AgentMissing -> Decision ["mux", "agent"] "AgentMissing" 5
    AgentShim -> Decision ["mux", "agent"] "NativeRequired" 6
    AgentPresent
      | authAllowed auth -> Decision ["mux", "agent", "auth"] "Ready" 0
      | auth == Auth.LoggedOut -> Decision ["mux", "agent", "auth"] "LoggedOut" 7
      | otherwise -> Decision ["mux", "agent", "auth"] "AuthFailed" 8

program :: Agent.Agent -> Program
program agent =
  NeedMux $ \mux ->
    NeedAgent $ \path ->
      NeedAuth path $ \outcome ->
        finish mux path outcome
  where
    finish mux path outcome
      | authAllowed (Auth.classifyAuth outcome) = Finished (Right (VerifiedReady mux agent path (Auth.classifyAuth outcome)))
      | otherwise = Finished (Left (AuthenticationFailure outcome))

preflight :: Mux.Family -> Text.Text -> Agent.Agent -> FilePath -> [(String, String)] -> IO (Either Failure Ready)
preflight = preflightUsing Nothing

preflightWithMux :: Mux.Multiplexer -> Mux.Family -> Text.Text -> Agent.Agent -> FilePath -> [(String, String)] -> IO (Either Failure Ready)
preflightWithMux mux = preflightUsing (Just mux)

preflightUsing :: Maybe Mux.Multiplexer -> Mux.Family -> Text.Text -> Agent.Agent -> FilePath -> [(String, String)] -> IO (Either Failure Ready)
preflightUsing knownMux family distribution agent cwd environment = interpret (program agent)
  where
    interpret (NeedMux next) = do
      result <- maybe (Mux.resolve family distribution cwd environment) (pure . Right) knownMux
      either (pure . Left . MultiplexerFailure) (interpret . next) result
    interpret (NeedAgent next) = do
      result <- Agent.resolveAgent family agent cwd environment
      either (pure . Left . AgentFailure) (interpret . next) result
    interpret (NeedAuth path next) = do
      outcome <- Auth.probe (Agent.table family agent) path cwd environment 10000000
      interpret (next outcome)
    interpret (Finished result) = pure result

warning :: Mux.Family -> Text.Text -> Agent.Agent -> Failure -> (Int, [Text.Text])
warning family distribution agent failure = case failure of
  AuthenticationFailure outcome -> Auth.warning agent outcome
  AgentFailure Agent.AgentMissing -> (5, ["agentctl: " <> name <> " was not found on PATH.", agentHint])
  AgentFailure (Agent.NativeRequired path) ->
    (6, ["agentctl: " <> name <> " resolves only to " <> Text.pack path <> "; agentctl starts only a native " <> name <> ".exe.", agentHint])
  AgentFailure (Agent.InvalidSearchDirectory _) -> (5, ["agentctl: the agent search requires an absolute working directory.", agentHint])
  AgentFailure (Agent.AgentDiscoveryFailed _) -> (5, ["agentctl: could not inspect PATH for " <> name <> ".", agentHint])
  MultiplexerFailure muxFailure -> multiplexerWarning family distribution muxFailure
  where
    name = Agent.agentText agent
    agentHint = install (Agent.installHint (Agent.table family agent))

multiplexerWarning :: Mux.Family -> Text.Text -> Mux.MuxError -> (Int, [Text.Text])
multiplexerWarning family distribution failure = case failure of
  Mux.Unavailable _ hint ->
    (3, ["agentctl: " <> muxName <> " " <> floorVersion <> " or later is required, and none was found on PATH.", install hint])
  Mux.VersionRejected path (Mux.BelowFloor raw _) hint ->
    (4, ["agentctl: " <> raw <> " at " <> Text.pack path <> " is older than " <> floorVersion <> ", the oldest version agentctl supports.", install hint])
  Mux.VersionRejected path (Mux.MalformedVersion raw) hint ->
    (4, ["agentctl: unrecognised " <> muxName <> " version at " <> Text.pack path <> ": " <> Text.pack (show raw), install hint])
  Mux.ProbeFailed _ hint -> (3, ["agentctl: could not check the multiplexer version.", install hint])
  Mux.ProbeExit path code _ hint ->
    (3, ["agentctl: the multiplexer version check at " <> Text.pack path <> " exited " <> Text.pack (show code) <> ".", install hint])
  Mux.DiscoveryFailed _ ->
    (3, ["agentctl: could not inspect PATH for the multiplexer.", install (Mux.remedy family distribution)])
  where
    muxName = if family == Mux.Windows then "psmux" else "tmux"
    floorVersion = if family == Mux.Windows then "3.4.0" else "3.2"

install :: Text.Text -> Text.Text
install hint = "agentctl: install it with: " <> hint
