-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Observe.Classify.Input (logicalInput) where

import AgentCtl.Observe.Capture (Visual (..), validVisual)
import AgentCtl.Observe.Normalize (lineEndings)
import Data.Char (isAscii, isDigit, isSpace)
import Data.List (dropWhileEnd)
import Data.Text (Text)
import qualified Data.Text as Text
import Text.Read (readMaybe)

type Glyph = (Char, Bool)

logicalInput :: Text -> Text -> Maybe Visual -> Text
logicalInput _ supplied Nothing = supplied
logicalInput marker supplied (Just visual)
  | not (validVisual visual) = uncertain supplied
  | otherwise = case styledRows (visualText visual) of
      Nothing -> uncertain supplied
      Just rows -> case drop (visualCursorY visual) rows of
        row : _ -> case composer marker row of
          Just (start, body)
            | Text.pack (map fst body) /= supplied -> uncertain supplied
            | Text.null supplied -> if visualCursorX visual == start then "" else uncertain supplied
            | visualCursorX visual == start && all (\(character, faint) -> isSpace character || faint) body -> ""
            | otherwise -> supplied
          Nothing -> if not (all (isSpace . fst) row) then uncertain supplied else supplied
        [] -> uncertain supplied

uncertain :: Text -> Text
uncertain supplied = if Text.null supplied then "<unverified composer>" else supplied

composer :: Text -> [Glyph] -> Maybe (Int, [Glyph])
composer marker row = case dropWhile (horizontal . fst) row of
  (character, _) : remaining
    | Text.singleton character == marker -> case remaining of
        [] -> Just (indent + 2, [])
        (separator, _) : body
          | horizontal separator -> Just (indent + 2, dropWhileEnd (isSpace . fst) body)
        _ -> Nothing
  _ -> Nothing
  where
    indent = length (takeWhile (horizontal . fst) row)
    horizontal character = character == ' ' || character == '\160'

styledRows :: Text -> Maybe [[Glyph]]
styledRows = scan False [] [] . Text.unpack . lineEndings
  where
    scan _ current rows [] = Just (reverse (reverse current : rows))
    scan faint current rows ('\n' : remaining) = scan faint [] (reverse current : rows) remaining
    scan faint current rows ('\ESC' : '[' : remaining) = case break (== 'm') remaining of
      (codes, 'm' : rest)
        | all (\character -> character == ';' || (isAscii character && isDigit character)) codes -> do
            values <- traverse number (Text.splitOn ";" (Text.pack codes))
            next <- attributes faint values
            scan next current rows rest
      _ -> Nothing
    scan _ _ _ ('\ESC' : _) = Nothing
    scan faint current rows (character : remaining)
      | character >= ' ' = scan faint ((character, faint) : current) rows remaining
      | otherwise = Nothing
    number value = if Text.null value then Just 0 else readMaybe (Text.unpack value)

attributes :: Bool -> [Int] -> Maybe Bool
attributes faint [] = Just faint
attributes _ (0 : remaining) = attributes False remaining
attributes _ (2 : remaining) = attributes True remaining
attributes _ (22 : remaining) = attributes False remaining
attributes faint (38 : 5 : _ : remaining) = attributes faint remaining
attributes faint (48 : 5 : _ : remaining) = attributes faint remaining
attributes faint (38 : 2 : _ : _ : _ : remaining) = attributes faint remaining
attributes faint (48 : 2 : _ : _ : _ : remaining) = attributes faint remaining
attributes _ (38 : _) = Nothing
attributes _ (48 : _) = Nothing
attributes faint (_ : remaining) = attributes faint remaining
