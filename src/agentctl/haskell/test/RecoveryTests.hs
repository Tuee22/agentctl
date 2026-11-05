-- Copyright (c) 2026 agentctl contributors.
module RecoveryTests (tests) where

import AgentCtl.Observe.Classify (ScreenClass (..))
import qualified AgentCtl.Recovery.Backoff as Backoff
import qualified AgentCtl.Recovery.Machine as Machine
import Control.Monad (forM_, replicateM)
import Data.List (nub)
import Data.Maybe (mapMaybe)
import qualified Data.Set as Set
import Data.Text (Text)
import qualified Data.Text as Text
import Data.Word (Word64)
import Test.Tasty (TestTree, testGroup)
import Test.Tasty.HUnit (Assertion, assertBool, assertEqual, assertFailure, testCase)

tests :: [TestTree]
tests =
  [ testGroup
      "Machine"
      [ testCase "never-send-unsafe" neverSendUnsafe,
        testCase "one-send-per-fingerprint" oneSendPerFingerprint,
        testCase "verify-needs-change" verifyNeedsChange
      ],
    testGroup
      "Backoff"
      [ testCase "within-bounds" withinBounds,
        testCase "grows-to-cap" growsToCap,
        testCase "seed-determines-delays" seedDeterminesDelays
      ]
  ]

overload :: Text -> Machine.Observation Text
overload key = Machine.Observation Overloaded (Just key) "overloaded at empty prompt"

observe :: ScreenClass -> Machine.Observation Text
observe category = Machine.Observation category Nothing "different screen"

walk :: Machine.State Text -> [(Double, Machine.Observation Text)] -> [(Machine.Observation Text, Machine.Decision Text)]
walk _ [] = []
walk state ((now, observation) : remaining) =
  let decision = Machine.step Backoff.defaultPolicy now observation state
   in (observation, decision) : walk (Machine.decisionState decision) remaining

timed :: [Machine.Observation Text] -> [(Double, Machine.Observation Text)]
timed = zip [0, 100 ..]

sent :: Machine.Decision key -> Bool
sent = elem Machine.SendRecovery . Machine.decisionActions

unsafeClasses :: [ScreenClass]
unsafeClasses = [Working, TrustDialog, BypassWarning, ApprovalDialog, PartialInput, LoginScreen, Exited, Unknown]

neverSendUnsafe :: Assertion
neverSendUnsafe = do
  let generated = replicateM 3 unsafeClasses
      scripts = [replicate 4 (overload "f") ++ map observe categories ++ replicate 4 (overload "g") | categories <- generated]
      traces = concatMap (walk (Machine.initial 1) . timed) scripts
      covered = Set.fromList [Machine.observationClass observation | (observation, _) <- traces, Machine.observationClass observation `elem` unsafeClasses]
  assertEqual "unsafe-class coverage is incomplete" (Set.fromList unsafeClasses) covered
  assertBool "never-send property lacks a reachable send" (any (sent . snd) traces)
  forM_ traces $ \(observation, decision) ->
    assertBool "unsafe observation requested recovery" (Machine.observationClass observation `notElem` unsafeClasses || not (sent decision))
  let f = overload "f"
      prefix = [f, f, f, f, f, f]
      states = Machine.initial 1 : map (Machine.decisionState . snd) (walk (Machine.initial 1) (zip [0, 1, 2, 100, 101, 200] prefix))
  assertEqual "state coverage is incomplete" (Set.fromList [minBound .. maxBound]) (Set.fromList (map Machine.stateMode states))
  forM_ states $ \state -> forM_ unsafeClasses $ \category -> do
    let observation = Machine.Observation category (Just "f") "unsafe current screen"
    assertBool "unsafe observation requested recovery" (not (sent (Machine.step Backoff.defaultPolicy 1000 observation state)))

episode :: Text -> [Machine.Observation Text]
episode key = replicate 4 (overload key) ++ replicate 2 (observe Working)

oneSendPerFingerprint :: Assertion
oneSendPerFingerprint = do
  let scripts = map (concatMap episode) (replicateM 4 ["f", "g", "h"])
      traces = map (walk (Machine.initial 37) . timed) scripts
      sentKeys trace = mapMaybe (Machine.observationFingerprint . fst) (filter (sent . snd) trace)
      keys = map sentKeys traces
  assertBool "fingerprint property lacks a second fresh send" (any ((>= 2) . length) keys)
  forM_ keys $ \fingerprints ->
    assertEqual "handled fingerprint received another recovery" (length fingerprints) (length (nub fingerprints))
  let existing = overload "f"
      state = Machine.baseline existing (Machine.initial 1)
      stale = walk state (timed (episode "f"))
      fresh = walk state (timed (episode "g"))
  assertBool "baseline fingerprint received recovery" (not (any (sent . snd) stale))
  assertBool "baseline suppressed an unrelated fresh fingerprint" (any (sent . snd) fresh)

verifyNeedsChange :: Assertion
verifyNeedsChange = do
  let original = overload "f"
      decisions = walk (Machine.initial 1) (zip [0, 1, 2, 100, 101] (replicate 5 original))
  case reverse decisions of
    (_, lastDecision) : _ -> do
      let state = Machine.decisionState lastDecision
          unchanged now = Machine.step Backoff.defaultPolicy now original state
      assertEqual "verification was skipped" Machine.Verify (Machine.stateMode state)
      assertEqual "recovery transition differs from oracle: unchanged screen counted as acknowledgement" Machine.Verify (Machine.stateMode (Machine.decisionState (unchanged 110)))
      let expired = unchanged 130
      assertEqual "recovery transition differs from oracle: unchanged screen counted as acknowledgement" Machine.Escalate (Machine.stateMode (Machine.decisionState expired))
      assertEqual "missing acknowledgement was not notified" [Machine.NotAcknowledgedNotice] (Machine.notifications (Machine.decisionActions expired))
      forM_ [Working, IdlePrompt] $ \category -> do
        let recovered = Machine.step Backoff.defaultPolicy 110 (observe category) state
        assertEqual "changed working or idle screen did not recover" Machine.Monitoring (Machine.stateMode (Machine.decisionState recovered))
        assertEqual "changed working or idle screen did not recover" Machine.Recovered (Machine.decisionEvent recovered)
      let redraw = Machine.step Backoff.defaultPolicy 110 (original {Machine.observationText = "redrawn same error"}) state
      assertEqual "redraw alone counted as acknowledgement" Machine.Verify (Machine.stateMode (Machine.decisionState redraw))
      let blocked = Machine.step Backoff.defaultPolicy 110 (observe PartialInput) state
      assertEqual "typed input counted as recovery" Machine.Ended (Machine.decisionEvent blocked)
      assertBool "verification sent into typed input" (not (sent blocked))
    [] -> assertFailure "verification positive control has no decisions"

withPolicy :: (Double, Double, Double, Double) -> (Backoff.Policy -> Assertion) -> Assertion
withPolicy (initial, growth, maximumWait, jitter) action = case Backoff.policy initial growth maximumWait jitter of
  Left failure -> assertFailure (Text.unpack failure)
  Right settings -> action settings

policies :: [(Double, Double, Double, Double)]
policies = [(initial, growth, initial * factor, jitter) | initial <- [0.25, 3, 30], growth <- [1.5, 2, 3], factor <- [2, 20, 100], jitter <- [0, 0.2, 0.75]]

withinBounds :: Assertion
withinBounds = do
  let invalid = [(0, 2, 900, 0.2), (-1, 2, 900, 0.2), (30, 1, 900, 0.2), (30, 0.5, 900, 0.2), (30, 2, 29, 0.2), (30, 2, 900, -0.1), (30, 2, 900, 1), (1 / 0, 2, 900, 0.2), (30, 1 / 0, 900, 0.2), (30, 2, 1 / 0, 0.2), (30, 2, 900, 0 / 0)]
  forM_ invalid $ \(initial, growth, maximumWait, jitter) -> case Backoff.policy initial growth maximumWait jitter of
    Left _ -> pure ()
    Right _ -> assertFailure "invalid backoff policy was accepted"
  withPolicy (30, 2, 900, 0.2) $ \settings -> do
    assertEqual "validated defaults differ" Backoff.defaultPolicy settings
    let attempt = 10 ^ (30 :: Int)
        scheduled = Backoff.retry settings attempt 1
    assertEqual "large retry attempt was truncated" attempt (Backoff.retryAttempt scheduled)
    assertBool "large retry escaped the cap" (Backoff.retryDelay scheduled >= 720 && Backoff.retryDelay scheduled <= 900)
  forM_ policies $ \values@(initial, growth, maximumWait, jitter) -> withPolicy values $ \settings ->
    forM_ [1 .. 40] $ \attempt -> forM_ ([0, 1, 37, maxBound] :: [Word64]) $ \seed -> do
      let scheduled = Backoff.retry settings attempt seed
          base = min maximumWait (initial * product (replicate (fromInteger attempt - 1) growth))
          epsilon = maximumWait * 1e-12
          delay = Backoff.retryDelay scheduled
      assertBool "backoff jitter escaped its allowed band" (delay + epsilon >= base * (1 - jitter) && delay <= min maximumWait (base * (1 + jitter)) + epsilon)

growsToCap :: Assertion
growsToCap = forM_ [(initial, growth, maximumWait, 0) | (initial, growth, maximumWait, _) <- policies] $ \values@(_, _, maximumWait, _) -> withPolicy values $ \settings -> do
  let delays = [Backoff.retryDelay (Backoff.retry settings attempt 1) | attempt <- [1 .. 40]]
  assertBool "backoff delay decreased with attempt" (and (zipWith (<=) delays (drop 1 delays)))
  assertEqual "backoff delay or escalation differs from oracle: failed to reach and retain cap" [maximumWait] (nub (drop 30 delays))

draws :: Backoff.Policy -> Word64 -> Integer -> [Double]
draws settings seed attempt
  | attempt > 25 = []
  | otherwise = let scheduled = Backoff.retry settings attempt seed in Backoff.retryDelay scheduled : draws settings (Backoff.retrySeed scheduled) (attempt + 1)

seedDeterminesDelays :: Assertion
seedDeterminesDelays = do
  let pairs = [(seed, seed + 1) | seed <- [0 .. 31]]
      sequences = [(draws Backoff.defaultPolicy left 1, draws Backoff.defaultPolicy right 1) | (left, right) <- pairs]
  forM_ pairs $ \(seed, _) -> assertEqual "backoff seed was not deterministic" (draws Backoff.defaultPolicy seed 1) (draws Backoff.defaultPolicy seed 1)
  assertBool "backoff seed did not change the delay sequence" (any (uncurry (/=)) sequences)
