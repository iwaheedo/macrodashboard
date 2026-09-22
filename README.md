# Waypoint — Macro & Crypto, Interpreted

A self-updating, self-explaining macro dashboard. Liquidity, rates, credit, the
dollar, risk assets, Bitcoin cycle gauges, crypto leverage, calendar and news —
and every chart tells you **what you're looking at, what a move means, and what
it reads like right now**.

**Live site:** https://iwaheedo.github.io/macrodashboard/

Built with zero paid services and zero servers:

```
GitHub Actions (cron 4×/day)
   └─ scripts/fetch_data.py   → pulls free public APIs
   └─ scripts/validate.py     → freshness + plausibility checks
   └─ commits site/data/*.json → deploys site/ to GitHub Pages
Static site (no build step): index.html + styles.css + app.js + Chart.js CDN
```

## Data sources (all free, no API keys)

| Data | Source | Fallback |
|---|---|---|
| Rates, curve, VIX, S&P, Nasdaq, oil, CPI, M2, unemployment, Fed/ECB/BoJ balance sheets, TGA, RRP, FX | FRED `fredgraph.csv` (keyless) | — |
| Classic DXY, gold futures | Yahoo Finance chart API | FRED broad dollar / PAXG |
| BTC price history, market cap, hashrate, active addresses | blockchain.com charts API | — |
| MVRV, realized price | bitcoin-data.com (free tier, ~10 req/h, ~1 week lag) | previous run's data |
| BTC/ETH spot, ETH & ETH/BTC history | Coinbase | — |
| Total mcap, dominance, majors, sectors | CoinGecko | CoinPaprika (global) |
| Fear & Greed | alternative.me | — |
| Stablecoin supply | DefiLlama | — |
| Funding, open interest, long/short | OKX → Bybit → Binance chain | keeps last good data |
| Economic calendar | ForexFactory weekly JSON | keeps last good data |
| Headlines | CoinDesk / Cointelegraph / Decrypt / WSJ / MarketWatch RSS | per-feed skip |

Notes discovered the hard way (do not "fix" these):

- **FRED rejects browser User-Agents** sent from non-browser TLS stacks; the
  pipeline sends an honest tool UA (`scripts/net.py`).
- **FRED silently drops series beyond ~12 per request** and zips large
  responses, splitting series across several CSV members. `sources.fred()`
  chunks requests (8 per call) and merges all zip members.
- **WTREGEN (TGA) is in $ millions, RRPONTSYD in $ billions.** Net liquidity =
  `WALCL/1e6 − WTREGEN/1e6 − RRPONTSYD/1e3` (trillions).
- **bitcoin-data.com free tier:** ~10 requests/hour and ~4 years of history.
  The pipeline calls it twice per run and salvages the previous JSON on 429.
- Liquidation heatmaps are not included: that data has no free public source
  (Coinglass etc. are paid). Funding + OI + long/short cover the same
  "where is the leverage" question.

## Running locally

```bash
python3 scripts/fetch_data.py    # fetch everything → site/data/*.json
python3 scripts/validate.py      # health check the output
python3 -m unittest discover -s tests   # unit tests (no network)
python3 -m http.server 8741 --directory site   # view at localhost:8741
```

No dependencies — pure Python 3.10+ stdlib.

## Maintenance (designed to be near zero)

- **Refresh:** `update-data.yml` runs 4×/day, validates, commits data and
  redeploys Pages. Data commits carry `[skip ci]`.
- **If a run fails:** the workflow opens (or comments on) an issue labeled
  `pipeline-alert` — you get a GitHub notification email. The site keeps
  serving the last good data meanwhile, and every card footer shows how fresh
  its data is.
- **Keep-alive:** GitHub disables cron on repos with no activity for ~60 days,
  but the pipeline's own data commits count as activity, so it self-sustains.
- **Tests:** `ci.yml` runs the unit suite on every push/PR.

## Troubleshooting

1. Open the failing run's log — the failing stage prints which source broke.
2. Non-critical sources (derivatives, calendar, news) degrade gracefully for up
   to 7 days before failing the run; critical ones (FRED, blockchain.com,
   Fear & Greed, DefiLlama) fail immediately.
3. A dead source usually means the endpoint changed. Swap URLs in
   `scripts/sources.py`; sanity ranges in `scripts/validate.py` will confirm
   the replacement returns believable numbers.
4. Close the `pipeline-alert` issue after a green run.

## Interpretation layer

- `scripts/interpret.py` — per-metric thresholds → signal (`good` /
  `neutral` / `caution` / `info`) + a one-line plain-English read.
- `scripts/composites.py` — the three documented gauges (Liquidity Impulse,
  Risk Appetite, Crypto Cycle) and the regime quadrant with its playbook.
- `site/explainers.js` — the static "what is this / if it rises / if it falls"
  text for every chart.

Everything is educational context about historical patterns — **not financial
advice** — and the site says so prominently.
