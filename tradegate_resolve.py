#!/usr/bin/env python3
"""Resolve Yahoo tickers -> Tradegate ISINs and check EUR tradability + spread.
Uses tradegate.de/kurssuche.php (real search) + refresh.php (live quote).
Writes tradegate_map.json: {ticker: {isin, name, tg_ticker, spread_pct, eur_volume}}
Run manually to refresh the map; engine reads the map."""
import json, os, re, sys, time
import urllib.request
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


ROW_RE = re.compile(
    r'<tr class="[^"]*kurssuche_ergebnis[^"]*" onclick="window\.location=\'orderbuch\.php\?isin=([A-Z]{2}[A-Z0-9]{9}[0-9])\'">\s*'
    r'<td>\s*<a href="orderbuch\.php\?isin=[^"]+">(.*?)</a>.*?'
    r'<td class="middle"[^>]*>([A-Z]{2}[A-Z0-9]{9}[0-9])</td>\s*'
    r'<td class="middle">([^<]*)</td>\s*'
    r'<td class="middle">([^<]*)</td>', re.S)


def search_rows(query):
    try:
        html = http_get("https://www.tradegate.de/kurssuche.php?suche=" + urllib.parse.quote(query))
    except Exception:
        return []
    rows = []
    for m in ROW_RE.finditer(html):
        isin, name_html, isin2, wkn, ticker = m.groups()
        name = re.sub(r"<[^>]+>", "", name_html).replace("&nbsp;", " ").strip()
        # bonds/certs contain these words or XS-prefix; plain equities don't
        bad = re.search(r"Notes|Nts|Anleihe|Bond|Call|Put|Zertifikat|Hypothek|Schuldvers|DL-|MTN|CVR|Warrant|Sub\.|Med\.", name, re.I) or isin.startswith("XS")
        rows.append({"isin": isin, "name": name, "wkn": wkn.strip(),
                    "ticker": ticker.strip(), "certificate": bool(bad)})
    return rows


# Manually verified Yahoo-ticker -> Tradegate ISIN overrides (price-checked 2026-09-27)
OVERRIDE = {
    "AVGO": "US11135F1012",   # Broadcom Corp, TG 309.90 vs YahooEUR 309.46
    "ASML": "NL0010273215",   # ASML Holding NL, TG 1525 vs YahooEUR 1529.64
    "NFLX": "US64110L1061",   # Netflix, TG 62.42 vs 62.41
    "YUM": "US9884981013",    # Yum Brands, TG 121.35 vs 121.59
    "MCD": "US5801351017",    # McDonald's, TG 207.60 vs 207.44
    "NSC": "US6558441084",    # Norfolk Southern, TG 274.00 vs 274.54
    "MUV2.DE": "DE0008430026",# Munich Re, TG 511.40 vs 510.40
    "HNR1.DE": "DE0008402215",# Hannover Rueck, TG 258.00 vs 257.80
    # --- expansion batch 2026-09-27 (all price-verified <1% diff) ---
    "ADI": "US0326541051",    # Analog Devices
    "MPWR": "US6098391054",   # Monolithic Power
    "TER": "US8807701029",    # Teradyne
    "SNPS": "US8716071076",   # Synopsys
    "CDNS": "US1273871087",   # Cadence Design
    "MELI": "US58733R1023",   # MercadoLibre
    "SHOP": "CA82509L1076",   # Shopify
    "APLD": "US0381692070",   # Applied Digital
    "WDC": "US9581021055",    # Western Digital
    "GEV": "US36828A1016",    # GE Vernova
    "CRCL": "US1725731079",   # Circle Internet Group
}


def search_isin(ticker, want_country, yahoo_eur=None, yahoo_names=()):
    """Match Tradegate search result by company name; validate by price sanity
    (TG last within 8% of Yahoo close, converted to EUR).
    Tries NAME_MAP query, then Yahoo longName/shortName.
    Handles both result-table hits and single direct-hit pages."""
    from name_map import NAME_MAP
    if ticker in OVERRIDE:
        r = quote(OVERRIDE[ticker])
        px = r.get("last") or ((r.get("bid") or 0) + (r.get("ask") or 0)) / 2
        if px and (not yahoo_eur or abs(px / yahoo_eur - 1) < 0.10):
            return {"isin": OVERRIDE[ticker], "name": ticker, "wkn": "", "ticker": "", "_quote": r}
    queries = []
    if NAME_MAP.get(ticker):
        queries.append(NAME_MAP[ticker])
    for n in yahoo_names:
        if n and n not in queries:
            queries.append(n)
    for query in queries:
        hit = _search_one(query, yahoo_eur)
        if hit:
            return hit
    return None


def _search_one(query, yahoo_eur=None):
    rows = search_rows(query)
    if not rows:
        # single-hit pages render a direct orderbuch view: the matched instrument is
        # in the JS var `var isin = "..."`
        try:
            html = http_get("https://www.tradegate.de/kurssuche.php?suche=" + urllib.parse.quote(query))
            m = re.search(r'var\s+isin\s*=\s*"([A-Z]{2}[A-Z0-9]{9}[0-9])"', html)
            if m:
                rows = [{"isin": m.group(1), "name": query, "wkn": "", "ticker": "", "certificate": False}]
        except Exception:
            return None
    # NOTE: no ISIN-country filter — many US-listed issuers are incorporated abroad
    # (ASML=NL, Eaton=IE...). The price-sanity check below is the real validator.
    cands = [r for r in rows if not r["certificate"]]
    if not cands:
        return None
    # prefer candidates whose name best matches the query (word overlap)
    qwords = [w for w in query.lower().replace(",", " ").split() if len(w) > 2]
    def name_score(r):
        nm = r["name"].lower()
        return sum(1 for w in qwords if w in nm)
    cands.sort(key=lambda r: -name_score(r))
    if yahoo_eur:
        for r in cands:
            q = quote(r["isin"])
            px = q.get("last") or ((q.get("bid") or 0) + (q.get("ask") or 0)) / 2
            if px and abs(px / yahoo_eur - 1) < 0.08:
                return {**r, "_quote": q}
        return None
    return cands[0]


def quote(isin):
    try:
        raw = http_get(f"https://www.tradegate.de/refresh.php?isin={isin}")
        d = json.loads(raw)
        def num(x):
            if isinstance(x, str):
                x = x.replace(" ", "").replace("\u00a0", "")
                if x in ("", "./.", "-", "--"):
                    return None
                return float(x.replace(",", "."))
            return float(x) if x is not None else None
        bid, ask = num(d.get("bid")), num(d.get("ask"))
        mid = (bid + ask) / 2 if bid and ask else None
        spread_abs = (ask - bid) if bid and ask else None
        spread_pct = (spread_abs / mid * 100) if spread_abs is not None and mid else None
        return {
            "bid": bid, "ask": ask, "last": num(d.get("last")),
            "spread_abs": spread_abs, "spread_pct": spread_pct,
            "eur_volume": num(d.get("umsatz")), "executions": d.get("executions"),
        }
    except Exception as e:
        return {"error": str(e)}


def eurusd_rate():
    from engine import fetch_chart
    for attempt in range(3):
        try:
            rows, _ = fetch_chart("EURUSD=X")
            if rows and rows[-1]["c"] > 0.5:
                return rows[-1]["c"]
        except Exception:
            pass
        time.sleep(2)
    return 1.0


def main():
    from universe import US_TICKERS, DE_TICKERS
    from engine import fetch_chart
    fx = eurusd_rate()
    print(f"EUR/USD = {fx:.4f}")
    tickers = US_TICKERS + DE_TICKERS
    out = {}
    for t in tickers:
        rows, meta = fetch_chart(t)
        yahoo_close = rows[-1]["c"] if rows else None
        want_country = "DE" if t.endswith(".DE") else "US"
        # convert yahoo USD close to EUR for sanity comparison (EURUSD = USD per EUR)
        yahoo_eur = yahoo_close / fx if (yahoo_close and want_country == "US") else yahoo_close
        names = [meta.get("longName"), meta.get("shortName")]
        names.insert(0, t.replace(".DE", ""))  # tradegate indexes WKN/ticker codes
        hit = search_isin(t, want_country, yahoo_eur, yahoo_names=[n for n in names if n])
        if not hit:
            out[t] = {"isin": None, "note": "not found/validated on tradegate"}
            print(f"{t:10} NOT FOUND")
            time.sleep(0.4)
            continue
        q = hit.get("_quote") or quote(hit["isin"])
        out[t] = {"isin": hit["isin"], "name": hit["name"], "tg_ticker": hit["ticker"], **q}
        sp = q.get("spread_pct")
        vol = q.get("eur_volume")
        print(f"{t:10} {hit['isin']}  tg={hit['ticker']:6} spread={('%.2f%%' % sp) if sp is not None else '?':>7}  vol={('%.0f EUR' % vol) if vol else '?':>12}  {hit['name'][:28]}")
        time.sleep(0.4)
    with open(os.path.join(HERE, "tradegate_map.json"), "w") as f:
        json.dump(out, f, indent=1)
    ok = sum(1 for v in out.values() if v.get("spread_pct") is not None)
    print(f"\nResolved+quoted: {ok}/{len(tickers)}")


if __name__ == "__main__":
    main()
