#!/usr/bin/env python3
"""Format engine state as German Telegram report."""
import json, os, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

REGIME_EMOJI = {
    "UPTREND_CONFIRMED": "🟢 Aufwärtstrend bestätigt",
    "REPAIR_TEST": "🟡 Reparatur-Phase (Testen erlaubt)",
    "NEUTRAL_CHOP": "🟠 Neutral / Chop",
    "BREAKDOWN": "🔴 Breakdown — kein neues Risiko",
}

def fmt(x, d=2):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")

def main(state_file="state.json"):
    st = json.load(open(os.path.join(HERE, state_file)))
    lines = []
    day = st["generated_utc"][:10]
    lines.append(f"📊 *PrimeTrading-Signal — {day}*")
    lines.append("")
    lines.append(f"*Markt-Regime:* {REGIME_EMOJI.get(st['regime'], st['regime'])}")
    lines.append(f"_{st['stance']}_")
    lines.append("")
    mkt = st["market_ref"]
    lines.append(f"*Markt-Gate ({mkt}):* " +
                ("✅ über steigender 21dma-Struktur" if st["market_above_rising_21"] else "❌ nicht über steigender Struktur") +
                (" · Reclaim!" if st["market_reclaim"] else ""))
    z = st["mco_z"]
    mco_state = ("überverkauft ≤ -2σ 🎯" if z <= -2 else
                 "überverkauft ≤ -1σ ⚠️" if z <= -1 else
                 "neutral" if z < 1 else "überkauft")
    lines.append(f"*MCO (Näherung):* {fmt(z)}σ — {mco_state}")
    mcsi_state = ("über 10dma ✅ (Partizipation ok)" if st["mcsi_above_10"] else "unter 10dma")
    if st["mcsi_reclaim_10"]:
        mcsi_state += " · RECLAIM der 10dma = Gas geben 🚀"
    elif st["mcsi_curl_down"]:
        mcsi_state += " · curlt nach unten ⛔ keine neuen Positionen"
    elif st["mcsi_curl_up"]:
        mcsi_state += " · curlt nach oben = Turn testen"
    lines.append(f"*MCSI:* {mcsi_state}")
    lines.append("")

    if st.get("breaks"):
        lines.append("⚠️ *Strukturbruch bei bisherigen Signalen:* " + ", ".join(st["breaks"]))
    if st.get("reclaims"):
        lines.append("♻️ *Reclaim bei bisherigen Signalen:* " + ", ".join(st["reclaims"]))
        lines.append("")

    setups = st.get("setups", [])
    GRADE = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
    if setups and st["regime"] != "BREAKDOWN":
        lines.append(f"*🎯 Alle {len(setups)} Setups — nach Qualität (beste zuerst):*")
        for i, s in enumerate(setups):
            zone_lo, zone_hi = s["entry_zone"]
            g = GRADE.get(s.get("grade"), "⚪")
            tag = " ✅Kontraktion" if s["contraction"] else ""
            unk = " ⚠️Earnings?" if s["earnings_unknown"] else ""
            eu = s.get("eur")
            eus = ""
            if eu and s.get("ccy") != "EUR":
                eus = f"\n   € Zone {fmt(eu['entry_zone'][0])}–{fmt(eu['entry_zone'][1])} · Stop {fmt(eu['stop'])} · 2R {fmt(eu['target_2r'])}"
            bn = ""
            if s.get("buy_now"):
                bn = f"\n   🔴🟢 *KAUFSIGNAL: Schluss {fmt(s['close'])} {s.get('ccy','USD')} in Entry-Zone → Limitorder zum Schlusskurs!*"
            sp = s.get("stop_pct")
            sps = ""
            if sp is not None:
                mark = "✓" if s.get("stop_pct_ok") else "⚠️"
                sps = f" · Stop-Abstand {fmt(sp,1)}% {mark}"
            lines.append(
                f"{g} *{i+1}. {s['symbol']}* (Score {fmt(s.get('score',0),2)} · RS {s['rs']}) — Zone {fmt(zone_lo)}–{fmt(zone_hi)}$ · Stop {fmt(s['stop'])}$ · 2R {fmt(s['target_2r'])}$ {tag}{unk}{sps}" + bn + eus
            )
        lines.append("")
        lines.append("_🟢 High Conviction (max 1% Risiko möglich) · 🟡 Mittel (0,25–0,5%) · 🔴 Schwach (nur wenn überhaupt: 0,125–0,25%)_")
        lines.append("_Entry-Typ 1 (Schwäche in Zone): 0,25% · Entry-Typ 2 (Reclaim/Bestätigung): 0,5%_")
        lines.append("_Trim: ⅓ bei 2R · Rest läuft bis Tagesschluss unter 21-EMA-Low_")
    elif st["regime"] == "BREAKDOWN":
        lines.append("💤 *Heute keine Long-Setups — Markt im Breakdown. Kapital schützen.*")
    else:
        lines.append("💤 *Keine Setups heute: keine Liquid Leader im kaufbaren 21dma-Pullback-Fenster.*")
    # personal watchlist
    pos = st.get("positions", [])
    if pos:
        lines.append("")
        sells = [p for p in pos if p["status"] == "SELL"]
        lines.append(f"*💼 Meine Watchlist ({len(pos)} Positionen)*" + (f" — ⚠️ {len(sells)} Verkaufssignal(e)!" if sells else ":"))
        for p in pos:
            pnl = p.get("pnl_pct")
            pnls = f"{pnl:+.1f}%".replace("-", "−") if pnl is not None else "—"
            if p["status"] == "SELL":
                lines.append(f"🔻 *{p['symbol']} — VERKAUFSSIGNAL!* Schluss {fmt(p['close'])} {p.get('ccy','USD')} unter Stop {fmt(p['stop'])} ({p.get('stop_src','')}) · P&L {pnls}")
            elif p["status"] == "NO_DATA":
                lines.append(f"❓ *{p['symbol']}* — keine Kursdaten")
            else:
                trim = " · ✅ *2R erreicht: ⅓ Trim!*" if p.get("trim_reached") else ""
                lines.append(f"💼 *{p['symbol']}* (seit {p.get('date','?')}) — Einstieg {fmt(p['entry'])} · Stop {fmt(p['stop'])} · Schluss {fmt(p['close'])} · P&L {pnls}{trim}")

    lines.append("")
    lines.append("_Keine Anlageberatung — Signal nach Alex' Swing-System (traderslab.gitbook.io). MCO/MCSI sind eine Universe-Näherung, keine NYSE-Originaldaten._")
    return "\n".join(lines)

if __name__ == "__main__":
    sf = sys.argv[1] if len(sys.argv) > 1 else "state.json"
    print(main(sf))
