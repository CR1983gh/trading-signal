#!/usr/bin/env python3
"""
PrimeTrading-style daily signal engine (Alex's Swing Trading System).
Implements: 21dma-structure (EMA of highs/closes/lows), ATR, RS rank,
McClellan-style breadth (MCO/MCSI approximated over the liquid universe),
pullback scan, focus list, market gate.

Data: Yahoo Finance chart API (no key). Output: JSON state + German report text.
NOT financial advice — signal service only.
"""
import json, math, os, sys, time, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def fetch_chart(symbol, range_="2y", interval="1d", retries=3):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?range={range_}&interval={interval}&events=div%2Csplit")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.load(r)
            res = d["chart"]["result"][0]
            ts = res["timestamp"]
            q = res["indicators"]["quote"][0]
            rows = []
            for i, t in enumerate(ts):
                o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
                if c is None or h is None or l is None:
                    continue
                rows.append({"t": t, "o": o or c, "h": h, "l": l, "c": c, "v": v or 0})
            return rows, res.get("meta", {})
        except Exception as e:
            if attempt == retries - 1:
                return None, {"error": str(e)}
            time.sleep(1.5 * (attempt + 1))


def ema(values, period):
    k = 2.0 / (period + 1)
    out = []
    prev = None
    for v in values:
        prev = v if prev is None else (v * k + prev * (1 - k))
        out.append(prev)
    return out


def atr(rows, period=14):
    trs = []
    for i, r in enumerate(rows):
        if i == 0:
            trs.append(r["h"] - r["l"])
        else:
            pc = rows[i - 1]["c"]
            trs.append(max(r["h"] - r["l"], abs(r["h"] - pc), abs(r["l"] - pc)))
    return ema(trs, period)


def structure(rows, length=21):
    """21dma-structure: EMA of highs (top band), closes (mid), lows (bottom band)."""
    hi = ema([r["h"] for r in rows], length)
    cl = ema([r["c"] for r in rows], length)
    lo = ema([r["l"] for r in rows], length)
    return hi, cl, lo


def rising(series, n=3):
    if len(series) < n + 1:
        return False
    return series[-1] > series[-1 - n]


def rs_rank(closes_by_symbol, w=(21, 63, 126, 252)):
    """Composite RS: weighted multi-horizon performance + proximity to 52w high.
    Returns dict symbol -> percentile rank 1-99 (higher = stronger)."""
    raw = {}
    for sym, closes in closes_by_symbol.items():
        if len(closes) < 253:
            continue
        perf = 0.0
        total_w = 0
        for p, wt in zip(w, (0.25, 0.25, 0.25, 0.25)):
            if len(closes) > p:
                perf += wt * (closes[-1] / closes[-1 - p] - 1.0)
                total_w += wt
        perf /= total_w if total_w else 1
        hi52 = max(closes[-252:])
        lo52 = min(closes[-252:])
        prox = (closes[-1] - lo52) / (hi52 - lo52) if hi52 > lo52 else 0.5
        raw[sym] = perf + 0.3 * prox
    ranked = sorted(raw.items(), key=lambda kv: kv[1])
    n = len(ranked)
    return {s: round(1 + 98 * i / max(n - 1, 1)) for i, (s, _) in enumerate(ranked)}, raw


def mcclellan(up_counts, down_counts):
    """McClellan-style over provided daily A/D counts (approximation of NYSE/NDX)."""
    net = [u - d for u, d in zip(up_counts, down_counts)]
    e19 = ema(net, 19)
    e39 = ema(net, 39)
    mco = [a - b for a, b in zip(e19, e39)]
    mcsi = []
    acc = 0.0
    for m in mco:
        acc += m
        mcsi.append(acc)
    mcsi_10 = ema(mcsi, 10)
    # rolling sigma of MCO for z-scores
    n = len(mco)
    window = mco[-120:] if n >= 120 else mco
    mean = sum(window) / len(window)
    var = sum((x - mean) ** 2 for x in window) / len(window)
    sd = math.sqrt(var) if var > 0 else 1.0
    return mco, mcsi, mcsi_10, mean, sd


EXCHANGE_MAP = {"NMS": "NASDAQ", "NGM": "NASDAQ", "NAS": "NASDAQ",
               "NYQ": "NYSE", "NYS": "NYSE", "NCM": "NASDAQ",
               "GER": "XETRA"}


def tv_link(symbol, exchange):
    """TradingView deep link: opens app on Android via tvchart://, web fallback."""
    ex = EXCHANGE_MAP.get(exchange)
    if not ex:
        return "https://www.tradingview.com/chart/?symbol=" + symbol
    full = f"{ex}:{symbol.replace('.DE','')}" if ex == "XETRA" else f"{ex}:{symbol}"
    return full


def analyze_symbol(rows):
    if not rows or len(rows) < 260:
        return None
    hi, cl, lo = structure(rows, 21)
    a = atr(rows, 14)[-1]
    c = rows[-1]["c"]
    ema21_lo, ema21_mid = lo[-1], cl[-1]
    sma50 = sum(r["c"] for r in rows[-50:]) / 50
    dist_ema21_atr = (c - ema21_mid) / a if a else 99
    dist_sma50_atr = (c - sma50) / a if a else 99
    adr_pct = ((sum(r["h"] - r["l"] for r in rows[-21:]) / 21) / c) * 100
    vol_avg_dollar = sum(r["v"] * r["c"] for r in rows[-21:]) / 21
    vol_avg_shares = sum(r["v"] for r in rows[-21:]) / 21
    # contraction: range of last 5 closes vs ATR
    last5 = [r["c"] for r in rows[-5:]]
    contraction = (max(last5) - min(last5)) < 1.2 * a
    struct_rising = rising(cl, 3) and rising(lo, 3)
    above_all = c > hi[-1] and c > cl[-1] and c > lo[-1]
    below_all = c < lo[-1]
    broke_low = rows[-1]["c"] < lo[-1] and rows[-2]["c"] >= lo[-2]
    reclaim = rows[-1]["c"] > hi[-1] and rows[-2]["c"] <= hi[-2]
    closes = [r["c"] for r in rows]
    N = 60  # chart history kept per symbol for GUI
    return {
        "close": c, "ema21_hi": hi[-1], "ema21_mid": cl[-1], "ema21_lo": lo[-1],
        "sma50": sma50, "atr": a, "adr_pct": adr_pct,
        "dist_ema21_atr": dist_ema21_atr, "dist_sma50_atr": dist_sma50_atr,
        "dollar_vol": vol_avg_dollar, "share_vol": vol_avg_shares,
        "contraction": contraction, "struct_rising": struct_rising,
        "above_all": above_all, "below_all": below_all,
        "broke_low": broke_low, "reclaim": reclaim,
        "closes": closes,
        "chart": {
            "c": [round(x, 2) for x in closes[-N:]],
            "e_mid": [round(x, 2) for x in cl[-N:]],
            "e_lo": [round(x, 2) for x in lo[-N:]],
            "e_hi": [round(x, 2) for x in hi[-N:]],
        },
    }


_CRUMB_CACHE = {"done": False, "val": None}

def _get_crumb():
    if _CRUMB_CACHE["done"]:
        return _CRUMB_CACHE["val"]
    _CRUMB_CACHE["done"] = True
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [("User-Agent", UA["User-Agent"])]
    try:
        opener.open("https://fc.yahoo.com", timeout=15)
    except Exception:
        pass
    crumb = opener.open("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=15).read().decode().strip()
    _CRUMB_CACHE["val"] = (opener, crumb)
    return _CRUMB_CACHE["val"]


def earnings_within_n_days(symbol, n=7, ref_ts=None):
    """Best-effort via Yahoo calendarEvents (quoteSummary + crumb). True/False/None.
    ref_ts: unix timestamp to measure 'now' from (for as-of simulations)."""
    if ref_ts is None:
        ref_ts = time.time()
    try:
        opener, crumb = _get_crumb()
        url = (f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
               f"?modules=calendarEvents&crumb={crumb}")
        with opener.open(url, timeout=20) as r:
            d = json.load(r)
        ev = d["quoteSummary"]["result"][0].get("calendarEvents", {}).get("earnings", {})
        dates = ev.get("earningsDate", [])
        for dd in dates:
            ts = dd.get("raw")
            if ts and ts <= ref_ts + n * 86400 and ts >= ref_ts - 86400:
                return True
        return False
    except Exception:
        return None  # unknown -> don't block, flag in report


def load_tg_map():
    path = os.path.join(HERE, "tradegate_map.json")
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except Exception:
            return {}
    return {}


def check_positions(ana, fx=None):
    """Check user's personal watchlist positions against today's close.
    Sell signal: Tagesschluss unter Stop. Stop None -> aktuelle 21-EMA-Low."""
    try:
        from positions import load as load_positions
        plist = load_positions()
    except Exception:
        plist = []
    out = []
    for p in plist:
        sym = p["symbol"]
        a = ana.get(sym)
        if not a:
            out.append({**p, "status": "NO_DATA", "close": None})
            continue
        stop = p.get("stop")
        stop_src = "manuell"
        if stop is None:
            stop = a["ema21_lo"]
            stop_src = "21-EMA-Low"
        close = a["close"]
        pnl_pct = (close / p["entry"] - 1) * 100 if p.get("entry") else None
        if close < stop:
            status = "SELL"  # Tagesschluss unter Stop -> Verkaufssignal
        elif pnl_pct is not None and pnl_pct >= 100:  # placeholder never triggers without 2R check
            status = "HOLD"
        else:
            status = "HOLD"
        # 2R check: close >= entry + 2*(entry-stop) -> trim hint
        trim_reached = False
        if p.get("entry") and stop and p["entry"] > stop:
            r2 = p["entry"] + 2 * (p["entry"] - stop)
            trim_reached = close >= r2
        item = {
            **p, "stop": round(stop, 2), "stop_src": stop_src,
            "close": round(close, 2), "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            "status": status, "trim_reached": trim_reached,
            "ccy": "EUR" if sym.endswith(".DE") else "USD",
        }
        if fx and item["ccy"] == "USD":
            item["eur"] = {"close": round(close / fx, 2), "stop": round(stop / fx, 2),
                          "entry": round(p["entry"] / fx, 2) if p.get("entry") else None}
        out.append(item)
    return out


def run(as_of=None):
    """as_of: 'YYYY-MM-DD' -> simulate run as of that day's close (data truncated)."""
    from universe import US_TICKERS, DE_TICKERS, MARKET_REFERENCES
    tg_map = load_tg_map()
    mkt_ref = MARKET_REFERENCES["market"]
    all_syms = list(dict.fromkeys(US_TICKERS + DE_TICKERS + [mkt_ref]))
    asof_ts = None
    if as_of:
        asof_ts = datetime.strptime(as_of, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc).timestamp()
    data = {}
    exchanges = {}
    for sym in all_syms:
        rows, meta = fetch_chart(sym)
        if rows:
            if asof_ts:
                rows = [r for r in rows if r["t"] <= asof_ts]
            data[sym] = rows
            exchanges[sym] = meta.get("exchangeName", "")
        time.sleep(0.15)

    # per-symbol analysis
    ana = {}
    for sym, rows in data.items():
        a = analyze_symbol(rows)
        if a:
            ana[sym] = a

    # breadth: daily up/down counts across combined universe (approximation)
    # align by date index from the end
    def updown(rows):
        ups, downs = [], []
        for i in range(1, len(rows)):
            ups.append(1 if rows[i]["c"] > rows[i - 1]["c"] else 0)
            downs.append(1 if rows[i]["c"] < rows[i - 1]["c"] else 0)
        return ups, downs

    up_series, down_series = [], []
    L = min(len(r) - 1 for r in data.values())
    for k in range(L):
        u = d = 0
        for rows in data.values():
            i = len(rows) - L + k
            if rows[i]["c"] > rows[i - 1]["c"]:
                u += 1
            elif rows[i]["c"] < rows[i - 1]["c"]:
                d += 1
        up_series.append(u)
        down_series.append(d)

    mco, mcsi, mcsi10, mco_mean, mco_sd = mcclellan(up_series, down_series)
    mco_now = mco[-1]
    mco_z = (mco_now - mco_mean) / mco_sd
    mcsi_curl_up = mcsi[-1] > mcsi[-2] > mcsi[-3] or mcsi[-1] > mcsi[-2]
    mcsi_reclaim_10 = mcsi[-1] > mcsi10[-1] and mcsi[-2] <= mcsi10[-2]
    mcsi_above_10 = mcsi[-1] > mcsi10[-1]
    mcsi_curl_down = mcsi[-1] < mcsi[-2] < mcsi[-3] or mcsi[-1] < mcsi[-2]

    # chart history (last 90 sessions) for GUI graphics
    HIST_N = 90
    hist = {
        "mco": [round(x, 2) for x in mco[-HIST_N:]],
        "mcsi": [round(x, 1) for x in mcsi[-HIST_N:]],
        "mcsi10": [round(x, 1) for x in mcsi10[-HIST_N:]],
    }

    # market gate (QQQE structure)
    mkt = MARKET_REFERENCES["market"]
    mkt_ana = ana.get(mkt)
    mkt_above_rising = bool(mkt_ana and mkt_ana["close"] > mkt_ana["ema21_mid"] and mkt_ana["struct_rising"])
    mkt_reclaim = bool(mkt_ana and mkt_ana["reclaim"])

    # market regime classification
    if mkt_above_rising and mcsi_above_10:
        regime = "UPTREND_CONFIRMED"
        stance = "Aggressiv: Pullbacks in Leader kaufen, bei Bestätigung 0,5% Risiko."
    elif mkt_reclaim or (mkt_ana and mkt_ana["close"] > mkt_ana["ema21_mid"]):
        regime = "REPAIR_TEST"
        stance = "Vorsichtig testen: Pilot-Positionen 0,125-0,25% Risiko, nur Top-Leader."
    elif mkt_ana and mkt_ana["below_all"]:
        regime = "BREAKDOWN"
        stance = "Kein neues Risiko. Kapital schützen, Structure-Rebuild abwarten."
    else:
        regime = "NEUTRAL_CHOP"
        stance = "Abwarten. Nur High-Conviction-Setups minimaler Größe."

    # RS ranks
    closes_by_symbol = {s: a["closes"] for s, a in ana.items()}
    rs, _ = rs_rank(closes_by_symbol)

    # Liquid Leaders filter (Alex's scan, adapted) + Tradegate tradability gate:
    # EUR-tradable on Tradegate with spread <= 1.0% and daily EUR volume >= 500k.
    leaders = []
    for sym, a in ana.items():
        if a["dollar_vol"] < 100e6:
            continue
        if a["share_vol"] < 1e6:
            continue
        if a["close"] < 10:
            continue
        if not (3.0 <= a["adr_pct"] <= 15.0):
            continue
        if rs.get(sym, 0) < 70:
            continue
        tg = tg_map.get(sym) or {}
        spread = tg.get("spread_pct")
        vol = tg.get("eur_volume")
        if not tg.get("isin") or spread is None or spread > 1.0:
            continue
        if vol is not None and vol < 100_000:
            continue
        leaders.append(sym)

    # FX rate for EUR display (USD->EUR). DE tickers are already EUR.
    fx = None
    try:
        from tradegate_resolve import eurusd_rate
        fx = eurusd_rate()
    except Exception:
        fx = None

    # Pullback setup scan
    setups = []
    for sym in leaders:
        a = ana[sym]
        if not a["struct_rising"]:
            continue
        if not (0.0 <= a["dist_ema21_atr"] <= 1.0):
            continue
        if not (-0.5 <= a["dist_sma50_atr"] <= 4.0):
            continue
        earn_soon = earnings_within_n_days(sym, 7, ref_ts=asof_ts)
        if earn_soon is True:
            continue
        entry_zone = (a["ema21_lo"], a["ema21_hi"])
        stop = a["ema21_lo"]
        risk_per_share = a["close"] - stop
        if risk_per_share <= 0:
            continue
        target_2r = a["close"] + 2 * risk_per_share
        # EUR display: DE tickers already EUR; US converted via EURUSD (USD->EUR = /fx)
        is_de = sym.endswith(".DE")
        if is_de:
            eur = {"entry_zone": entry_zone, "stop": stop, "target_2r": target_2r, "close": a["close"]}
        elif fx:
            eur = {"entry_zone": (entry_zone[0] / fx, entry_zone[1] / fx),
                   "stop": stop / fx, "target_2r": target_2r / fx, "close": a["close"] / fx}
        else:
            eur = None
        if eur:
            ez = eur["entry_zone"]
            eur = {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in eur.items()}
            eur["entry_zone"] = [round(ez[0], 2), round(ez[1], 2)]
        setups.append({
            "symbol": sym, "rs": rs.get(sym), "close": a["close"],
            "ccy": "EUR" if is_de else "USD",
            "eur": {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in eur.items()} if eur else None,
            "tv": tv_link(sym, exchanges.get(sym, "")),
            "tg_isin": (tg_map.get(sym) or {}).get("isin"),
            "tg_spread": (tg_map.get(sym) or {}).get("spread_pct"),
            "entry_zone": entry_zone, "stop": stop, "target_2r": target_2r,
            "dist_atr": a["dist_ema21_atr"], "contraction": a["contraction"],
            "earnings_unknown": earn_soon is None,
            "chart": a["chart"],
            # BUY NOW: Tagesschluss liegt IN der Entry-Zone -> Limitorder zum Schlusskurs moeglich
            "buy_now": (entry_zone[0] <= a["close"] <= entry_zone[1]),
            # Risk: prozentualer Abstand Schlusskurs -> Stop. Ideal <= 5%.
            "stop_pct": round(risk_per_share / a["close"] * 100.0, 2),
            "stop_pct_ok": (risk_per_share / a["close"] * 100.0) <= 5.0,
        })
    setups.sort(key=lambda s: (-s["rs"], s["dist_atr"]))
    focus = setups[:5]

    # Quality score per setup (Alex's tie-break priorities from the docs):
    # RS (relative strength) 45%, proximity to structure 30%,
    # contraction 15%, earnings cleanliness 10%.
    for s in setups:
        rs_n = s["rs"] / 99.0
        prox = max(0.0, min(1.0, 1.0 - s["dist_atr"]))  # 0..1xATR -> 1..0
        contr = 1.0 if s["contraction"] else 0.0
        earn = 0.5 if s["earnings_unknown"] else 1.0
        score = 0.45 * rs_n + 0.30 * prox + 0.15 * contr + 0.10 * earn
        s["score"] = round(score, 3)
        s["grade"] = "green" if score >= 0.72 else ("yellow" if score >= 0.58 else "red")
    setups.sort(key=lambda s: -s["score"])
    focus = setups[:5]

    # structure breaks for previously signaled names (state diff)
    state_path = os.path.join(HERE, "state_sim.json" if as_of else "state.json")
    prev = {}
    if os.path.exists(state_path):
        try:
            prev = json.load(open(state_path))
        except Exception:
            prev = {}
    breaks = [s for s in ana if s in prev.get("focus", []) and ana[s]["broke_low"]]
    reclaims = [s for s in ana if s in prev.get("focus", []) and ana[s]["reclaim"]]

    # personal watchlist check
    positions = check_positions(ana, fx=fx)

    state = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "regime": regime, "stance": stance,
        "mco": mco_now, "mco_z": mco_z,
        "mcsi": mcsi[-1], "mcsi_above_10": mcsi_above_10,
        "mcsi_reclaim_10": mcsi_reclaim_10, "mcsi_curl_up": mcsi_curl_up,
        "mcsi_curl_down": mcsi_curl_down,
        "market_ref": mkt, "market_above_rising_21": mkt_above_rising,
        "market_reclaim": mkt_reclaim,
        "market_chart": mkt_ana["chart"] if mkt_ana else None,
        "hist": hist,
        "fx_usd_eur": round(fx, 4) if fx else None,
        "leaders_count": len(leaders),
        "focus": [s["symbol"] for s in focus],
        "setups": setups, "breaks": breaks, "reclaims": reclaims,
        "positions": positions,
    }
    with open(state_path, "w") as f:
        json.dump(state, f, indent=1)
    with open(os.path.join(HERE, f"report_{state['generated_utc'][:10]}.json"), "w") as f:
        json.dump(state, f, indent=1)
    return state


if __name__ == "__main__":
    st = run()
    print(json.dumps({k: v for k, v in st.items() if k != "setups"}, indent=1))
    print("SETUPS:", json.dumps(st["setups"][:8], indent=1))
