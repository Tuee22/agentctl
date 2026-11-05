-- Copyright (c) 2026 agentctl contributors.
module Main (main) where

import qualified AgentCtl.Agent as Agent
import qualified AgentCtl.Launch as Launch
import qualified AgentCtl.Mux as Mux
import qualified AgentCtl.Mux.Command as Command
import qualified AgentCtl.PaneExec as PaneExec
import qualified AgentCtl.Paths as Paths
import AgentCtl.Protocol (commandList, handshake, validHandoff)
import qualified AgentCtl.Sessions as Sessions
import qualified AgentCtl.Supervisor as Supervisor
import qualified AgentCtl.Supervisor.Log as Log
import qualified AgentCtl.Supervisor.Log.File as LogFile
import qualified AgentCtl.Supervisor.Settings as SupervisorSettings
import qualified AgentCtl.Supervisor.Watch as Watch
import Data.Aeson (encode)
import qualified Data.ByteString.Lazy.Char8 as Bytes
import Data.List (isPrefixOf)
import qualified Data.Text as Text
import qualified Data.Text.IO as Text
import qualified Options.Applicative as Options
import System.Directory (getCurrentDirectory)
import System.Environment (getArgs, getEnvironment, getExecutablePath, lookupEnv, withProgName)
import System.Exit (ExitCode (ExitFailure), exitFailure, exitSuccess, exitWith)
import System.IO (hIsTerminalDevice, hPutStrLn, hSetBinaryMode, stderr, stdin, stdout)

data Operation = Session Sessions.Operation | Logs Text.Text | Supervise SupervisorSettings.Values

main :: IO ()
main = do
  supplied <- lookupEnv "AGENTCTL_PROTOCOL_VERSION"
  arguments <- getArgs
  case arguments of
    ["pane-exec", path] -> do
      result <- PaneExec.run path
      case result of
        Left failure -> hPutStrLn stderr ("agentctl pane-exec: " ++ show failure) >> exitFailure
        Right 0 -> exitSuccess
        Right status -> exitWith (ExitFailure status)
    _ | not (validHandoff supplied) -> do
      hPutStrLn stderr "Run agentctl to manage terminal agents."
      exitFailure
    ["--handshake"] -> Bytes.putStrLn (encode handshake)
    name : tailArguments | Just agent <- Agent.agentFromText (Text.pack name) -> launch agent tailArguments
    name : _ | not ("-" `isPrefixOf` name) && name `notElem` commandList -> do
      hPutStrLn stderr "Run agentctl to manage terminal agents."
      exitFailure
    _ -> withProgName "agentctl" $ do
      operation <- Options.execParser (Options.info (Options.helper <*> operationParser) (Options.progDesc "Manage terminal coding agents."))
      case operation of
        Session selected -> sessions selected
        Logs target -> logs target
        Supervise values -> case SupervisorSettings.validate values of
          Left failure -> Text.hPutStrLn stderr ("agentctl: " <> failure) >> exitFailure
          Right settings -> withRequest (`Supervisor.run` settings)

operationParser :: Options.Parser Operation
operationParser =
  Options.hsubparser
    ( sessionCommand "list" (pure Sessions.List) "List managed sessions."
        <> sessionCommand "status" (Sessions.Status <$> Options.optional (Text.pack <$> Options.strArgument (Options.metavar "NAME"))) "Show session status."
        <> sessionCommand "attach" (Sessions.Attach . Text.pack <$> Options.strArgument (Options.metavar "NAME")) "Attach to a managed session."
        <> sessionCommand "stop" (Sessions.Stop . Text.pack <$> Options.strArgument (Options.metavar "NAME")) "Stop a managed session."
        <> sessionCommand "adopt" (Sessions.Adopt <$> Options.argument (Options.eitherReader parsePane) (Options.metavar "PANE") <*> Options.option (Options.eitherReader parseAgent) (Options.long "agent" <> Options.metavar "claude|codex")) "Register an existing pane without taking ownership."
        <> sessionCommand "watch" (watchParser Watch.Watch) "Watch a managed session or adopted pane."
        <> sessionCommand "unwatch" (watchParser Watch.Unwatch) "Remove watch intent without ending the agent."
        <> sessionCommand "pause" (watchParser Watch.Pause) "Pause supervision without ending the agent."
        <> sessionCommand "resume-watch" (watchParser Watch.ResumeWatch) "Resume supervision with a new baseline."
        <> Options.command "logs" (Options.info (Options.helper <*> (Logs . Text.pack <$> Options.strArgument (Options.metavar "NAME|%ID"))) (Options.progDesc "Show one target's supervisor records."))
        <> Options.command "supervisor" (Options.info (Options.helper <*> supervisorParser) (Options.progDesc "Run recovery supervision in the foreground."))
    )

supervisorParser :: Options.Parser Operation
supervisorParser = Options.hsubparser (Options.command "run" (Options.info (Options.helper <*> (Supervise <$> SupervisorSettings.parser)) (Options.progDesc "Watch active targets until interrupted.")))

sessionCommand :: String -> Options.Parser Sessions.Operation -> String -> Options.Mod Options.CommandFields Operation
sessionCommand name parser description = Options.command name (Options.info (Options.helper <*> (Session <$> parser)) (Options.progDesc description))

watchParser :: Watch.Operation -> Options.Parser Sessions.Operation
watchParser operation = Sessions.WatchTarget operation . Text.pack <$> Options.strArgument (Options.metavar "NAME|%ID")

parsePane :: String -> Either String Command.Pane
parsePane = maybe (Left "expected a pane id such as %3") Right . Command.makePane . Text.pack

parseAgent :: String -> Either String Agent.Agent
parseAgent = maybe (Left "expected claude or codex") Right . Agent.agentFromText . Text.pack

logs :: Text.Text -> IO ()
logs target = do
  environment <- getEnvironment
  case Mux.hostFamily >>= \family -> either (const Nothing) Just (Paths.fromEnvironment (family == Mux.Windows) environment) of
    Nothing -> hPutStrLn stderr "agentctl: invalid directory handoff; run agentctl from its Python application." >> exitWith (ExitFailure 2)
    Just paths -> do
      loaded <- LogFile.load paths
      case loaded of
        Left failure -> hPutStrLn stderr ("agentctl: cannot read supervisor log: " ++ show failure) >> exitFailure
        Right records -> do
          let selection = Log.select target records
          hSetBinaryMode stdout True
          mapM_ (Bytes.putStrLn . encode) (Log.selectedRecords selection)
          if Log.selectionExit selection == 0
            then exitSuccess
            else Text.hPutStrLn stderr (Log.selectionMessage selection) >> exitWith (ExitFailure (Log.selectionExit selection))

sessions :: Sessions.Operation -> IO ()
sessions operation = withRequest (`Sessions.run` operation)

withRequest :: (Sessions.Request -> IO Int) -> IO ()
withRequest action = do
  environment <- getEnvironment
  case (Mux.hostFamily, Mux.hostFamily >>= \family -> either (const Nothing) Just (Paths.fromEnvironment (family == Mux.Windows) environment)) of
    (Just family, Just paths) -> do
      directory <- getCurrentDirectory
      inputTerminal <- hIsTerminalDevice stdin
      outputTerminal <- hIsTerminalDevice stdout
      let distribution = maybe "unknown" Text.pack (lookup "AGENTCTL_DISTRIBUTION" environment)
      code <- action (Sessions.Request family distribution directory environment paths (inputTerminal && outputTerminal))
      if code == 0 then exitSuccess else exitWith (ExitFailure code)
    _ -> hPutStrLn stderr "agentctl: invalid directory handoff; run agentctl from its Python application." >> exitWith (ExitFailure 2)

launch :: Agent.Agent -> [String] -> IO ()
launch agent arguments = do
  environment <- getEnvironment
  case (Mux.hostFamily, Mux.hostFamily >>= \family -> either (const Nothing) Just (Paths.fromEnvironment (family == Mux.Windows) environment)) of
    (Just family, Just paths) -> do
      directory <- getCurrentDirectory
      binary <- getExecutablePath
      inputTerminal <- hIsTerminalDevice stdin
      outputTerminal <- hIsTerminalDevice stdout
      let distribution = maybe "unknown" Text.pack (lookup "AGENTCTL_DISTRIBUTION" environment)
      code <- Launch.run (Launch.Request family distribution agent directory arguments environment paths binary (inputTerminal && outputTerminal))
      if code == 0 then exitSuccess else exitWith (ExitFailure code)
    _ -> hPutStrLn stderr "agentctl: invalid directory handoff; run agentctl from its Python application." >> exitWith (ExitFailure 2)
