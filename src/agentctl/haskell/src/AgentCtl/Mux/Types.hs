-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Mux.Types
  ( Family (..),
    Kind (..),
    Multiplexer (..),
    muxExecutable,
    muxKind,
    muxVersion,
  )
where

import Data.Text (Text)

data Family = Linux | Darwin | Windows deriving (Eq, Show)

data Kind = Tmux | Psmux deriving (Eq, Show)

data Multiplexer = Multiplexer Kind FilePath Text deriving (Eq, Show)

muxExecutable :: Multiplexer -> FilePath
muxExecutable (Multiplexer _ path _) = path

muxKind :: Multiplexer -> Kind
muxKind (Multiplexer kind _ _) = kind

muxVersion :: Multiplexer -> Text
muxVersion (Multiplexer _ _ version) = version
