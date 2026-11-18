[![make.fun](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/dickycan42/makefun-btc-race-20261118/rank.svg)](https://make.fun)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/dickycan42/makefun-btc-race-20261118/reward.svg)](https://make.fun)

# Hourly-momentum trend rider — BTC race bot

A bot for the make.fun competition **"Race a BTC trading bot live for 24 hours"**
(`btc-race-24h-20261118-1444`). It trades Coinbase Wrapped BTC (cbBTC) against
USDC, one-minute bars, long only, with 1,000 USDC of paper money. Nothing here
trades for real.

## Strategy

One idea, kept deliberately simple so it survives a 24-hour window it has never
seen: ride a genuine hourly trend, get out when the trend dies.

- **Enter** when the 60-minute return of the close rises above **+50 bps**.
  One-minute closes jitter about 7 bps a bar, so a 50 bps hourly move is a real
  trend, not noise — and it is large enough to pay the ~26 bps a full-size round
  trip costs in fees, slippage and pool impact and still leave room.
- **Exit** on whichever comes first:
  - the 60-minute return falls below **−50 bps** (momentum flip);
  - the close gives back **80 bps** from the highest close since entry
    (trailing stop);
  - **360 bars (6 hours)** have passed since entry (time stop — a dead trend
    is never ridden through its whole reversal).
- **Re-arm:** after any exit the bot waits until the 60-minute return has gone
  negative again before it may buy anew, so it cannot instantly re-buy the same
  hot move it just sold.
- **Size:** the whole cash balance on entry, the whole position on exit. At most
  one open position, never short, never leveraged.

All decisions are exact integer arithmetic on the closes the harness sent. No
randomness, no wall clock, no network, no files outside the repository — two
runs on the same bars answer byte for byte alike.

## Files

- `main.py` — the bot (Python 3.13, standard library only).
- `vendor/makefun_bars.py` — the kit's protocol shim, copied byte for byte.
- `LICENSE` — MIT.

## Local grading (dev window, 1,440 one-minute bars)

Graded with a local replica of the kit's own harness (same fill math: 4 bps fee,
2 bps slippage, constant-product impact against each bar's open depth), run
twice — both runs produced byte-identical action logs.

| Measure | Result |
|---|---|
| Net PnL (dev window) | **+10.63 USDC** |
| Trades (filled orders) | 4 (2 round trips) |
| Fees paid | 1.62 USDC |
| Maximum drawdown | 1.10% |
| First half (bars 0–719) | +13.16 USDC |
| Second half (bars 720–1439) | −2.53 USDC |
| Rejected orders | 0 |
| Determinism (2 runs) | identical action logs |

The profit comes from one trade: buying near the bottom of the window's one
big multi-hour up-leg and selling near its top. The second trade roughly breaks
even. The dev window decides only who races — the ranking is decided by the
unseen 24-hour race window — so the parameters above were chosen on a plateau
(neighbouring thresholds give similar results), not tuned to a spike.

## Running it

The kit grades the repository with:

```
node cli/makefun.mjs grade-local --kit . --bot <repository> --driver docker
```
