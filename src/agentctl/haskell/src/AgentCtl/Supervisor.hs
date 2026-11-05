-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Supervisor (run) where

import qualified AgentCtl.Native as Native
import qualified AgentCtl.Paths as Paths
import qualified AgentCtl.Preflight as Preflight
import qualified AgentCtl.Sessions as Sessions
import qualified AgentCtl.Supervisor.Lock as Lock
import qualified AgentCtl.Supervisor.Log.File as LogFile
import qualified AgentCtl.Supervisor.Runtime as Runtime
import qualified AgentCtl.Supervisor.Settings as Settings
import qualified Data.Text as Text
import qualified Data.Text.IO as Text
import Data.Time (defaultTimeLocale, formatTime, getCurrentTime)
import GHC.Clock (getMonotonicTimeNSec)
import System.IO (stderr)

run :: Sessions.Request -> Settings.Settings -> IO Int
run request settings = do
  result <- Native.withStopRequests $ \stopped ->
    LogFile.withWriter (Sessions.requestPaths request) $ \writer -> do
      queried <- Sessions.openQuery request
      case queried of
        Left failure -> pure (Right (Left (Runtime.QueryFailure failure)))
        Right query -> do
          pid <- Native.processId
          began <- getMonotonicTimeNSec
          time <- getCurrentTime
          let identifier = Text.pack (formatTime defaultTimeLocale "%Y%m%dT%H%M%S%qZ" time ++ "-" ++ show pid ++ "-" ++ show began)
          Right <$> Runtime.run request settings query writer stopped identifier began
  case result of
    Left failure -> refuse ("native stop scope failed: " <> Text.pack (show failure))
    Right (Left (LogFile.LockFailure (Lock.NativeFailure (Native.LockBusy owner)))) ->
      refuse ("supervisor state is locked" <> maybe "" (\pid -> " by pid " <> Text.pack (show pid)) owner <> " at " <> Text.pack (Paths.stateDirectory (Sessions.requestPaths request)))
    Right (Left failure) -> refuse ("supervisor log failed: " <> Text.pack (show failure))
    Right (Right (Left (Runtime.QueryFailure (Sessions.QueryMuxError failure)))) -> do
      let (code, messages) = Preflight.multiplexerWarning (Sessions.requestFamily request) (Sessions.requestDistribution request) failure
      mapM_ (Text.hPutStrLn stderr) messages
      pure code
    Right (Right (Left failure)) -> refuse ("supervisor failed: " <> Text.pack (show failure))
    Right (Right (Right ())) -> pure 0
  where
    refuse message = Text.hPutStrLn stderr ("agentctl: " <> message) >> pure 1
