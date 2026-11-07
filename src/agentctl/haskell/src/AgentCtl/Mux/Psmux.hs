-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Mux.Psmux (render) where

import AgentCtl.Mux.Command (Command (..), Rendered (..), paneId)
import qualified AgentCtl.Mux.Tmux as Tmux
import AgentCtl.Session.Name (sessionNameText)
import qualified Data.Text as Text

render :: Command -> Rendered
render command =
  (Tmux.render command)
    { executable = "psmux.exe",
      arguments = case command of
        RemainOnExit name pane True -> ["set-option", "-p", "-t", target name pane, "remain-on-exit", "on"]
        RemainOnExit name pane False -> ["set-option", "-p", "-u", "-t", target name pane, "remain-on-exit"]
        _ -> arguments (Tmux.render command)
    }
  where
    target name pane = "=" ++ Text.unpack (sessionNameText name) ++ ":" ++ Text.unpack (paneId pane)
