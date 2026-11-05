-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Agent.Auth
  ( AuthState (..),
    ProbeOutcome (..),
    classifyAuth,
    probe,
    warning,
  )
where

import AgentCtl.Agent (Agent, Entry (..), agentText, table)
import AgentCtl.Mux (Family (Linux))
import qualified AgentCtl.Process as Process
import Data.Aeson (FromJSON (parseJSON), Value (String))
import qualified Data.Text as Text

data ProbeOutcome = Exited Int | Signalled | ProbeTimeout | ProbeUnavailable deriving (Eq, Show)

data AuthState = LoggedIn | LoggedOut | CheckFailed deriving (Eq, Show)

instance FromJSON ProbeOutcome where
  parseJSON (String "signal") = pure Signalled
  parseJSON (String "timeout") = pure ProbeTimeout
  parseJSON (String "spawn-error") = pure ProbeUnavailable
  parseJSON value = Exited <$> parseJSON value

classifyAuth :: ProbeOutcome -> AuthState
classifyAuth (Exited 0) = LoggedIn
classifyAuth (Exited 1) = LoggedOut
classifyAuth (Exited _) = CheckFailed
classifyAuth Signalled = CheckFailed
classifyAuth ProbeTimeout = CheckFailed
classifyAuth ProbeUnavailable = CheckFailed

probe :: Entry -> FilePath -> FilePath -> [(String, String)] -> Int -> IO ProbeOutcome
probe entry executable directory environment deadline = do
  result <- Process.runStatus (probeInvocation entry executable directory environment deadline)
  pure $ case result of
    Right code | code < 0 -> Signalled
    Right code -> Exited code
    Left Process.TimedOut -> ProbeTimeout
    Left _ -> ProbeUnavailable

probeInvocation :: Entry -> FilePath -> FilePath -> [(String, String)] -> Int -> Process.Invocation
probeInvocation entry executable = Process.Invocation executable (authArguments entry)

warning :: Agent -> ProbeOutcome -> (Int, [Text.Text])
warning agent outcome = case classifyAuth outcome of
  LoggedIn -> (0, [])
  LoggedOut ->
    ( 7,
      [ "agentctl: " <> name <> " is not logged in, so no session was started.",
        "agentctl: log in yourself by typing: " <> loginRemedy entry
      ]
    )
  CheckFailed ->
    ( 8,
      [ "agentctl: could not tell whether " <> name <> " is logged in: `" <> name <> " " <> Text.unwords (map Text.pack (authArguments entry)) <> "` " <> detail outcome <> ".",
        "agentctl: run it yourself to see why; no session was started."
      ]
    )
  where
    name = agentText agent
    entry = table Linux agent
    detail (Exited code) = "exited " <> Text.pack (show code)
    detail Signalled = "was terminated by a signal"
    detail ProbeTimeout = "timed out"
    detail ProbeUnavailable = "could not be run"
