# Tržní přehled (dashboard)

## Spuštění
1. `pip install -r requirements.txt`
2. `python fetch_data.py` (stáhne data a vytvoří `data.js`)
3. Otevři `index.html` v prohlížeči (stačí dvojklik).

## Denní aktualizace
- Linux/macOS (cron, po zavření USA trhů): `30 23 * * 1-5 cd /cesta/k/market-dashboard && python3 fetch_data.py`
- Windows: Plánovač úloh spouštějící `python fetch_data.py`.
- Online: nahraj složku na GitHub Pages / Netlify a spouštěj `fetch_data.py` třeba přes GitHub Actions.

## Úpravy
- Přidání ukazatele: nový řádek `M.append(metric(...))` v `fetch_data.py`. Pravidla barev jsou funkce `rule_*`.
- Prahy (např. VIX 16/25) si uprav podle sebe v těchto funkcích.
