-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Agent
  ( Agent (..),
    Entry (..),
    agentFromText,
    agentText,
    table,
    FileEntry (..),
    Listing (..),
    ResolutionError (..),
    selectAgent,
    resolveAgent,
  )
where

import AgentCtl.Agent.Types (Agent (..), agentFromText, agentText)
import AgentCtl.Mux (Family (..))
import Control.Exception (IOException, catch)
import Control.Monad (forM)
import Data.Aeson (FromJSON (parseJSON), withObject, (.:))
import qualified Data.Text as Text
import qualified System.Directory as Directory
import qualified System.FilePath.Posix as Posix
import qualified System.FilePath.Windows as Windows

data Entry = Entry
  { executableName :: FilePath,
    mandatoryFlags :: [String],
    removableAliases :: [String],
    authArguments :: [String],
    loginRemedy :: Text.Text,
    loginVariants :: [Text.Text],
    installHint :: Text.Text,
    recoveryText :: Text.Text
  }
  deriving (Eq, Show)

table :: Family -> Agent -> Entry
table family agent = case agent of
  Claude ->
    Entry
      (nativeName family "claude")
      ["--dangerously-skip-permissions"]
      []
      ["auth", "status"]
      "claude auth login"
      ["claude auth login --console", "claude auth login --sso"]
      (claudeInstall family)
      "Continue the interrupted task from the last completed step."
  Codex ->
    Entry
      (nativeName family "codex")
      ["--dangerously-bypass-approvals-and-sandbox", "--no-daemon"]
      ["--yolo"]
      ["login", "status"]
      "codex login"
      ["codex login --device-auth"]
      (codexInstall family)
      "Continue the interrupted task from the last saved checkpoint."

nativeName :: Family -> String -> FilePath
nativeName Windows name = name ++ ".exe"
nativeName Linux name = name
nativeName Darwin name = name

claudeInstall :: Family -> Text.Text
claudeInstall Windows = "winget install Anthropic.ClaudeCode"
claudeInstall Linux = "curl -fsSL https://claude.ai/install.sh | bash"
claudeInstall Darwin = "curl -fsSL https://claude.ai/install.sh | bash"

codexInstall :: Family -> Text.Text
codexInstall Windows = "powershell -ExecutionPolicy ByPass -c \"irm https://chatgpt.com/codex/install.ps1 | iex\""
codexInstall Linux = "curl -fsSL https://chatgpt.com/codex/install.sh | sh"
codexInstall Darwin = "curl -fsSL https://chatgpt.com/codex/install.sh | sh"

data FileEntry = FileEntry FilePath Bool deriving (Eq, Show)

data Listing = Listing FilePath [FileEntry] deriving (Eq, Show)

data ResolutionError
  = AgentMissing
  | NativeRequired FilePath
  | InvalidSearchDirectory FilePath
  | AgentDiscoveryFailed Text.Text
  deriving (Eq, Show)

instance FromJSON FileEntry where
  parseJSON = withObject "executable entry" $ \fields ->
    FileEntry <$> fields .: "name" <*> fields .: "executable"

instance FromJSON Listing where
  parseJSON = withObject "PATH directory" $ \fields ->
    Listing <$> fields .: "directory" <*> fields .: "files"

selectAgent :: Family -> Agent -> FilePath -> [String] -> [Listing] -> Either ResolutionError FilePath
selectAgent family agent cwd extensions listings
  | not (absolute family cwd) = Left (InvalidSearchDirectory cwd)
  | otherwise = case matches of
      [] -> Left AgentMissing
      path : _
        | family == Windows && Text.toLower (Text.pack (Windows.takeExtension path)) /= ".exe" -> Left (NativeRequired path)
        | not (absolute family path) -> Left (InvalidSearchDirectory path)
        | otherwise -> Right path
  where
    base = Text.unpack (agentText agent)
    names = if family == Windows then map (base ++) (if null extensions then [".COM", ".EXE", ".BAT", ".CMD"] else extensions) else [base]
    same left right = if family == Windows then Text.toCaseFold (Text.pack left) == Text.toCaseFold (Text.pack right) else left == right
    matches =
      [ joinPath family (makeAbsolute family cwd directory) name
      | Listing directory files <- listings,
        requested <- names,
        FileEntry name True <- files,
        same name requested
      ]

absolute :: Family -> FilePath -> Bool
absolute Windows = Windows.isAbsolute
absolute Linux = Posix.isAbsolute
absolute Darwin = Posix.isAbsolute

joinPath :: Family -> FilePath -> FilePath -> FilePath
joinPath Windows directory name = Windows.normalise (directory Windows.</> name)
joinPath Linux directory name = Posix.normalise (directory Posix.</> name)
joinPath Darwin directory name = Posix.normalise (directory Posix.</> name)

makeAbsolute :: Family -> FilePath -> FilePath -> FilePath
makeAbsolute family cwd path = if absolute family path then path else joinPath family cwd path

resolveAgent :: Family -> Agent -> FilePath -> [(String, String)] -> IO (Either ResolutionError FilePath)
resolveAgent family agent cwd environment = discover `catch` refused
  where
    refused :: IOException -> IO (Either ResolutionError FilePath)
    refused exception = pure (Left (AgentDiscoveryFailed (Text.pack (show exception))))
    variable key = lookup key (if family == Windows then [(Text.unpack (Text.toUpper (Text.pack name)), value) | (name, value) <- environment] else environment)
    paths = maybe [] (if family == Windows then Windows.splitSearchPath else Posix.splitSearchPath) (variable "PATH")
    extensions = maybe [] (map Text.unpack . Text.splitOn ";" . Text.pack) (variable "PATHEXT")
    discover = do
      listings <- forM paths $ \directory -> do
        let path = makeAbsolute family cwd directory
        present <- Directory.doesDirectoryExist path
        names <- if present then Directory.listDirectory path else pure []
        files <- forM names $ \name -> do
          let candidate = joinPath family path name
          regular <- Directory.doesFileExist candidate
          executable <- if regular then Directory.executable <$> Directory.getPermissions candidate else pure False
          pure (FileEntry name executable)
        pure (Listing directory files)
      case selectAgent family agent cwd extensions listings of
        Left failure -> pure (Left failure)
        Right path -> Right <$> Directory.canonicalizePath path
