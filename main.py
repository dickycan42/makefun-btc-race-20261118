"""Hourly-momentum trend rider for the make.fun BTC race (agent-fun/bars-replay/v1).

One asset, CBBTC/USDC, one-minute bars, long only, paper money. The bot reads the
bars the harness sends, keeps the last 61 closes, and trades a single idea:

  * Enter: the 60-minute return of the close crosses above +50 bps. A 60-minute
    move of that size is a real hourly trend, not one-minute noise (one-minute
    closes jitter ~7 bps a bar), and it is big enough to pay the ~26 bps a full
    round trip costs in fees, slippage and pool impact and still leave room.
  * Exit, whichever comes first:
      - momentum flip: the 60-minute return falls below -50 bps;
      - trailing stop: the close falls 80 bps below the highest close seen
        since the entry;
      - time stop: 360 bars (6 hours) have passed since the entry, so a dead
        trend is never ridden through its whole reversal.
  * Re-arm: after any exit the bot waits until the 60-minute return has gone
    negative again before it may buy anew, so it cannot instantly re-buy the
    same hot move it just sold.

Position size is the whole cash balance on every entry and the whole position
on every exit. One open position at most, never a short, never leverage.

Local grade on the frozen dev window (1,440 one-minute bars, exact harness
fill math): net PnL +10.63 USDC, 4 filled orders (2 round trips), fees 1.62
USDC, maximum drawdown 1.10%, first half +13.16 USDC, second half -2.53 USDC,
no rejected orders, and two runs produced byte-identical action logs.

Everything is integer arithmetic on the bar closes the harness sent; there is
no randomness, no wall clock, no network and no file access, so two runs on
the same bars answer byte for byte alike. Diagnostics go to stderr only.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars

# --- strategy constants (basis points, bars) --------------------------------
LOOKBACK_BARS = 60        # the momentum window: one hour of one-minute bars
ENTER_BPS = 50            # 60-minute return above this opens a position
EXIT_BPS = -50            # 60-minute return below this closes it
TRAIL_BPS = 80            # give-back from the peak close since entry
MAX_HOLD_BARS = 360       # time stop: six hours in the trade, then out
MAX_SLIPPAGE_BPS = 300    # wide enough never to refuse an ordinary fill

DEFAULT_SYMBOL = "CBBTC"


def _above(close, old, bps):
    """True when (close - old) / old exceeds bps basis points, exactly."""
    return (close - old) * 10_000 > bps * old


def _below(close, old, bps):
    """True when (close - old) / old is below bps basis points, exactly."""
    return (close - old) * 10_000 < bps * old


class TrendBot:
    """State for one run: the close history and the open-trade bookkeeping."""

    def __init__(self):
        self.symbol = DEFAULT_SYMBOL
        self.min_notional = 1_000_000
        self.closes = []          # closes, oldest first, last LOOKBACK_BARS + 1
        self.in_position = False
        self.peak = 0             # highest close seen since the entry
        self.held = 0             # bars since the entry was decided
        self.armed = True         # False after an exit until momentum resets

    def on_hello(self, state):
        symbols = state.hello.get("symbols") or []
        if symbols:
            self.symbol = symbols[0]["symbol"]
        fees = state.hello.get("fees") or {}
        try:
            self.min_notional = int(fees.get("min_notional_quote_units", 1_000_000))
        except (TypeError, ValueError):
            self.min_notional = 1_000_000

    def _bar(self, batch):
        for bar in batch.get("bars") or []:
            if bar.get("symbol") == self.symbol:
                return bar
        return None

    def _sell_all(self, state):
        holding = state.positions.get(self.symbol)
        if holding is None or holding.qty <= 0:
            self.in_position = False
            return []
        self.in_position = False
        self.armed = False
        return [{
            "side": "sell",
            "symbol": self.symbol,
            "qty": holding.qty,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]

    def on_batch(self, state, batch):
        bar = self._bar(batch)
        if bar is None:
            return []
        close = int(bar["c"])
        self.closes.append(close)
        if len(self.closes) > LOOKBACK_BARS + 1:
            del self.closes[: len(self.closes) - (LOOKBACK_BARS + 1)]

        if state.warming_up:
            return []

        # The account is the truth about the position: a buy whose fill was
        # refused leaves no position behind, and a sell refused at the fill
        # leaves the position in place.
        holding = state.positions.get(self.symbol)
        has_position = holding is not None and holding.qty > 0
        if self.in_position and not has_position:
            self.in_position = False
        elif has_position and not self.in_position:
            self.in_position = True
            self.peak = close
            self.held = 0

        if len(self.closes) < LOOKBACK_BARS + 1:
            return []
        old = self.closes[0]

        if self.in_position:
            self.held += 1
            if close > self.peak:
                self.peak = close
            giveback = (self.peak - close) * 10_000 >= TRAIL_BPS * self.peak
            flipped = _below(close, old, EXIT_BPS)
            timed_out = self.held >= MAX_HOLD_BARS
            if giveback or flipped or timed_out:
                return self._sell_all(state)
            return []

        if not self.armed:
            if _below(close, old, 0):
                self.armed = True
            return []
        if not _above(close, old, ENTER_BPS):
            return []

        notional = min(state.cash, state.weight_room(self.symbol))
        if notional < self.min_notional:
            return []
        self.in_position = True
        self.peak = close
        self.held = 0
        self.armed = False
        return [{
            "side": "buy",
            "symbol": self.symbol,
            "notional_quote_units": notional,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]


def main():
    bot = TrendBot()
    makefun_bars.run(bot.on_batch, on_hello=bot.on_hello)


if __name__ == "__main__":
    main()
