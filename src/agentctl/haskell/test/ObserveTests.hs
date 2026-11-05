-- Copyright (c) 2026 agentctl contributors.
module ObserveTests (tests) where

import AgentCtl.Observe.Capture (Screen (..), Visual (..))
import qualified AgentCtl.Observe.Classify as Classify
import qualified AgentCtl.Observe.Classify.Claude as Claude
import qualified AgentCtl.Observe.Classify.Codex as Codex
import AgentCtl.Observe.Fingerprint (ErrorBlock (..), fingerprint, fingerprintText)
import AgentCtl.Observe.Normalize (normalise)
import Control.Monad (forM_, replicateM)
import Data.List (nub)
import Data.Text (Text)
import qualified Data.Text as Text
import Test.Tasty (TestTree, testGroup)
import Test.Tasty.HUnit (assertEqual, testCase)

tests :: [TestTree]
tests =
  [ testGroup "Normalize" [testCase "idempotent" idempotent],
    testGroup "Classify" [testCase "dead-pane-is-exited" deadPaneIsExited, testCase "placeholder-needs-visual-evidence" placeholderNeedsVisualEvidence],
    testGroup
      "Fingerprint"
      [ testCase "stable-under-redraw" stableUnderRedraw,
        testCase "different-error-differs" differentErrorDiffers
      ]
  ]

deadPaneIsExited :: IO ()
deadPaneIsExited =
  forM_ [(Claude.classify, "Claude Code\n❯"), (Codex.classify, "OpenAI Codex\n›")] $ \(classify, text) -> do
    assertEqual "pane death was inferred from text" Classify.Exited (Classify.classificationClass (classify (Screen text True Nothing)))
    assertEqual "live idle prompt is not recognized" Classify.IdlePrompt (Classify.classificationClass (classify (Screen text False Nothing)))

placeholderNeedsVisualEvidence :: IO ()
placeholderNeedsVisualEvidence =
  forM_ [(Claude.classify, "❯"), (Codex.classify, "›")] $ \(classify, marker) -> do
    let text = marker <> " Try inspect parser"
        faint = marker <> " \ESC[2mTry inspect parser\ESC[0m\n"
        normal = marker <> " Try inspect parser\n"
        screen styled column = Screen text False (Just (Visual column 0 80 1 styled))
        category = Classify.classificationClass . classify
    assertEqual "empty composer suggestion was treated as a draft" Classify.IdlePrompt (category (screen faint 2))
    forM_ [screen normal 2, screen faint 3, Screen text False Nothing, screen (marker <> " \ESC[38;5;2mTry inspect parser\ESC[0m\n") 2, screen (marker <> " \ESC[2mOther content\ESC[0m\n") 2] $ \draft ->
      assertEqual "classifier accepted a draft as a placeholder" Classify.PartialInput (category draft)
    assertEqual "classifier accepted a whitespace draft" Classify.PartialInput (category (Screen marker False (Just (Visual 3 0 80 1 (marker <> " \n")))))

idempotent :: IO ()
idempotent = do
  let screens = concatMap (`replicateM` ("aλ \t\r\n" :: String)) [0 .. 5]
  forM_ screens $ \screen -> do
    let once = normalise (Text.pack screen)
    assertEqual "screen normalisation changed on second pass" once (normalise once)
  assertEqual "screen normalisation lost line or whitespace semantics" "  indented\nnext\nlast" (normalise "  indented\t \r\nnext\rlast  \n \t\n")
  assertEqual "screen normalisation lost the bounded tail" (numbered [10 .. 109]) (normalise (numbered [0 .. 109]))
  assertEqual "screen normalisation retains only blank output" "" (normalise " \t\r\n\r\n")

numbered :: [Int] -> Text
numbered = Text.intercalate "\n" . map (Text.pack . show)

stableUnderRedraw :: IO ()
stableUnderRedraw = do
  let expected = "23b17b289036cd30c2589d4a240da953b6df4c997d701f59e7732571757e5d02"
      contexts =
        [ ("", ""),
          ("older tool output\n", "\n> "),
          ("redrawn header\nold overload\n", "\n\n> "),
          ("overloaded\nintervening work\n", "\nnew footer")
        ]
  forM_ contexts $ \(before, after) ->
    forM_ ["overloaded", "overloaded  \r\n\t\n"] $ \content ->
      assertEqual "error fingerprint included surrounding output or redraw" expected (fingerprintText (fingerprint (ErrorBlock before content after)))

differentErrorDiffers :: IO ()
differentErrorDiffers = do
  -- Expected SHA-256 values come from Python hashlib over the literal UTF-8 blocks.
  let cases =
        [ ("overloaded", "23b17b289036cd30c2589d4a240da953b6df4c997d701f59e7732571757e5d02"),
          ("capacity unavailable", "68de99fff128a06f90daa741b0f788b02f255fa7f5fc27c350ab59de53d85ef1"),
          ("server λ日", "2db91624d7ed59145bd9683ecb07e3a61a3b9ad45e6e31ed441626004f1063a6"),
          ("", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
        ]
      observed = map (fingerprintText . fingerprint . (\content -> ErrorBlock "" content "") . fst) cases
  assertEqual "error fingerprint differs from independent SHA-256" (map snd cases) observed
  assertEqual "distinct error blocks share a fingerprint" (length cases) (length (nub observed))
