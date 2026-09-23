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
| Chokepoint tanker flows (war page) | IMF PortWatch ArcGIS API (AIS-derived, ~2–4 day lag) | keeps last good data |
| Brent crude | FRED (DCOILBRENTEU) | — |
| War headlines | Al Jazeera / BBC World / gCaptain + keyword filter over market feeds | per-feed skip |

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

## Bull-Market Playbook (top of `index.html`)

A cycle-phase tracker and live confirmation checklist following the framework
The DeFi Report (Michael Nadeau & Ryan Sean Adams) discusses on their weekly
show — four phases: Early Bull → Wealth Creation → Wealth Distribution →
Wealth Destruction. Attribution is shown on the page; all thresholds,
computations and text are this repo's own (`scripts/playbook.py`), computed
from free public data. Checks: golden cross, 50-week reclaim (with weekly-close
streak), 200-day hold, price vs STH cost basis, dominance turning up,
stablecoin rebuild, leverage rebuild, DEX-volume inflection, spot-ETF flows.
New data: bitcoin-data.com STH realized price, CoinGecko ETH mcap (dominance
proxy), DefiLlama DEX volumes + TVL, SoSoValue ETF flows (keyless POST).

## War Risk page (`war.html`)

Theater playbooks (Iran/Hormuz, Red Sea, Russia–Ukraine, Taiwan), a
physical-flows-vs-price tracker (tanker transits through Hormuz, Bab el-Mandeb
and Suez vs Brent), and a divergence detector with four states:
`aligned`, `disruption_priced`, `disruption_underpriced`,
`premium_no_disruption`. Baseline = each chokepoint's own **pre-war window**
(Hormuz: Nov ’24–Oct ’25, its last calm year; Red Sea routes: Jan–Oct ’23,
pre-Houthi; Black Sea straits: 2019–Jan ’22, pre-invasion; Taiwan: 2024–25
calm norm) — defined in `BASELINE_WINDOWS` in `scripts/fetch_data.py`.
Disruption = 14-day flow >25% below baseline; hot price = Brent +10% in 30
days. AIS caveat: jamming and dark sailing can make observed flows understate
real traffic — the page says so wherever it matters.

## Refresh cadence & cost

- Pipeline cron: **every 4 hours** (`23 */4 * * *`), plus on every code push.
  Each run re-fetches data, recomputes every "Right now" read, gauge and the
  war divergence banner, then redeploys.
- Effective freshness is source-bound: FRED market series update ~daily,
  PortWatch lags ~2–4 days, MVRV ~1 week, spot crypto/news are near-live at
  each run. Every card footer shows its own data-through date.
- **Cost: $0.** Public repo → GitHub Actions minutes and Pages hosting are
  free; every API is keyless/free tier. **No LLM anywhere** — all generated
  text is deterministic threshold rules in `interpret.py`, so runs cost zero
  tokens and the behavior is reproducible and testable.

## Security

- **No secrets exist** in this system — no API keys, no tokens beyond the
  workflow's own scoped `GITHUB_TOKEN`. Nothing to leak or rotate.
- Static site, no backend, no user input, no cookies, no analytics.
- CSP meta on both pages; the only external asset (Chart.js, pinned 4.4.9) is
  loaded with an SRI integrity hash from jsdelivr.
- All externally-sourced strings (news titles, calendar rows) are HTML-escaped
  before rendering.
- Workflows use only official `actions/*` steps.

## Maintenance (designed to be near zero)

- **Refresh:** `update-data.yml` runs every 4 hours, validates, commits data
  and redeploys Pages. Data commits carry `[skip ci]`.
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
