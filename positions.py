#!/usr/bin/env python3
"""Manage the user's personal position watchlist (positions.json).

Positions are added via Telegram ("ich habe SNOW zu 335 gekauft") by the agent,
checked daily by engine.py. Format:
[
  {"symbol": "SNOW", "entry": 335.0, "stop": 325.29, "date": "2026-09-27",
   "note": "Setup #1, Limit Schlusskurs"}
]
"""
import json, os, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "positions.json")


def load():
    if os.path.exists(PATH):
        try:
            return json.load(open(PATH))
        except Exception:
            return []
    return []


def save(positions):
    with open(PATH, "w") as f:
        json.dump(positions, f, indent=1)


def add(symbol, entry, stop=None, note=""):
    """Add a position. stop defaults to None -> engine uses current 21-EMA-low."""
    positions = load()
    positions = [p for p in positions if p["symbol"] != symbol]  # replace existing
    positions.append({
        "symbol": symbol.upper(),
        "entry": float(entry),
        "stop": float(stop) if stop is not None else None,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "note": note,
    })
    save(positions)
    return positions


def remove(symbol):
    positions = [p for p in load() if p["symbol"] != symbol.upper()]
    save(positions)
    return positions


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps(load(), indent=1))
    elif sys.argv[1] == "add":
        sym = sys.argv[2]
        entry = sys.argv[3]
        stop = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != "-" else None
        note = sys.argv[5] if len(sys.argv) > 5 else ""
        ps = add(sym, entry, stop, note)
        print(f"ADDED {sym} entry={entry} stop={stop} | total {len(ps)} positions")
    elif sys.argv[1] == "remove":
        ps = remove(sys.argv[2])
        print(f"REMOVED {sys.argv[2]} | total {len(ps)} positions")
