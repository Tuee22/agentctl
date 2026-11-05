-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Mux.Psmux (render) where

import AgentCtl.Mux.Command (Command (..), Rendered (..), optionName, optionValueText)
import qualified AgentCtl.Mux.Tmux as Tmux
import AgentCtl.Session.Name (sessionNameText)
import qualified Data.Text as Text

render :: Command -> Rendered
render command =
  (Tmux.render command)
    { executable = "psmux.exe",
      arguments = case command of
        ShowOptions name -> ["show-options", "-t", "=" ++ Text.unpack (sessionNameText name)]
        SetIdentity name key value -> ["set-option", "-t", "=" ++ Text.unpack (sessionNameText name), optionName key, Text.unpack (optionValueText value)]
        _ -> arguments (Tmux.render command)
    }
