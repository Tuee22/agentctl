-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Mux.Tmux (render) where

import AgentCtl.Mux.Command (Command (..), Rendered (..), optionName, optionValueText, paneText)
import AgentCtl.Session.Name (sessionNameText)
import Data.Text (Text)
import qualified Data.Text as Text

render :: Command -> Rendered
render command = Rendered "tmux" $ case command of
  Create name binary spec -> ["new-session", "-d", "-s", text (sessionNameText name), "-P", "-F", "#{pane_id}", "--", binary, "pane-exec", spec]
  HasSession name -> ["has-session", "-t", exact (sessionNameText name)]
  ListSessions format -> ["list-sessions", "-F", text format]
  ShowOptions name -> ["show-options", "-t", exact (sessionNameText name) ++ ":"]
  ListPanes name format -> ["list-panes", "-s", "-t", exact (sessionNameText name), "-F", text format]
  PaneState pane -> ["display-message", "-p", "-t", text (paneText pane), "#{pane_pid} #{pane_dead} #{pane_dead_status} #{pane_dead_signal}"]
  InspectPane pane format -> ["display-message", "-p", "-t", text (paneText pane), text format]
  SetIdentity name key value -> ["set-option", "-t", exact (sessionNameText name) ++ ":", optionName key, text (optionValueText value)]
  RemainOnExit pane True -> ["set-option", "-p", "-t", text (paneText pane), "remain-on-exit", "on"]
  RemainOnExit pane False -> ["set-option", "-p", "-u", "-t", text (paneText pane), "remain-on-exit"]
  Capture pane count -> ["capture-pane", "-p", "-J", "-t", text (paneText pane), "-S", "-" ++ show count]
  CaptureVisual pane -> ["capture-pane", "-p", "-e", "-t", text (paneText pane), "-S", "0"]
  SendLiteral pane value -> ["send-keys", "-l", "-t", text (paneText pane), "--", text value]
  SendEnter pane -> ["send-keys", "-t", text (paneText pane), "Enter"]
  Attach name -> ["attach-session", "-t", exact (sessionNameText name)]
  Switch name -> ["switch-client", "-t", exact (sessionNameText name)]
  Kill name -> ["kill-session", "-t", exact (sessionNameText name)]

text :: Text -> String
text = Text.unpack

exact :: Text -> String
exact name = "=" ++ text name
