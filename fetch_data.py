#!/usr/bin/env python3
"""Stáhne tržní data (Yahoo Finance + FRED), spočítá metriky a uloží je do data.js."""
import io
import json
import datetime as dt
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

OUT = Path(__file__).parent / "data.js"
YF_TICKERS = ["^GSPC", "SPY", "RSP", "IWM", "^VIX", "^VIX3M", "HYG", "IEF",
              "XLY", "XLP", "SMH", "HG=F", "GC=F", "DX-Y.NYB"]
FRED_IDS = ["DGS10", "DGS2", "T10Y2Y", "DFII10", "BAMLH0A0HYM2"]


# ---------- stahování ----------
def load_yahoo():
    df = yf.download(YF_TICKERS, period="2y", auto_adjust=True, progress=False)["Close"]
    return df.ffill()


def load_fred(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), index_col=0, parse_dates=True)
    s = pd.to_numeric(df.iloc[:, 0], errors="coerce").dropna()
    return s[s.index >= pd.Timestamp.today() - pd.Timedelta(days=800)]


# ---------- pravidla stavu: vrací green / yellow / red / neutral ----------
def vs_ma(s, n):
    return s.iloc[-1] / s.tail(n).mean() - 1


def rule_risk_on_ratio(s):      # růst poměru = chuť k riziku
    d = vs_ma(s, 50)
    return "green" if d > 0.005 else "red" if d < -0.005 else "yellow"


def rule_narrow_leadership(s):  # růst SPY/RSP = užší vedení trhu
    return "yellow" if vs_ma(s, 50) > 0 else "green"


def rule_vix(s):
    v = s.iloc[-1]
    return "green" if v < 16 else "yellow" if v < 25 else "red"


def rule_vix_term(s):
    v = s.iloc[-1]
    return "green" if v < 0.9 else "yellow" if v < 1 else "red"


def rule_spx(s):
    if s.iloc[-1] < s.tail(200).mean():
        return "red"
    return "yellow" if s.iloc[-1] < s.tail(50).mean() else "green"


def rule_curve(s):
    v = s.iloc[-1]
    return "red" if v < 0 else "yellow" if v < 0.5 else "green"


def rule_hy(s):
    v = s.iloc[-1]
    return "green" if v < 3.5 else "yellow" if v < 5 else "red"


def rule_yield(s):              # neutrální, upozorní jen na rychlý pohyb
    return "yellow" if abs(s.iloc[-1] - s.iloc[-22]) > 0.4 else "neutral"


def rule_neutral(s):
    return "neutral"


# ---------- sestavení metrik ----------
def metric(id_, name, group, s, rule, desc, unit="", kind="pct", digits=2):
    s = s.dropna()
    last = float(s.iloc[-1])

    def chg(n):
        if len(s) <= n:
            return None
        p = float(s.iloc[-1 - n])
        return round((last - p) * 100, 1) if kind == "bp" else round((last / p - 1) * 100, 2)

    tail = s.tail(126)
    return {
        "id": id_, "name": name, "group": group, "desc": desc, "unit": unit,
        "kind": kind, "digits": digits, "value": round(last, 4),
        "chg": {"1D": chg(1), "5D": chg(5), "1M": chg(21), "3M": chg(63)},
        "pctile": round(float((s.tail(252) <= last).mean() * 100)),
        "status": rule(s),
        "dates": [d.strftime("%Y-%m-%d") for d in tail.index],
        "series": [round(float(v), 4) for v in tail.values],
    }


def main():
    y = load_yahoo()
    f = {i: load_fred(i) for i in FRED_IDS}
    ratio = lambda a, b: (y[a] / y[b]).dropna()

    M = []
    G1, G2, G3, G4, G5 = "Šíře trhu", "Strach a volatilita", "Dluhopisy a sazby", "Kredit", "Rotace a chuť k riziku"
    M.append(metric("spx", "S&P 500", "Trend trhu", y["^GSPC"].dropna(), rule_spx,
                    "Zelená: nad 50DMA i 200DMA. Žlutá: pod 50DMA. Červená: pod 200DMA.", digits=0))
    M.append(metric("spy_rsp", "SPY / RSP (S&P 500 vs. equal weight)", G1, ratio("SPY", "RSP"), rule_narrow_leadership,
                    "Růst = trh táhne hrstka megacapů. Pokles = trh se rozšiřuje.", digits=3))
    M.append(metric("iwm_spy", "IWM / SPY (malé firmy vs. velké)", G1, ratio("IWM", "SPY"), rule_risk_on_ratio,
                    "Růst = malé firmy si vedou lépe, zdravější šíře trhu.", digits=3))
    M.append(metric("vix", "VIX", G2, y["^VIX"].dropna(), rule_vix,
                    "Pod 16 klid, 16 až 25 zvýšená opatrnost, nad 25 stres."))
    M.append(metric("vix_term", "VIX / VIX3M", G2, ratio("^VIX", "^VIX3M"), rule_vix_term,
                    "Nad 1 je křivka v backwardation, což znamená akutní stres.", digits=3))
    M.append(metric("y10", "Výnos 10Y Treasury (%)", G3, f["DGS10"], rule_yield,
                    "Změny v bazických bodech (bp). Žlutá při pohybu o více než 40 bp za měsíc.",
                    unit="%", kind="bp"))
    M.append(metric("y2", "Výnos 2Y Treasury (%)", G3, f["DGS2"], rule_yield,
                    "Odráží očekávání politiky Fedu.", unit="%", kind="bp"))
    M.append(metric("curve", "Křivka 10Y − 2Y (p. b.)", G3, f["T10Y2Y"], rule_curve,
                    "Pod 0 inverzní křivka (varování), nad 0,5 normální.", unit="p. b.", kind="bp"))
    M.append(metric("real10", "Reálný výnos 10Y (%)", G3, f["DFII10"], rule_neutral,
                    "Výnos očištěný o inflaci (TIPS). Vysoké hodnoty tlačí na ocenění akcií.",
                    unit="%", kind="bp"))
    M.append(metric("hy", "High Yield spread (p. b.)", G4, f["BAMLH0A0HYM2"], rule_hy,
                    "Pod 3,5 klid, 3,5 až 5 napětí, nad 5 stres na kreditním trhu.", unit="p. b.", kind="bp"))
    M.append(metric("hyg_ief", "HYG / IEF (rizikové vs. bezpečné dluhopisy)", G4, ratio("HYG", "IEF"), rule_risk_on_ratio,
                    "Růst = investoři jsou ochotni brát kreditní riziko.", digits=3))
    M.append(metric("xly_xlp", "XLY / XLP (cyklické vs. defenzivní)", G5, ratio("XLY", "XLP"), rule_risk_on_ratio,
                    "Růst = chuť k riziku (spotřebitelé utrácejí).", digits=3))
    M.append(metric("smh_spy", "SMH / SPY (polovodiče vs. trh)", G5, ratio("SMH", "SPY"), rule_risk_on_ratio,
                    "Polovodiče jsou motorem AI a technologií. Růst = technologické vedení.", digits=3))
    M.append(metric("cu_au", "Měď / zlato", G5, ratio("HG=F", "GC=F"), rule_risk_on_ratio,
                    "Růst = globální růst vítězí nad hledáním bezpečí.", digits=5))
    M.append(metric("dxy", "Dolarový index (DXY)", G5, y["DX-Y.NYB"].dropna(), rule_neutral,
                    "Silný dolar bývá tlakem na globální riziková aktiva."))

    counts = {k: sum(m["status"] == k for m in M) for k in ("green", "yellow", "red")}
    payload = {"updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
               "score": counts, "metrics": M}
    OUT.write_text("window.DASHBOARD = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"Uloženo {len(M)} metrik do {OUT}  {counts}")


if __name__ == "__main__":
    main()
