#!/usr/bin/env python3
"""DonAlt (@DonAlt) X-Sentiment-Indikator.

Zieht seine oeffentlichen Posts (twiscan/xitter-Mirrors, kein X-API-Key) und
scoret sie mit einem Bullisch/Baerisch-Lexikon + Positions-Signalen.
Ausgabe: donalt_sentiment.json  {signal: BULLISH|NEUTRAL|BEARISH, score, posts[]}

DonAlt-Stil (horizontal S/R, weekly/monthly closes, klare Invalidierung):
Positions-Statements ("bought", "longed", "not selling", "HODL") wiegen schwerer
als Grundstimmungs-Woerter.
"""
import datetime
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36"}
MIRRORS = [
    "https://twiscan.com/en/x/DonAlt",
    "https://xitter.cf/DonAlt",
]

# Gewichtetes Lexikon (lowercase regex-match). Bull-Liste positiv, Bear-Liste negativ.
BULL = {
    r"\bbullish\b": 2, r"bull market": 2,
    r"leg up": 2, r"explode": 2, r"parabolic": 3,
    r"new ath|ath is in sight|make a new ath|new all-time": 2,
    r"\bhodl\b": 2, r"no (serious )?resistance": 2, r"nothing (left )?in (the )?way": 2,
    r"looks excellent|still strong|looks good": 1, r"love to see": 1,
    r"reclaim|flipped? as support": 2,
    r"bull market is officially on": 3,
    r"shrugging off": 1,
}
BEAR = {
    r"\bbearish\b": -2, r"\bbear(?:tard(?:ing)?)?\b": -1,
    r"crash": -3, r"rekt": -2, r"pump and dump|dumped": -2,
    r"expect price down|down \d{1,3}%": -3, r"lost support": -3,
    r"disappointing": -2, r"taking profits": -1,
    r"hack": -3, r"black monday": -3,
    r"capitulate|capitulation": -2,
    r"miserable": -1,
}
# Positions-Signale wiegen schwerer (DonAlt handelt, was er sagt)
POS = {
    r"\bbought\b": 3, r"will buy|buying more|buy more|buy some": 3, r"longed": 3,
    r"not selling|won'?t sell|am i taking profits\? no": 3,
    r"ignore everything and hodl": 3,
    r"shorts? (from|into|here)|added shorts|hold my shorts": -3,
    r"stopped (out|longs)|closed (my )?longs": -3,
}
LEX = {**BULL, **BEAR, **POS}
THRESH = 2.5


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")


def parse_posts():
    """Datum + Text der Posts vom Twiscan-Mirror (Fallback: xitter-Mirror)."""
    import html as _html
    posts = []
    for base in MIRRORS:
        try:
            page = fetch(base)
        except Exception:
            continue
        txt = _html.unescape(re.sub(r"<[^>]+>", "\n", page))
        lines = [l.strip() for l in txt.split("\n") if l.strip()]
        for i, l in enumerate(lines):
            m = re.match(r"^(\d{4})\.(\d{2})\.(\d{2}) (\d{2}):(\d{2})$", l)
            if not m:
                continue
            body, j = [], i + 1
            while j < len(lines) and len(body) < 8:
                s = lines[j]
                if re.match(r"^\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}$", s):
                    break
                if re.match(r"^(@|\d{1,3}$|·|DonAlt\b|Vaxxed|Following|Followers|https?://|source post|verdict)", s):
                    break
                if re.fullmatch(r"[\d.,KM%–\-+ ]{1,10}", s):
                    j += 1
                    continue
                body.append(s)
                j += 1
            text = " ".join(body).strip()
            if len(text) < 12:
                continue
            dt = datetime.datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]))
            posts.append({"date": dt.isoformat(), "text": text[:400]})
        if posts:
            break
    seen, out = set(), []
    for p in sorted(posts, key=lambda x: x["date"], reverse=True):
        if p["text"][:80] in seen:
            continue
        seen.add(p["text"][:80])
        out.append(p)
    return out


def score_text(text):
    t = text.lower()
    score, hits = 0.0, []
    for pat, w in LEX.items():
        n = len(re.findall(pat, t))
        if n:
            score += w * n if abs(w) < 3 else w  # Positions-Signale zaehlen 1x
            hits.append(pat)
    return score, hits


def run(push=False):
    posts = parse_posts()
    if not posts:
        print("FEHLER: keine Posts von den Mirrors bekommen", file=sys.stderr)
        return 1
    scored = []
    for p in posts:
        s, hits = score_text(p["text"])
        scored.append({**p, "score": round(s, 1), "hits": hits[:6]})
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=14)).isoformat()
    window = [p for p in scored if p["date"] >= cutoff]
    use = window if len(window) >= 3 else scored[:10]
    # stark exponentieller Zeitverfall: aktueller Post zahlen am meisten
    now = datetime.datetime.utcnow()
    num = den = 0.0
    for p in use:
        age_d = (now - datetime.datetime.fromisoformat(p["date"])).total_seconds() / 86400.0
        w = 0.5 ** (age_d / 5.0)  # Halbwertszeit 5 Tage
        num += p["score"] * w
        den += max(w, 1e-9)
    agg = num / den
    signal = "BULLISH" if agg >= THRESH else ("BEARISH" if agg <= -THRESH else "NEUTRAL")
    latest = scored[0]
    out = {
        "handle": "DonAlt",
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "signal": signal,
        "avg_score": round(agg, 2),
        "n_posts_scored": len(use),
        "window_days": 14,
        "threshold": THRESH,
        "latest_post": {"date": latest["date"], "text": latest["text"], "score": latest["score"]},
        "posts": use[:15],
        "note": "Lexikon-Score ueber oeffentliche X-Posts via Mirror (kein X-API). DonAlt-Fokus: BTC/ETH.",
    }
    path = os.path.join(HERE, "donalt_sentiment.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"SIGNAL: {signal}  (Score {agg:+.2f}, {len(use)} Posts, 14d-Fenster)")
    print("Neuester Post:", latest["date"], "|", latest["text"][:120], f"| Score {latest['score']}")
    if push and os.environ.get("GITHUB_TOKEN"):
        push_api(out)
    return 0


def push_api(payload):
    import base64
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ.get("SIGNAL_REPO", "CR1983gh/trading-signal")
    api = f"https://api.github.com/repos/{repo}/contents/donalt_sentiment.json"

    def req(url, data=None, method=None):
        r = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        return json.load(urllib.request.urlopen(r))
    body = {
        "message": f"DonAlt sentiment {datetime.datetime.utcnow():%Y-%m-%d %H:%M}",
        "content": base64.b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode(),
        "branch": "main",
    }
    try:
        body["sha"] = req(api, method="GET")["sha"]
    except Exception:
        pass  # Datei existiert noch nicht
    req(api, data=json.dumps(body).encode(), method="PUT")
    print("pushed donalt_sentiment.json")


if __name__ == "__main__":
    sys.exit(run(push="--push" in sys.argv))
