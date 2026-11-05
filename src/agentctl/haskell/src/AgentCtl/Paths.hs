-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Paths
  ( Paths,
    PathsError (..),
    makePaths,
    fromEnvironment,
    cacheDirectory,
    dataDirectory,
    stateDirectory,
    launchDirectory,
  )
where

import qualified System.FilePath.Posix as Posix
import qualified System.FilePath.Windows as Windows

data Paths = Paths
  { cacheDirectory :: FilePath,
    dataDirectory :: FilePath,
    stateDirectory :: FilePath,
    windowsPaths :: Bool
  }
  deriving (Eq, Show)

data PathsError = MissingDirectory String | InvalidDirectory FilePath deriving (Eq, Show)

makePaths :: Bool -> FilePath -> FilePath -> FilePath -> Either PathsError Paths
makePaths windows cache stored state = do
  mapM_ valid [cache, stored, state]
  pure (Paths cache stored state windows)
  where
    valid path
      | '\0' `elem` path || not (if windows then Windows.isAbsolute path else Posix.isAbsolute path) = Left (InvalidDirectory path)
      | otherwise = Right ()

fromEnvironment :: Bool -> [(String, String)] -> Either PathsError Paths
fromEnvironment windows environment = do
  cache <- required "AGENTCTL_CACHE_DIR"
  stored <- required "AGENTCTL_DATA_DIR"
  state <- required "AGENTCTL_STATE_DIR"
  makePaths windows cache stored state
  where
    required key = maybe (Left (MissingDirectory key)) Right (lookup key environment)

launchDirectory :: Paths -> FilePath
launchDirectory paths = if windowsPaths paths then stateDirectory paths Windows.</> "launch" else stateDirectory paths Posix.</> "launch"
