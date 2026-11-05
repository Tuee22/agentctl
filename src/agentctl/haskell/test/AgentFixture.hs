-- Copyright (c) 2026 agentctl contributors.
module AgentFixture (run) where

import qualified AgentCtl.Agent as Agent
import qualified AgentCtl.Agent.Auth as Auth
import qualified AgentCtl.Mux as Mux
import qualified AgentCtl.Preflight as Preflight
import Data.Aeson (Value, eitherDecode, encode, object, withObject, (.!=), (.:), (.:?), (.=))
import Data.Aeson.Types (parseEither)
import qualified Data.ByteString.Lazy.Char8 as Bytes
import qualified Data.Text.IO as Text
import System.Environment (getEnvironment)
import System.Exit (ExitCode (ExitFailure), die, exitWith)
import System.IO (stderr)

run :: IO ()
run = do
  input <- Bytes.getContents
  value <- either die pure (eitherDecode input)
  (operation, name, executable, directory, deadline, distribution) <- either die pure (parseEither context value)
  agent <- maybe (die "unknown fixture agent") pure (Agent.agentFromText name)
  family <- maybe (die "unsupported native agent host") pure Mux.hostFamily
  environment <- getEnvironment
  case operation of
    "probe" -> do
      outcome <- Auth.probe (Agent.table family agent) executable directory environment deadline
      let (code, linesOfWarning) = Auth.warning agent outcome
      Bytes.putStrLn (encode (object ["state" .= show (Auth.classifyAuth outcome), "outcome" .= show outcome, "warning" .= object ["exit" .= code, "lines" .= linesOfWarning]]))
    "preflight" -> do
      result <- Preflight.preflight family distribution agent directory environment
      case result of
        Left failure -> do
          let (code, linesOfWarning) = Preflight.warning family distribution agent failure
          Bytes.putStrLn (encode (object ["state" .= ("Refused" :: String), "warning" .= object ["exit" .= code, "lines" .= linesOfWarning]]))
          mapM_ (Text.hPutStrLn stderr) linesOfWarning
          exitWith (ExitFailure code)
        Right ready -> Bytes.putStrLn (encode (readyValue ready))
    _ -> die "unknown agent fixture operation"
  where
    context = withObject "agent fixture" $ \fields ->
      (,,,,,) <$> (fields .:? "operation" .!= ("probe" :: String)) <*> fields .: "agent" <*> (fields .:? "executable" .!= "") <*> fields .: "directory" <*> (fields .:? "deadline" .!= 10000000) <*> (fields .:? "distribution" .!= "unknown")

readyValue :: Preflight.Ready -> Value
readyValue ready =
  object
    [ "state" .= ("Ready" :: String),
      "agent" .= Agent.agentText (Preflight.readyAgent ready),
      "executable" .= Preflight.readyExecutable ready,
      "auth" .= show (Preflight.readyAuth ready),
      "multiplexer" .= Mux.muxExecutable (Preflight.readyMultiplexer ready)
    ]
