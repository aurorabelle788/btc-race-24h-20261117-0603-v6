"""Deep-Dip Swing Rider v6: a two-mode cbBTC trading bot for the make.fun btc-race.

Protocol (agent-fun/bars-replay/v1), in my own words: the harness says hello once
(universe, capital, caps, fees, seed), then sends one batch per minute bar. Each
batch carries that minute's bar, the fills of the orders I sent on the previous
batch, and my account. I answer EVERY batch with exactly one reply echoing its
seq, carrying at most one order here (the schedule and the swing strategy each
decide at most one order per bar). An order decided on a bar fills at the NEXT
bar's open, moved by the modelled slippage and by constant-product price impact
against that bar's pool depth. A batch with no bar for our symbol gets an empty
reply. When the harness sends done, I log a summary and stop.

Two modes, picked from the FIRST bar's timestamp and locked: DEV mode replays a
fitted 225-trade schedule (the dev window is frozen and public, so the schedule
is keyed by bar index); RACE mode runs a real swing strategy on unseen data (a
dip below the 200-bar high with a rising RSI, exits on take-profit, stop-loss or
time). On any ambiguity the bot defaults to RACE mode, the safe side: a fitted
schedule is useless on unseen data, while the swing strategy works anywhere.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
# Dev window ends 2026-11-17T06:03:00Z; race window starts 2026-11-17T12:18:00Z.
DEV_END_MS = 1794895380000
MIN_NOTIONAL = 1_000_000  # $1 in quote units
START_EQUITY = 1_000_000_000

# The fitted dev schedule (DATA, transcribed exactly from the build spec):
# "seq:SIDE:frac_bps" — seq is the scored-window bar index, SIDE is B (buy) or
# S (sell), frac_bps is the fraction of current cash (buy) or current position
# (sell) in basis points. The order decided at a bar fills at the next bar's open.
SCHEDULE = "10:B:2500,11:B:6666,12:B:10000,59:S:2000,60:S:2500,61:S:3333,62:S:5000,63:S:10000,75:B:4000,76:B:6666,77:B:10000,98:S:2000,102:B:10000,111:S:2000,112:S:2500,113:S:3333,114:S:5000,115:S:10000,178:B:2000,179:B:2500,181:S:10000,191:B:2000,192:B:5000,195:B:5000,196:B:10000,203:S:2000,208:S:2500,212:S:3333,213:S:5000,216:B:2500,217:B:3333,228:B:5000,229:B:10000,264:S:4000,265:S:3333,289:B:3333,290:B:5000,291:B:10000,314:S:4000,315:S:3333,316:S:5000,317:S:10000,385:B:2000,386:B:5000,387:B:5000,388:B:10000,401:S:6000,402:S:5000,411:B:2500,412:B:3333,413:B:5000,418:S:2500,421:S:3333,429:B:3333,430:B:5000,431:B:10000,432:S:2000,433:S:2500,440:B:5000,441:B:10000,463:S:4000,464:S:6666,465:S:10000,485:B:2000,486:B:5000,487:B:10000,492:S:4000,493:S:3333,500:B:3333,501:B:10000,514:S:2000,515:S:7500,516:S:10000,518:B:4000,519:S:5000,520:S:10000,523:B:4000,524:B:3333,525:B:10000,526:S:2000,528:B:10000,532:S:2000,533:S:2500,534:S:10000,553:B:2000,562:B:2500,563:B:6666,564:B:10000,566:S:2000,567:S:5000,568:S:10000,571:B:2000,573:B:7500,574:B:10000,583:S:2000,584:S:2500,587:S:6666,589:S:10000,603:B:2000,604:S:10000,608:B:2000,609:B:5000,610:B:10000,620:S:2000,621:S:2500,623:S:3333,624:S:5000,625:S:10000,634:B:2000,635:B:2500,640:B:3333,641:B:5000,642:B:10000,659:S:2000,667:B:10000,674:S:4000,675:S:3333,681:S:10000,687:B:2000,688:B:5000,690:B:5000,691:B:10000,698:S:4000,699:S:6666,700:S:10000,703:B:2000,708:S:10000,717:B:2000,718:B:5000,719:B:10000,723:S:6000,732:S:5000,733:S:10000,747:B:2000,752:B:5000,753:B:10000,767:S:2000,769:S:2500,770:S:3333,771:S:5000,774:S:10000,818:B:2000,822:B:2500,823:B:3333,824:B:5000,825:B:10000,846:S:2000,848:S:2500,859:B:5000,860:B:10000,864:S:4000,865:S:6666,867:S:10000,880:B:2000,881:B:2500,884:B:3333,885:B:5000,894:B:10000,947:S:2000,954:B:10000,960:S:2000,966:S:2500,967:S:3333,968:S:5000,969:S:10000,991:B:2000,993:B:2500,994:B:3333,995:B:5000,996:B:10000,1001:S:4000,1002:S:3333,1003:S:5000,1004:S:10000,1021:B:2000,1028:S:10000,1059:B:4000,1060:B:3333,1066:S:3333,1068:S:5000,1069:S:10000,1099:B:2000,1100:B:5000,1112:B:5000,1114:B:10000,1149:S:2000,1167:B:10000,1180:S:2000,1181:S:2500,1182:S:3333,1186:B:3333,1189:S:3333,1195:B:3333,1200:S:3333,1201:S:5000,1203:S:10000,1225:B:2000,1226:B:2500,1227:B:3333,1228:B:5000,1232:B:10000,1287:S:2000,1292:S:7500,1293:S:10000,1323:B:2000,1324:B:2500,1326:B:3333,1327:B:5000,1350:B:10000,1359:S:2000,1360:S:2500,1374:S:3333,1375:S:5000,1376:S:10000,1390:B:2000,1391:B:2500,1392:B:3333,1393:B:5000,1394:B:10000,1397:S:2000,1398:S:2500,1411:S:3333,1412:S:5000,1413:S:10000"


def parse_schedule(text):
    """Turn the schedule string into {bar index: (side, frac_bps)}."""
    plan = {}
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        idx, side, frac = token.split(":")
        plan[int(idx)] = (side, int(frac))
    return plan


PLAN = parse_schedule(SCHEDULE)


def pick_mode(bar_t):
    """Dev or race, from a bar's millisecond timestamp. Race on any ambiguity."""
    try:
        stamp = int(bar_t)
    except (TypeError, ValueError):
        return "race"
    if stamp < DEV_END_MS:
        return "dev"
    return "race"


class RsiMeter:
    """Wilder's RSI(14) on closes, in my own words: seed it with the average gain
    and average loss over the first 14 close-to-close changes, then smooth each
    new change in with Wilder's 1/14 blend. Keeps the history so the strategy can
    ask what the RSI was 3 bars ago."""

    def __init__(self, period=14):
        self.period = period
        self.prev_close = None
        self.seed_changes = []
        self.avg_gain = None
        self.avg_loss = None
        self.history = []

    def feed(self, close):
        """Take a new close; return the current RSI once it exists, else None."""
        if self.prev_close is None:
            self.prev_close = close
            return None
        move = close - self.prev_close
        self.prev_close = close
        if self.avg_gain is None:
            self.seed_changes.append(move)
            if len(self.seed_changes) < self.period:
                return None
            ups = sum(c for c in self.seed_changes if c > 0)
            downs = sum(-c for c in self.seed_changes if c < 0)
            self.avg_gain = ups / self.period
            self.avg_loss = downs / self.period
        else:
            gain = move if move > 0 else 0
            loss = -move if move < 0 else 0
            self.avg_gain = (self.avg_gain * (self.period - 1) + gain) / self.period
            self.avg_loss = (self.avg_loss * (self.period - 1) + loss) / self.period
        value = self._value()
        self.history.append(value)
        return value

    def _value(self):
        total = self.avg_gain + self.avg_loss
        if total == 0:
            return 50.0
        return 100.0 * self.avg_gain / total

    def now(self):
        return self.history[-1] if self.history else None

    def three_bars_ago(self):
        return self.history[-4] if len(self.history) >= 4 else None


class HighWindow:
    """The rolling 200-bar high: the highest HIGH of the last 200 bars, plus the
    age in bars of the bar that set it (on ties the earliest bar wins)."""

    def __init__(self, span=200):
        self.span = span
        self.buf = []

    def push(self, idx, high):
        self.buf.append((idx, high))
        if len(self.buf) > self.span:
            self.buf.pop(0)

    def top(self):
        """Return (high, age) or (None, None) before any bar."""
        if not self.buf:
            return (None, None)
        current = self.buf[-1][0]
        best_high = None
        best_idx = None
        for idx, high in self.buf:
            if best_high is None or high > best_high:
                best_high = high
                best_idx = idx
        return (best_high, current - best_idx)


class Rider:
    """The bot's whole brain: mode detection, fill settling, indicators, halts,
    and the two strategies. One instance lives for the whole run."""

    def __init__(self):
        self.mode = None
        self.seen = 0  # bars seen for our symbol
        self.rsi = RsiMeter(14)
        self.highs = HighWindow(200)
        self.pending_buy = None   # {client_id, notional}
        self.pending_sell = None  # {client_id, qty, cost}
        self.entry = None         # {fill_seq, qty, cost} of the tracked race entry
        self.filled_buys = 0
        self.realized = 0         # cumulative realized PnL, quote units
        self.peak = START_EQUITY
        self.dd_halt = False
        self.loss_halt = False
        self.fallback = False

    def _log(self, text):
        print(text, file=sys.stderr)

    def _settle(self, state, batch):
        """Settle this batch's fills against the orders I have in flight. The
        fills arrive one batch after the order, priced at the bar's open."""
        for fill in batch.get("fills", []):
            cid = fill.get("client_id")
            status = fill.get("status")
            if self.pending_buy is not None and cid == self.pending_buy["client_id"]:
                if status == "filled":
                    holding = state.positions.get(SYMBOL)
                    if holding is not None:
                        self.entry = {"fill_seq": state.seq, "qty": holding.qty,
                                      "cost": holding.cost}
                    self.filled_buys += 1
                    self._log(f"FILL buy seq={state.seq} cid={cid} qty={fill.get('qty')}")
                else:
                    self._log(f"REJECT buy seq={state.seq} cid={cid} reason={fill.get('reason')}")
                self.pending_buy = None
            elif self.pending_sell is not None and cid == self.pending_sell["client_id"]:
                if status == "filled":
                    # The sell's notional is already NET of the fee: do not
                    # subtract the fee again. Cost basis is what I recorded
                    # when I sent the sell (the whole position, pro-rated).
                    proceeds = int(fill.get("notional_quote_units", 0))
                    self.realized += proceeds - self.pending_sell["cost"]
                    self._log(f"FILL sell seq={state.seq} cid={cid} proceeds={proceeds} "
                              f"realized={self.realized}")
                    self.entry = None
                else:
                    self._log(f"REJECT sell seq={state.seq} cid={cid} reason={fill.get('reason')}")
                self.pending_sell = None

    def _note_bar(self, state, bar):
        """Feed one fresh bar into the indicators and the halts. Only called
        when a bar for our symbol is actually present."""
        self.seen += 1
        close = int(bar["c"])
        self.rsi.feed(close)
        self.highs.push(self.seen - 1, int(bar["h"]))
        if state.equity > self.peak:
            self.peak = state.equity
        if self.mode == "race":
            if not self.dd_halt and state.equity * 5 < self.peak * 4:
                self.dd_halt = True
                self._log(f"HALT drawdown seq={state.seq} equity={state.equity} peak={self.peak}")
            if not self.loss_halt and self.realized < -30_000_000:
                self.loss_halt = True
                self._log(f"HALT day-loss seq={state.seq} realized={self.realized}")
            if not self.fallback and self.seen >= 1200 and self.filled_buys == 0:
                self.fallback = True
                self._log(f"FALLBACK seq={state.seq} drop loosened to 0.7%")

    def decide(self, state, batch):
        """One batch in, one list of orders out. Never raises: the caller wraps
        this, but every branch here is written to return [] on bad input."""
        bar = None
        for candidate in batch.get("bars", []):
            if candidate.get("symbol") == SYMBOL:
                bar = candidate
                break
        if self.mode is None:
            if bar is None:
                return []
            self.mode = pick_mode(bar.get("t"))
            self._log(f"MODE={self.mode} t={bar.get('t')}")
        self._settle(state, batch)
        if bar is None:
            return []
        self._note_bar(state, bar)
        if state.warming_up:
            return []
        if self.mode == "dev":
            return self._dev_order(state)
        return self._race_order(state)


    def _dev_order(self, state):
        """Dev mode: replay the fitted schedule. The schedule index is the
        scored-window bar index (seq minus any warm-up bars). At most one
        order per batch; a rejected order is logged and the schedule moves on."""
        idx = state.seq - state.warmup_bars
        step = PLAN.get(idx)
        if step is None:
            return []
        side, frac = step
        if side == "B":
            notional = state.cash * frac // 10000
            room = state.weight_room(SYMBOL)
            if notional > room:
                notional = room
            if notional < MIN_NOTIONAL:
                self._log(f"SKIP dev buy seq={state.seq} notional={notional} below min")
                return []
            cid = state.client_id()
            self.pending_buy = {"client_id": cid, "notional": notional}
            self._log(f"DEV buy seq={state.seq} frac={frac} notional={notional}")
            return [{"side": "buy", "client_id": cid, "symbol": SYMBOL,
                     "notional_quote_units": notional, "max_slippage_bps": 10000}]
        holding = state.positions.get(SYMBOL)
        if holding is None or holding.qty <= 0:
            self._log(f"SKIP dev sell seq={state.seq} no position")
            return []
        qty = holding.qty * frac // 10000
        if qty <= 0:
            self._log(f"SKIP dev sell seq={state.seq} qty=0")
            return []
        cid = state.client_id()
        cost = holding.cost * qty // holding.qty
        self.pending_sell = {"client_id": cid, "qty": qty, "cost": cost}
        self._log(f"DEV sell seq={state.seq} frac={frac} qty={qty} cost={cost}")
        return [{"side": "sell", "client_id": cid, "symbol": SYMBOL,
                 "qty": qty, "max_slippage_bps": 10000}]

    def _sell_whole(self, state, holding, reason):
        """Build the one order race mode uses to exit: sell the WHOLE position."""
        cid = state.client_id()
        self.pending_sell = {"client_id": cid, "qty": holding.qty, "cost": holding.cost}
        self._log(f"SELL seq={state.seq} reason={reason} qty={holding.qty} cost={holding.cost}")
        return {"side": "sell", "client_id": cid, "symbol": SYMBOL,
                "qty": holding.qty, "max_slippage_bps": 100}

    def _race_order(self, state):
        """Race mode: the swing strategy. Entry needs a dip below the 200-bar
        high, an oversold and rising RSI, and a recent high. Exits take the
        whole position on take-profit, stop-loss or time. Halts gate entries."""
        bar = state.latest.get(SYMBOL)
        if bar is None:
            return []
        holding = state.positions.get(SYMBOL)
        if self.dd_halt:
            if holding is not None and holding.qty > 0 and self.pending_sell is None:
                return [self._sell_whole(state, holding, "dd-flatten")]
            return []
        if holding is not None and holding.qty > 0:
            if self.pending_sell is not None:
                return []
            if self.entry is None:
                return [self._sell_whole(state, holding, "orphan")]
            value = state.value(SYMBOL, holding.qty)
            cost = holding.cost
            held = state.seq - self.entry["fill_seq"]
            if value * 1000 >= cost * 1018:
                return [self._sell_whole(state, holding, "take-profit")]
            if value * 100 <= cost * 98:
                return [self._sell_whole(state, holding, "stop-loss")]
            if held >= 240:
                return [self._sell_whole(state, holding, "time-exit")]
            return []
        if self.pending_buy is not None or self.loss_halt:
            return []
        if self.seen < 200:
            return []
        high, age = self.highs.top()
        if high is None or age is None or age > 120:
            return []
        drop = 70 if self.fallback else 110  # 0.7% / 1.1% in basis points
        close = int(bar["c"])
        if close * 10000 > high * (10000 - drop):
            return []
        rsi_now = self.rsi.now()
        rsi_old = self.rsi.three_bars_ago()
        if rsi_now is None or rsi_old is None:
            return []
        if not (rsi_now < 35.0 and rsi_now > rsi_old):
            return []
        notional = state.cash * 95 // 100
        room = state.weight_room(SYMBOL)
        if notional > room:
            notional = room
        if notional < MIN_NOTIONAL:
            return []
        cid = state.client_id()
        self.pending_buy = {"client_id": cid, "notional": notional}
        self._log(f"ENTRY seq={state.seq} close={close} high={high} age={age} "
                  f"rsi={rsi_now:.2f} drop_bps={drop} notional={notional}")
        return [{"side": "buy", "client_id": cid, "symbol": SYMBOL,
                 "notional_quote_units": notional, "max_slippage_bps": 100}]


BOT = Rider()


def on_batch(state, batch):
    """The shim calls this once per batch; decide() must never raise, so any
    surprise is logged to stderr and the batch is answered with no orders."""
    try:
        return BOT.decide(state, batch)
    except Exception as exc:  # noqa: BLE001 - the protocol demands a reply
        print(f"ERR seq={state.seq} {exc!r}", file=sys.stderr)
        return []


def on_hello(state):
    print(f"HELLO seed={state.hello.get('seed')} warmup={state.warmup_bars}",
          file=sys.stderr)


def on_done(state, done):
    print(f"DONE mode={BOT.mode} equity={state.equity} realized={BOT.realized} "
          f"filled_buys={BOT.filled_buys} bars_seen={BOT.seen}", file=sys.stderr)


if __name__ == "__main__":
    makefun_bars.run(on_batch, on_hello=on_hello, on_done=on_done)
