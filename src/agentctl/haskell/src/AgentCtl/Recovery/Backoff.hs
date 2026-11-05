-- Copyright (c) 2026 agentctl contributors.
module AgentCtl.Recovery.Backoff
  ( Policy,
    policy,
    defaultPolicy,
    initialDelay,
    Level (..),
    levelText,
    Retry (..),
    retry,
    cappedDelay,
  )
where

import Data.Bits (shiftR, (.&.))
import Data.Text (Text)
import Data.Word (Word64)

data Policy = Policy
  { initialDelay :: Double,
    multiplier :: Double,
    maximumDelay :: Double,
    jitterFraction :: Double
  }
  deriving (Eq, Show)

policy :: Double -> Double -> Double -> Double -> Either Text Policy
policy initial growth maximumWait jitter
  | any (\number -> isNaN number || isInfinite number) [initial, growth, maximumWait, jitter] = Left "backoff values must be finite"
  | initial <= 0 || growth <= 1 || maximumWait < initial || jitter < 0 || jitter >= 1 = Left "backoff requires positive initial, multiplier > 1, maximum >= initial and 0 <= jitter < 1"
  | otherwise = Right (Policy initial growth maximumWait jitter)

defaultPolicy :: Policy
defaultPolicy = Policy 30 2 900 0.2

data Level = Info | Warning deriving (Eq, Show)

levelText :: Level -> Text
levelText value = case value of
  Info -> "info"
  Warning -> "warning"

data Retry = Retry
  { retryAttempt :: Integer,
    retryBase :: Double,
    retryDelay :: Double,
    retryLevel :: Level,
    retryNotify :: Bool,
    retrySeed :: Word64
  }
  deriving (Eq, Show)

cap :: Policy -> Double -> Double
cap settings = min (maximumDelay settings)

cappedDelay :: Policy -> Integer -> Double
cappedDelay settings attempt = cap settings unbounded
  where
    power = fromIntegral (max 1 attempt - 1)
    factor = multiplier settings ** power
    unbounded
      | isInfinite factor = exp (log (initialDelay settings) + power * log (multiplier settings))
      | otherwise = initialDelay settings * factor

retry :: Policy -> Integer -> Word64 -> Retry
retry settings suppliedAttempt seed = Retry attempt base delay level notify nextSeed
  where
    attempt = max 1 suppliedAttempt
    base = cappedDelay settings attempt
    nextSeed = seed * 6364136223846793005 + 1442695040888963407
    unit = fromIntegral (nextSeed `shiftR` 11) / 9007199254740992
    offset = jitterFraction settings * (2 * unit - 1)
    delay = cap settings (base * (1 + offset))
    level = if base >= maximumDelay settings then Warning else Info
    notify = attempt .&. (attempt - 1) == 0
