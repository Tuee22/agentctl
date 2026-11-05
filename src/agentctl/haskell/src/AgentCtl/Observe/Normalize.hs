-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Observe.Normalize (normalise, tailLines, lineEndings) where

import Data.Text (Text)
import qualified Data.Text as Text

tailLines :: Int
tailLines = 100

normalise :: Text -> Text
normalise screen =
  Text.intercalate "\n" $
    reverse $
      take tailLines $
        dropWhile Text.null $
          reverse $
            map (Text.dropWhileEnd horizontalSpace) $
              Text.splitOn "\n" (lineEndings screen)

lineEndings :: Text -> Text
lineEndings = Text.replace "\r" "\n" . Text.replace "\r\n" "\n"

horizontalSpace :: Char -> Bool
horizontalSpace character = character == ' ' || character == '\t'
