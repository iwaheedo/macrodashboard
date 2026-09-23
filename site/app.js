/* Waypoint dashboard — loads pipeline JSON, renders gauges, tiles and
 * self-explaining chart cards. No build step; Chart.js from CDN. */
"use strict";

/* EXPLAINERS, SECTION_INTROS, GAUGE_EXPLAINERS come from explainers.js */

const REPO_URL = "https://github.com/iwaheedo/macrodashboard";

/* ------------------------------------------------------------ palette --- */
const C = {
  ink: "#2A2014", ink2: "#6E5C49", ink3: "#A08D77",
  line: "#E7DFD1", accent: "#8A5731", camel: "#C3A583",
  deep: "#5F3A1E", clay: "#A9713F", stone: "#8C7A66",
  good: "#3F7352", warn: "#B95C33",
  goodSoft: "rgba(63,115,82,.14)", warnSoft: "rgba(185,92,51,.13)",
  accentSoft: "rgba(138,87,49,.10)",
};

/* --------------------------------------------------------- formatters --- */
const fmt = {
  usd: v => v == null ? "–" : "$" + compact(v),
  usd0: v => v == null ? "–" : "$" + Math.round(v).toLocaleString("en-US"),
  usd2: v => v == null ? "–" : "$" + v.toLocaleString("en-US", { maximumFractionDigits: 2 }),
  pct1: v => v == null ? "–" : v.toFixed(1) + "%",
  pct2: v => v == null ? "–" : v.toFixed(2) + "%",
  pct3: v => v == null ? "–" : v.toFixed(3) + "%",
  trillion: v => v == null ? "–" : "$" + v.toFixed(2) + "T",
  billion: v => v == null ? "–" : "$" + compact(v * 1e9),
  ratio2: v => v == null ? "–" : v.toFixed(2),
  ratio4: v => v == null ? "–" : v.toFixed(4),
  num: v => v == null ? "–" : compact(v),
  ehs: v => v == null ? "–" : compact(v / 1e6) + " EH/s",
  raw: v => v == null ? "–" : String(v),
};
function compact(v) {
  const a = Math.abs(v);
  if (a >= 1e12) return (v / 1e12).toFixed(2) + "T";
  if (a >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (v / 1e6).toFixed(2) + "M";
  if (a >= 1e4) return (v / 1e3).toFixed(1) + "K";
  if (a >= 100) return v.toFixed(0);
  if (a >= 1) return v.toFixed(2);
  return v.toPrecision(3);
}
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function tickLabel(iso) {
  return MONTHS[+iso.slice(5, 7) - 1] + " ’" + iso.slice(2, 4);
}
function fullDate(iso) {
  return MONTHS[+iso.slice(5, 7) - 1] + " " + (+iso.slice(8, 10)) + ", " + iso.slice(0, 4);
}
function relTime(isoOrDate) {
  const t = new Date(isoOrDate).getTime();
  if (!isFinite(t)) return "";
  const mins = Math.max(0, (Date.now() - t) / 60000);
  if (mins < 60) return Math.round(mins) + "m ago";
  if (mins < 60 * 36) return Math.round(mins / 60) + "h ago";
  return Math.round(mins / 1440) + "d ago";
}
function asof(series, iso) {
  const d = series.dates; let lo = 0, hi = d.length - 1, ans = -1;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (d[m] <= iso) { ans = m; lo = m + 1; } else hi = m - 1; }
  return ans < 0 ? null : series.values[ans];
}
function sliceRange(series, range) {
  if (!series || !series.dates.length) return { dates: [], values: [] };
  if (range === "All") return series;
  const yrs = { "3M": 0.25, "1Y": 1, "2Y": 2, "3Y": 3, "5Y": 5, "10Y": 10 }[range] || 100;
  const lastD = new Date(series.dates[series.dates.length - 1]);
  lastD.setFullYear(lastD.getFullYear() - yrs);
  const cut = lastD.toISOString().slice(0, 10);
  let i = series.dates.findIndex(d => d >= cut);
  if (i < 0) i = 0;
  return { dates: series.dates.slice(i), values: series.values.slice(i) };
}

/* ---------------------------------------------------- chart.js defaults --- */
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
Chart.defaults.font.size = 11.5;
Chart.defaults.color = C.ink3;
Chart.defaults.animation = false;
Chart.defaults.elements.point.radius = 0;
Chart.defaults.elements.point.hoverRadius = 4;
Chart.defaults.elements.line.borderWidth = 2;
Chart.defaults.plugins.legend.display = false;

const zonePlugin = {
  id: "zones",
  beforeDatasetsDraw(chart, _a, opts) {
    if (!opts.zones) return;
    const { ctx, chartArea: ar, scales: { y } } = chart;
    for (const z of opts.zones) {
      const top = y.getPixelForValue(Math.min(z.to, y.max));
      const bot = y.getPixelForValue(Math.max(z.from, y.min));
      if (bot <= ar.top || top >= ar.bottom) continue;
      ctx.fillStyle = z.color;
      ctx.fillRect(ar.left, Math.max(top, ar.top), ar.width, Math.min(bot, ar.bottom) - Math.max(top, ar.top));
    }
  },
  afterDatasetsDraw(chart, _a, opts) {
    if (!opts.hline && opts.hline !== 0) return;
    const { ctx, chartArea: ar, scales: { y } } = chart;
    const py = y.getPixelForValue(opts.hline);
    if (py < ar.top || py > ar.bottom) return;
    ctx.save(); ctx.strokeStyle = "rgba(42,32,20,.28)"; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(ar.left, py); ctx.lineTo(ar.right, py); ctx.stroke(); ctx.restore();
  },
};
Chart.register(zonePlugin);

function baseOptions(yFmt, extra = {}) {
  return {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    scales: {
      x: {
        grid: { display: false }, border: { color: C.line },
        ticks: { maxTicksLimit: 7, maxRotation: 0, autoSkipPadding: 24,
                 callback(v) { return tickLabel(this.getLabelForValue(v)); } },
      },
      y: {
        position: "right", border: { display: false },
        grid: { color: "rgba(231,223,209,.55)", drawTicks: false },
        ticks: { padding: 8, maxTicksLimit: 6, callback: v => yFmt(v) },
        ...(extra.log ? { type: "logarithmic" } : {}),
        ...(extra.yMin != null ? { min: extra.yMin } : {}),
        ...(extra.yMax != null ? { max: extra.yMax } : {}),
      },
    },
    plugins: {
      zones: { zones: extra.zones, hline: extra.hline },
      tooltip: {
        backgroundColor: "#FFFFFF", titleColor: C.ink, bodyColor: C.ink2,
        borderColor: C.line, borderWidth: 1, cornerRadius: 10,
        padding: 10, boxPadding: 4, titleFont: { weight: "600" },
        callbacks: {
          title: items => items.length ? fullDate(items[0].label) : "",
          label: ctx => ` ${ctx.dataset.label || ""}: ${yFmt(ctx.parsed.y)}`.replace(/^ : /, " "),
        },
      },
      legend: extra.legend
        ? { display: true, position: "top", align: "start",
            labels: { boxWidth: 14, boxHeight: 2, padding: 14, color: C.ink2, font: { size: 12 } } }
        : { display: false },
    },
  };
}

function gradientFill(ctx, color) {
  const g = ctx.createLinearGradient(0, 0, 0, ctx.canvas.height || 260);
  g.addColorStop(0, color); g.addColorStop(1, "rgba(255,255,255,0)");
  return g;
}

/* -------------------------------------------------------- chart configs --- */
const SERIES_COLORS = [C.accent, C.camel, C.stone, C.good, C.warn];

const CHARTS = [
  // -------- liquidity
  { id: "net_liquidity", section: "liquidity", title: "Fed Net Liquidity",
    sub: "Fed balance sheet − Treasury account − reverse repo", unit: fmt.trillion,
    read: "net_liquidity", ranges: ["1Y", "5Y", "All"], def: "5Y", area: true,
    series: [{ f: "macro", k: "net_liquidity", label: "Net liquidity ($T)" }],
    source: "FRED (WALCL, WTREGEN, RRPONTSYD)" },
  { id: "global_cb", section: "liquidity", title: "Global Central Bank Balance Sheets",
    sub: "Fed + ECB + Bank of Japan, in US dollars", unit: fmt.trillion,
    read: "global_cb", ranges: ["1Y", "5Y", "All"], def: "5Y", area: true,
    series: [{ f: "macro", k: "global_cb", label: "Big-3 assets ($T)" }],
    source: "FRED (WALCL, ECBASSETSW, JPNASSETS, FX)" },
  { id: "m2_yoy", section: "liquidity", title: "US Money Supply Growth",
    sub: "M2, year over year", unit: fmt.pct1,
    read: "m2_yoy", ranges: ["5Y", "10Y", "All"], def: "10Y", hline: 0,
    series: [{ f: "macro", k: "m2_yoy", label: "M2 YoY" }], source: "FRED (M2SL)" },
  { id: "cpi", section: "liquidity", title: "Inflation",
    sub: "Consumer prices, year over year", unit: fmt.pct1,
    read: "cpi", ranges: ["5Y", "10Y", "All"], def: "10Y", hline: 2, legend: true,
    series: [{ f: "macro", k: "cpi_yoy", label: "Headline CPI" },
             { f: "macro", k: "core_cpi_yoy", label: "Core CPI", dash: [5, 4] }],
    source: "FRED (CPIAUCSL, CPILFESL)" },
  { id: "policy_rates", section: "liquidity", title: "The Fed &amp; the Bond Market",
    sub: "Policy rate vs 2-year and 10-year Treasury yields", unit: fmt.pct2,
    read: "fedfunds", ranges: ["3Y", "10Y", "All"], def: "10Y", legend: true,
    series: [{ f: "macro", k: "fedfunds", label: "Fed funds" },
             { f: "macro", k: "dgs10", label: "10Y yield" },
             { f: "macro", k: "dgs2", label: "2Y yield", dash: [5, 4] }],
    source: "FRED (FEDFUNDS, DGS10, DGS2)" },
  { id: "unrate", section: "liquidity", title: "Unemployment",
    sub: "US unemployment rate", unit: fmt.pct1,
    read: "unrate", ranges: ["5Y", "10Y", "All"], def: "10Y",
    series: [{ f: "macro", k: "unrate", label: "Unemployment" }], source: "FRED (UNRATE)" },

  // -------- rates & dollar
  { id: "yield_curve", section: "rates", title: "Yield Curve",
    sub: "Long minus short Treasury yields — below zero = inverted", unit: fmt.pct2,
    read: "yield_curve", ranges: ["3Y", "10Y", "All"], def: "10Y", hline: 0, legend: true,
    series: [{ f: "macro", k: "t10y2y", label: "10Y − 2Y" },
             { f: "macro", k: "t10y3m", label: "10Y − 3M", dash: [5, 4] }],
    source: "FRED (T10Y2Y, T10Y3M)" },
  { id: "hy_oas", section: "rates", title: "Credit Stress",
    sub: "High-yield corporate bond spread over Treasuries", unit: fmt.pct1,
    read: "hy_oas", ranges: ["3Y", "10Y", "All"], def: "10Y",
    zones: [{ from: 5, to: 25, color: C.warnSoft }],
    series: [{ f: "macro", k: "hy_oas", label: "HY spread" }],
    source: "FRED (BAMLH0A0HYM2)" },
  { id: "dollar", section: "rates", title: "US Dollar",
    sub: "", unit: fmt.ratio2, read: "dollar", ranges: ["1Y", "5Y", "10Y"], def: "5Y",
    series: [{ f: "macro", k: "__dollar__", label: "Dollar index" }],
    source: "" },

  // -------- risk assets
  { id: "spx", section: "assets", title: "S&amp;P 500",
    sub: "With 200-day moving average", unit: fmt.num,
    read: "spx", ranges: ["1Y", "3Y", "10Y"], def: "3Y", legend: true,
    series: [{ f: "macro", k: "spx", label: "S&P 500" },
             { f: "macro", k: "spx_200dma", label: "200-day avg", dash: [5, 4] }],
    source: "FRED (SP500)" },
  { id: "nasdaq", section: "assets", title: "Nasdaq Composite",
    sub: "With 200-day moving average", unit: fmt.num,
    read: "nasdaq", ranges: ["1Y", "3Y", "10Y"], def: "3Y", legend: true,
    series: [{ f: "macro", k: "nasdaq", label: "Nasdaq" },
             { f: "macro", k: "nasdaq_200dma", label: "200-day avg", dash: [5, 4] }],
    source: "FRED (NASDAQCOM)" },
  { id: "vix", section: "assets", title: "Volatility (VIX)",
    sub: "Expected 30-day S&amp;P 500 volatility", unit: fmt.ratio2,
    read: "vix", ranges: ["1Y", "3Y", "10Y"], def: "3Y",
    zones: [{ from: 28, to: 95, color: C.warnSoft }, { from: 0, to: 14, color: C.goodSoft }],
    series: [{ f: "macro", k: "vix", label: "VIX" }], source: "FRED (VIXCLS)" },
  { id: "gold", section: "assets", title: "Gold",
    sub: "US dollars per ounce", unit: fmt.usd,
    read: "gold", ranges: ["1Y", "3Y", "10Y"], def: "3Y",
    series: [{ f: "macro", k: "gold", label: "Gold" }], source: "Yahoo Finance (GC=F)" },
  { id: "oil", section: "assets", title: "Oil (WTI)",
    sub: "US dollars per barrel", unit: fmt.usd,
    read: "oil", ranges: ["1Y", "3Y", "10Y"], def: "3Y",
    series: [{ f: "macro", k: "oil", label: "WTI crude" }], source: "FRED (DCOILWTICO)" },

  // -------- playbook (cycle-framework charts)
  { id: "costbasis", section: "playbook", title: "The Cost-Basis Ladder", full: true,
    sub: "Price vs the market's average cost basis and what recent buyers paid — the market-structure view", unit: fmt.usd,
    read: ["sth_basis", "realized"], ranges: ["1Y", "3Y", "All"], def: "3Y", legend: true,
    series: [{ f: "crypto", k: "btc_price", label: "BTC" },
             { f: "crypto", k: "btc_sth_realized", label: "STH cost basis", dash: [6, 4], color: C.warn },
             { f: "crypto", k: "btc_realized", label: "Realized price (all)", dash: [6, 4], color: C.good }],
    source: "blockchain.com · bitcoin-data.com" },
  { id: "dominance", section: "playbook", title: "BTC Dominance (majors proxy)",
    sub: "Bitcoin's share of BTC + ETH + stablecoins — the rotation dial", unit: fmt.pct1,
    read: "dominance", ranges: ["1Y"], def: "1Y",
    series: [{ f: "crypto", k: "btc_dominance_proxy", label: "BTC share of majors" }],
    source: "blockchain.com · CoinGecko · DefiLlama" },
  { id: "etf", section: "playbook", title: "Spot-ETF Net Flows",
    sub: "Daily net flows into US spot-Bitcoin ETFs", unit: v => v == null ? "–" : (v >= 0 ? "+" : "") + compact(v) + "M",
    read: "etf_flows", ranges: ["3M", "1Y"], def: "3M", bar: true, hline: 0, barPosGood: true,
    series: [{ f: "crypto", k: "etf_flows", label: "Net flow ($M)" }],
    source: "SoSoValue" },
  { id: "dex", section: "playbook", title: "On-Chain Activity",
    sub: "Total DEX trading volume per day, all chains", unit: v => v == null ? "–" : "$" + compact(v) + "B",
    read: "dex_volume", ranges: ["1Y", "3Y", "All"], def: "1Y", area: true,
    series: [{ f: "crypto", k: "dex_volume", label: "DEX volume ($B/day)" }],
    source: "DefiLlama" },
  { id: "tvl", section: "playbook", title: "DeFi TVL",
    sub: "Capital locked in DeFi — crypto's internal credit system", unit: v => v == null ? "–" : "$" + compact(v) + "B",
    read: "defi_tvl", ranges: ["1Y", "3Y", "All"], def: "3Y", area: true,
    series: [{ f: "crypto", k: "defi_tvl", label: "TVL ($B)" }],
    source: "DefiLlama" },

  // -------- crypto
  { id: "btc", section: "crypto", title: "Bitcoin &amp; Its Reference Lines", full: true,
    sub: "Price vs 200-day, 200-week and realized price (network cost basis)", unit: fmt.usd,
    read: ["btc", "realized"], ranges: ["1Y", "3Y", "All"], def: "3Y", legend: true, logOnAll: true,
    series: [{ f: "crypto", k: "btc_price", label: "BTC" },
             { f: "crypto", k: "btc_200dma", label: "200-day avg", dash: [5, 4] },
             { f: "crypto", k: "btc_200wma", label: "200-week avg", dash: [2, 3], color: C.stone },
             { f: "crypto", k: "btc_realized", label: "Realized price", dash: [6, 4], color: C.good }],
    source: "blockchain.com · bitcoin-data.com" },
  { id: "rainbow", section: "crypto", title: "Bitcoin Long-Term Value Bands", full: true,
    sub: "Log-scale price with bands around its fitted long-term growth path", unit: fmt.usd,
    read: "rainbow", ranges: ["All"], def: "All", rainbow: true,
    series: [], source: "blockchain.com · fitted in pipeline" },
  { id: "mvrv", section: "crypto", title: "MVRV Ratio",
    sub: "Market value ÷ realized value", unit: fmt.ratio2,
    read: "mvrv", ranges: ["3Y", "5Y", "All"], def: "All", hline: 1,
    zones: [{ from: 3.2, to: 12, color: C.warnSoft }, { from: 0, to: 1, color: C.goodSoft }],
    series: [{ f: "crypto", k: "btc_mvrv", label: "MVRV" }], source: "bitcoin-data.com" },
  { id: "mayer", section: "crypto", title: "Mayer Multiple",
    sub: "Price ÷ 200-day moving average", unit: fmt.ratio2,
    read: "mayer", ranges: ["3Y", "5Y", "All"], def: "All", hline: 1,
    zones: [{ from: 2.4, to: 5, color: C.warnSoft }, { from: 0, to: 0.8, color: C.goodSoft }],
    series: [{ f: "crypto", k: "btc_mayer", label: "Mayer" }], source: "computed from blockchain.com" },
  { id: "fng", section: "crypto", title: "Fear &amp; Greed",
    sub: "Crypto sentiment, 0 (fear) – 100 (greed)", unit: fmt.raw,
    read: "fng", ranges: ["1Y", "2Y"], def: "1Y", yMin: 0, yMax: 100,
    zones: [{ from: 75, to: 100, color: C.warnSoft }, { from: 0, to: 25, color: C.goodSoft }],
    series: [{ f: "crypto", k: "fng", label: "Fear & Greed" }], source: "alternative.me" },
  { id: "stables", section: "crypto", title: "Stablecoin Supply",
    sub: "Total dollar stablecoins in circulation — crypto's dry powder", unit: v => v == null ? "–" : "$" + compact(v) + "B",
    read: "stables", ranges: ["1Y", "3Y", "All"], def: "3Y", area: true,
    series: [{ f: "crypto", k: "stablecoin_mcap", label: "Stablecoins ($B)" }], source: "DefiLlama" },
  { id: "eth", section: "crypto", title: "Ether",
    sub: "ETH price, USD", unit: fmt.usd,
    read: null, ranges: ["1Y", "3Y", "All"], def: "3Y",
    series: [{ f: "crypto", k: "eth_price", label: "ETH" }], source: "Coinbase" },
  { id: "ethbtc", section: "crypto", title: "ETH / BTC",
    sub: "Crypto's internal risk appetite dial", unit: fmt.ratio4,
    read: "ethbtc", ranges: ["1Y", "3Y", "All"], def: "3Y",
    series: [{ f: "crypto", k: "ethbtc", label: "ETH/BTC" }], source: "Coinbase" },
  { id: "hashrate", section: "crypto", title: "Bitcoin Hashrate",
    sub: "Network computing power (30-day view smooths daily noise)", unit: fmt.ehs,
    read: "hashrate", ranges: ["1Y", "3Y", "5Y"], def: "3Y",
    series: [{ f: "crypto", k: "btc_hashrate", label: "Hashrate" }], source: "blockchain.com" },
  { id: "active_addr", section: "crypto", title: "Active Addresses",
    sub: "Unique BTC addresses used per day", unit: fmt.num,
    read: null, ranges: ["1Y", "2Y"], def: "1Y",
    series: [{ f: "crypto", k: "btc_active_addr", label: "Active addresses" }], source: "blockchain.com" },

  // -------- leverage
  { id: "funding", section: "derivs", title: "Perp Funding Rate",
    sub: "BTC perpetual futures — average 8-hour rate paid by longs", unit: fmt.pct3,
    read: "funding", ranges: ["All"], def: "All", bar: true, hline: 0,
    series: [{ f: "derivs", k: "funding.btc", label: "BTC funding (8h)" }], source: "" },
  { id: "open_interest", section: "derivs", title: "Futures Open Interest",
    sub: "Value of open BTC futures positions", unit: v => v == null ? "–" : "$" + compact(v) + "B",
    read: "open_interest", ranges: ["All"], def: "All", area: true,
    series: [{ f: "derivs", k: "open_interest.btc", label: "BTC OI ($B)", toUSDB: true }], source: "" },
  { id: "long_short", section: "derivs", title: "Long / Short Accounts",
    sub: "Retail positioning on OKX — accounts long per account short", unit: fmt.ratio2,
    read: "long_short", ranges: ["All"], def: "All", hline: 1,
    series: [{ f: "derivs", k: "long_short.btc", label: "Long/short ratio" }], source: "OKX" },
];

/* ------------------------------------------------------------- render --- */
const DATA = {};
const charts = {};

async function loadJSON(name) {
  try {
    const r = await fetch(`data/${name}.json`, { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch (e) { console.warn(`missing data/${name}.json`, e); return null; }
}

function getSeries(spec) {
  const doc = DATA[spec.f];
  if (!doc) return null;
  if (spec.k === "__dollar__") {
    const s = doc.series.dxy || doc.series.dxy_broad;
    return s && s.values.length ? s : null;
  }
  let node = spec.k.includes(".")
    ? spec.k.split(".").reduce((o, k) => (o || {})[k], doc)
    : (doc.series || {})[spec.k];
  if (!node || !node.dates || !node.dates.length) return null;
  if (spec.toUSDB && DATA.crypto) {
    if (node.unit === "usd") {
      return { dates: node.dates, values: node.values.map(v => v / 1e9),
               source: node.source };
    }
    const px = DATA.crypto.series.btc_price;
    const vals = node.dates.map((d, i) => {
      const p = asof(px, d); return p ? node.values[i] * p / 1e9 : null;
    });
    return { dates: node.dates, values: vals, source: node.source };
  }
  return node;
}

function signalChip(sig) {
  const words = { good: "Supportive", caution: "Caution", neutral: "Neutral", info: "Context" };
  return `<span class="chip ${sig}">${words[sig] || sig}</span>`;
}

function nowBox(read) {
  if (!read) return "";
  return `<div class="now ${read.signal}"><span class="now-tag">Right now</span>${esc(read.text)}</div>`;
}

function esc(s) { return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

function explainBlock(id) {
  const e = EXPLAINERS[id];
  if (!e) return "";
  return `<div class="explain">
    <div class="e-what"><h4>What you're looking at</h4><p>${esc(e.what)}</p></div>
    <div><h4><span class="arrow-up">↑</span> If it rises</h4><p>${esc(e.up)}</p></div>
    <div><h4><span class="arrow-down">↓</span> If it falls</h4><p>${esc(e.down)}</p></div>
  </div>`;
}

function renderCard(cfg) {
  const grid = document.getElementById(`grid-${cfg.section}`);
  const el = document.createElement("div");
  el.className = "card" + (cfg.full ? " full" : "");
  el.id = `card-${cfg.id}`;

  const primary = cfg.rainbow ? (DATA.crypto ? DATA.crypto.series.btc_price : null)
                              : getSeries(cfg.series[0] || {});
  const reads = [].concat(cfg.read || []).map(k => (DATA.signals?.reads || {})[k]).filter(Boolean);
  const latest = primary ? primary.values[primary.values.length - 1] : null;
  const lastDate = primary ? primary.dates[primary.dates.length - 1] : null;
  const sig = reads[0]?.signal;

  const src = cfg.source || (primary && primary.source ? cap(primary.source) : "");
  const rangesHtml = cfg.ranges.length > 1
    ? `<div class="ranges">${cfg.ranges.map(r =>
        `<button data-r="${r}" class="${r === cfg.def ? "on" : ""}">${r}</button>`).join("")}</div>`
    : "";

  el.innerHTML = `
    <div class="card-top">
      <div><h3 class="card-title">${cfg.title}</h3><p class="card-sub" id="sub-${cfg.id}">${cfg.sub}</p></div>
      ${rangesHtml}
    </div>
    <div class="card-value-row">
      <span class="card-value">${primary ? cfg.unit(latest) : "–"}</span>
      ${sig ? signalChip(sig) : ""}
    </div>
    <div class="chart-box${cfg.full ? " full-h" : ""}"><canvas id="cv-${cfg.id}"></canvas></div>
    ${reads.map(nowBox).join("")}
    ${explainBlock(cfg.id)}
    <div class="card-foot">
      <span>${primary ? "Data through " + fullDate(lastDate) : "Source unavailable — auto-retries on next refresh"}</span>
      <span id="src-${cfg.id}">${esc(src)}</span>
    </div>`;
  grid.appendChild(el);

  if (!primary) { el.classList.add("unavailable"); return; }

  if (cfg.id === "dollar") {
    const isClassic = !!(DATA.macro.series.dxy && DATA.macro.series.dxy.values.length);
    document.getElementById("sub-dollar").textContent = isClassic
      ? "DXY — dollar vs major currencies" : "Trade-weighted broad dollar index (DXY proxy)";
    document.getElementById("src-dollar").textContent = isClassic ? "Yahoo Finance" : "FRED (DTWEXBGS)";
  }
  if (cfg.id === "gold" && primary.source === "paxg") {
    document.getElementById("src-gold").textContent = "PAXG proxy (CoinGecko)";
  }
  if (cfg.section === "derivs" && primary.source) {
    document.getElementById(`src-${cfg.id}`).textContent = cap(primary.source);
  }

  drawChart(cfg, cfg.def);
  el.querySelectorAll(".ranges button").forEach(btn => btn.addEventListener("click", () => {
    el.querySelectorAll(".ranges button").forEach(b => b.classList.toggle("on", b === btn));
    drawChart(cfg, btn.dataset.r);
  }));
}
function cap(s) { return s ? s[0].toUpperCase() + s.slice(1) : s; }

function drawChart(cfg, range) {
  const canvas = document.getElementById(`cv-${cfg.id}`);
  if (charts[cfg.id]) charts[cfg.id].destroy();
  if (cfg.rainbow) { charts[cfg.id] = drawRainbow(canvas); return; }

  const primary = sliceRange(getSeries(cfg.series[0]), range);
  const labels = primary.dates;
  const datasets = cfg.series.map((spec, i) => {
    const s = getSeries(spec);
    if (!s) return null;
    const color = spec.color || SERIES_COLORS[i];
    const data = i === 0 ? primary.values : labels.map(d => asof(s, d));
    return {
      label: spec.label, data, borderColor: color,
      backgroundColor: cfg.bar
        ? primary.values.map(v => cfg.barPosGood
            ? (v >= 0 ? "rgba(63,115,82,.75)" : "rgba(185,92,51,.75)")
            : (v >= 0 ? "rgba(138,87,49,.75)" : "rgba(63,115,82,.75)"))
        : (cfg.area && i === 0 ? gradientFill(canvas.getContext("2d"), C.accentSoft) : color),
      fill: cfg.area && i === 0, borderDash: spec.dash || [],
      borderWidth: cfg.bar ? 0 : (i === 0 ? 2.2 : 1.6),
    };
  }).filter(Boolean);

  const useLog = cfg.logOnAll && range === "All";
  charts[cfg.id] = new Chart(canvas, {
    type: cfg.bar ? "bar" : "line",
    data: { labels, datasets },
    options: baseOptions(cfg.unit, { zones: cfg.zones, hline: cfg.hline,
                                     legend: cfg.legend, log: useLog,
                                     yMin: useLog ? undefined : cfg.yMin, yMax: useLog ? undefined : cfg.yMax }),
  });
}

const BAND_FILL = ["rgba(63,115,82,.16)", "rgba(63,115,82,.09)", "rgba(195,165,131,.12)",
                   "rgba(195,165,131,.20)", "rgba(185,92,51,.13)", "rgba(185,92,51,.22)"];
const BAND_NAMES = ["Deep value", "Accumulate", "Still cheap", "Fair value", "Frothy", "Euphoria"];

function drawRainbow(canvas) {
  const rb = DATA.crypto.rainbow;
  const price = DATA.crypto.series.btc_price;
  // start where our displayed price history starts — early-years bands would
  // drag the log axis down to fractions of a cent
  let start = rb.dates.findIndex(d => d >= (price.dates[0] || "2013-01-01"));
  if (start < 0) start = 0;
  const labels = rb.dates.slice(start);
  const bands = rb.bands.map(b => b.slice(start));
  const priceData = labels.map(d => d <= price.dates[price.dates.length - 1] ? asof(price, d) : null);
  const datasets = bands.map((band, i) => ({
    label: i > 0 ? BAND_NAMES[i - 1] : "band floor", data: band,
    borderColor: "rgba(0,0,0,0)", borderWidth: 0, pointRadius: 0,
    fill: i === 0 ? false : "-1",
    backgroundColor: i === 0 ? "transparent" : BAND_FILL[i - 1],
  }));
  datasets.push({ label: "BTC", data: priceData, borderColor: C.deep, borderWidth: 2.2, fill: false });
  const floor = Math.max(1, Math.min(...bands[0].filter(v => v > 0)) * 0.8);
  const ceil = Math.max(...bands[bands.length - 1]) * 1.15;
  const opts = baseOptions(fmt.usd, { log: true, yMin: floor, yMax: ceil });
  opts.plugins.tooltip.callbacks.label = ctx =>
    ctx.dataset.label === "BTC" ? ` BTC: ${fmt.usd(ctx.parsed.y)}` : null;
  opts.plugins.tooltip.filter = item => item.dataset.label === "BTC";
  return new Chart(canvas, { type: "line", data: { labels, datasets }, options: opts });
}

/* ----------------------------------------------------- regime & gauges --- */
function renderRegime() {
  const el = document.getElementById("regime-card");
  const g = DATA.signals?.gauges;
  if (!g) { el.innerHTML = "<p>Signals unavailable.</p>"; return; }
  const r = g.regime;
  el.innerHTML = `
    <div class="regime-head"><span class="regime-label">Current regime</span></div>
    <div class="regime-name">${esc(r.name)}</div>
    <p class="regime-summary">${esc(r.summary)}</p>
    <div class="playbook">
      ${r.playbook.map(p => `<div class="playbook-item">${esc(p)}</div>`).join("")}
    </div>`;
}

function gaugeSVG(score, uid) {
  const pct = Math.max(0.02, Math.min(100, score)) / 100;
  const start = Math.PI, end = Math.PI * (1 - pct);
  const r = 70, cx = 84, cy = 88;
  const x1 = cx + r * Math.cos(start), y1 = cy - r * Math.sin(start);
  const x2 = cx + r * Math.cos(end), y2 = cy - r * Math.sin(end);
  // gauge sweep is pct*180° ≤ 180°, so the SVG large-arc flag is always 0
  const large = 0;
  const gid = `gg-${uid}`;  // gradient ids must be unique across inline SVGs
  return `<svg class="gauge-svg" viewBox="0 0 168 100">
    <path d="M14 88 A70 70 0 0 1 154 88" fill="none" stroke="#EDE5D7" stroke-width="11" stroke-linecap="round"/>
    <path d="M${x1} ${y1} A${r} ${r} 0 ${large} 1 ${x2} ${y2}" fill="none"
          stroke="url(#${gid})" stroke-width="11" stroke-linecap="round"/>
    <defs><linearGradient id="${gid}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="${C.clay}"/><stop offset="1" stop-color="${C.deep}"/>
    </linearGradient></defs>
  </svg>`;
}

function renderGauges() {
  const wrap = document.getElementById("gauges");
  const g = DATA.signals?.gauges;
  if (!g) return;
  const items = [
    ["liquidity_impulse", "Liquidity Impulse", "Is money being added or drained?"],
    ["risk_appetite", "Risk Appetite", "How much risk are markets embracing?"],
    ["crypto_cycle", "Crypto Cycle", "Where is Bitcoin in its boom-bust arc?"],
  ];
  wrap.innerHTML = items.map(([key, title, sub]) => {
    const d = g[key];
    if (!d || d.score == null) return "";
    return `<div class="gauge-card">
      <h3 class="gauge-title">${title}</h3>
      <p class="gauge-sub">${sub}</p>
      ${gaugeSVG(d.score, key)}
      <div class="gauge-score">${d.score}</div>
      <div class="gauge-word">${esc(d.label)}</div>
      <details>
        <summary>How it's computed</summary>
        ${d.components.map(c => `<div class="gauge-comp"><span>${esc(c.name)}</span><b>${c.score ?? "–"}</b></div>`).join("")}
        <div class="gauge-note">${esc(GAUGE_EXPLAINERS[key] || "")}</div>
      </details>
    </div>`;
  }).join("");
}

/* ----------------------------------------------------------- playbook --- */
function renderPlaybook() {
  const pb = DATA.signals?.playbook;
  const phaseEl = document.getElementById("phase-tracker");
  const listEl = document.getElementById("checklist");
  if (!pb || !phaseEl) {
    if (phaseEl) phaseEl.innerHTML = "";
    return;
  }
  const ph = pb.phase;
  phaseEl.innerHTML = `
    <div class="phase-card">
      <div class="phase-bar">
        ${ph.phases.map(p => `<div class="phase-seg${p.key === ph.key ? " active" : ""}">${esc(p.name)}</div>`).join("")}
      </div>
      <p class="phase-why"><b>${ph.checks_passing} of ${ph.checks_total}</b> confirmation checks passing · ${esc(ph.why)}</p>
      <div class="phase-guide">
        <div><h4>This phase's signature</h4><p>${esc(ph.guide.signature)}</p></div>
        <div><h4>What has historically worked</h4><p>${esc(ph.guide.playbook)}</p></div>
        <div><h4>The exit tell</h4><p>${esc(ph.guide.exit_tell)}</p></div>
      </div>
    </div>`;

  const icons = { pass: "✓", warn: "!", fail: "✕" };
  listEl.innerHTML = `<div class="check-grid">
    ${pb.checks.map(c => `
      <a class="check-item" href="${c.anchor ? "#" + c.anchor : "#playbook"}">
        <div class="check-head">
          <span class="check-icon ${c.state}">${icons[c.state] || "·"}</span>
          <span class="check-label">${esc(c.label)}</span>
        </div>
        <div class="check-value">${esc(c.value)}</div>
        <div class="check-note">${esc(c.note)}</div>
      </a>`).join("")}
  </div>`;
}

/* -------------------------------------------------------------- tiles --- */
function pctDelta(series, days = 1) {
  if (!series || series.values.length < 2) return null;
  const last = series.values[series.values.length - 1];
  const prev = series.values[Math.max(0, series.values.length - 1 - days)];
  return prev ? (last / prev - 1) * 100 : null;
}
function tile(label, value, delta, suffix = "%") {
  const cls = delta == null ? "flat" : delta > 0.001 ? "pos" : delta < -0.001 ? "neg" : "flat";
  const dTxt = delta == null ? "" : `${delta > 0 ? "+" : ""}${delta.toFixed(delta && Math.abs(delta) < 0.1 ? 2 : 1)}${suffix}`;
  return `<div class="tile"><div class="t-label">${label}</div>
    <div class="t-value">${value}</div><div class="t-delta ${cls}">${dTxt}</div></div>`;
}
function renderTiles() {
  const el = document.getElementById("tiles");
  const ms = DATA.macro?.series || {}, cs = DATA.crypto?.series || {}, spot = DATA.crypto?.spot || {};
  const t = [];
  if (spot.btc) t.push(tile("Bitcoin", fmt.usd0(spot.btc), pctDelta(cs.btc_price)));
  if (spot.eth) t.push(tile("Ether", fmt.usd0(spot.eth), pctDelta(cs.eth_price)));
  if (spot.total_mcap) t.push(tile("Crypto mkt cap", "$" + compact(spot.total_mcap), spot.mcap_change_24h));
  if (spot.btc_dominance) t.push(tile("BTC dominance", spot.btc_dominance.toFixed(1) + "%", null));
  if (ms.spx) t.push(tile("S&P 500", fmt.num(ms.spx.values.at(-1)), pctDelta(ms.spx)));
  if (ms.dgs10) t.push(tile("10Y yield", fmt.pct2(ms.dgs10.values.at(-1)),
    (ms.dgs10.values.at(-1) - ms.dgs10.values.at(-2)) * 100, "bp"));
  const dollar = ms.dxy?.values?.length ? ms.dxy : ms.dxy_broad;
  if (dollar) t.push(tile("Dollar", dollar.values.at(-1).toFixed(1), pctDelta(dollar)));
  if (ms.gold) t.push(tile("Gold", fmt.usd0(ms.gold.values.at(-1)), pctDelta(ms.gold)));
  if (ms.vix) t.push(tile("VIX", ms.vix.values.at(-1).toFixed(1), null));
  if (cs.fng) t.push(tile("Fear & Greed", Math.round(cs.fng.values.at(-1)) + "/100", null));
  const war = DATA.signals?.war;
  if (war && war.state) {
    const words = { aligned: "Calm", disruption_priced: "Disruption, priced",
                    disruption_underpriced: "Underpriced risk", premium_no_disruption: "Fear premium" };
    t.push(`<a class="tile" href="war.html" style="text-decoration:none;color:inherit">
      <div class="t-label">War risk</div>
      <div class="t-value" style="font-size:16px;line-height:1.3;padding-top:3px">${words[war.state] || war.state}</div>
      <div class="t-delta ${war.signal === "caution" ? "neg" : war.signal === "good" ? "pos" : "flat"}">Open monitor →</div></a>`);
  }
  el.innerHTML = t.join("");
}

/* ------------------------------------------------- majors & sectors --- */
function renderMajors() {
  const majors = DATA.crypto?.majors || [];
  if (!majors.length) return;
  const grid = document.getElementById("grid-crypto");
  const el = document.createElement("div");
  el.className = "card list-card";
  el.innerHTML = `
    <div class="card-top"><div><h3 class="card-title">The Majors</h3>
      <p class="card-sub">Top coins by market cap</p></div></div>
    <table class="majors">
      <thead><tr><th>Asset</th><th>Price</th><th>24h</th><th>7d</th><th>Mkt cap</th></tr></thead>
      <tbody>${majors.map(c => `<tr>
        <td>${esc(c.name)}<span class="sym">${esc(c.symbol)}</span></td>
        <td>${fmt.usd2(c.price)}</td>
        <td class="${(c.chg24h || 0) >= 0 ? "pos" : "neg"}">${c.chg24h == null ? "–" : c.chg24h.toFixed(1) + "%"}</td>
        <td class="${(c.chg7d || 0) >= 0 ? "pos" : "neg"}">${c.chg7d == null ? "–" : c.chg7d.toFixed(1) + "%"}</td>
        <td>$${compact(c.mcap || 0)}</td></tr>`).join("")}
      </tbody></table>
    <div class="card-foot"><span>Prices refresh with the pipeline, not live</span><span>CoinGecko</span></div>`;
  grid.appendChild(el);
}

function renderSectors() {
  const sectors = DATA.crypto?.sectors || [];
  if (!sectors.length) return;
  const grid = document.getElementById("grid-crypto");
  const max = Math.max(...sectors.map(s => Math.abs(s.chg24h)), 1);
  const el = document.createElement("div");
  el.className = "card list-card";
  el.innerHTML = `
    <div class="card-top"><div><h3 class="card-title">Sector Rotation</h3>
      <p class="card-sub">Best and worst crypto sectors, 24h market-cap change</p></div></div>
    <div>${sectors.map(s => {
      const w = Math.abs(s.chg24h) / max * 100;
      const pos = s.chg24h >= 0;
      return `<div class="sectorbar"><span class="sname" title="${esc(s.name)}">${esc(s.name)}</span>
        <div class="bar" style="width:${Math.max(3, w * 0.55)}%;background:${pos ? C.good : C.warn}"></div>
        <span class="bval ${pos ? "pos" : "neg"}">${pos ? "+" : ""}${s.chg24h.toFixed(1)}%</span></div>`;
    }).join("")}</div>
    <div class="card-foot"><span>Rotation shows where speculative money is moving — durable trends need more than a day</span><span>CoinGecko</span></div>`;
  grid.appendChild(el);
}

/* ------------------------------------------------------ news/calendar --- */
function renderWeek() {
  const grid = document.getElementById("grid-week");
  const cal = DATA.newscal?.calendar || [];
  const news = DATA.newscal?.news || [];

  const calEl = document.createElement("div");
  calEl.className = "card list-card";
  const interesting = cal.filter(e => e.impact === "High" || e.impact === "Medium").slice(0, 14);
  const rows = (interesting.length ? interesting : cal.slice(0, 12)).map(e => {
    const d = new Date(e.date);
    const when = isFinite(d) ? `${MONTHS[d.getMonth()]} ${d.getDate()}` : "";
    const fx = [e.forecast && `f: ${e.forecast}`, e.previous && `prev: ${e.previous}`].filter(Boolean).join(" · ");
    return `<div class="rowitem"><span class="impact-dot impact-${esc(e.impact)}"></span>
      <span class="cal-when">${when}<br>${esc(e.country)}</span>
      <span>${esc(e.title)}${fx ? `<div class="cal-fx">${esc(fx)}</div>` : ""}</span></div>`;
  }).join("");
  calEl.innerHTML = `
    <div class="card-top"><div><h3 class="card-title">Economic Calendar</h3>
      <p class="card-sub">High- and medium-impact events this week — these move markets on release</p></div></div>
    <div class="rowlist">${rows || '<div class="rowitem">Calendar unavailable — auto-retries on next refresh.</div>'}</div>
    <div class="card-foot"><span>Times are release days (UTC-ish)</span><span>ForexFactory</span></div>`;
  grid.appendChild(calEl);

  const newsEl = document.createElement("div");
  newsEl.className = "card list-card";
  newsEl.innerHTML = `
    <div class="card-top"><div><h3 class="card-title">Headlines</h3>
      <p class="card-sub">Latest macro &amp; crypto headlines from public feeds</p></div></div>
    <div class="rowlist">${news.slice(0, 14).map(n => `
      <div class="rowitem"><span class="impact-dot" style="background:${n.kind === "macro" ? C.camel : C.accent}"></span>
        <span><a href="${esc(n.link)}" target="_blank" rel="noopener">${esc(n.title)}</a>
        <div class="row-meta">${esc(n.source)} · ${relTime(n.published)}</div></span></div>`).join("")}</div>
    <div class="card-foot"><span>Headlines link to the original source</span><span>RSS</span></div>`;
  grid.appendChild(newsEl);
}

/* --------------------------------------------------------- methodology --- */
function renderMethod() {
  const grid = document.getElementById("grid-method");
  const cards = [
    ["Liquidity Impulse", GAUGE_EXPLAINERS.liquidity_impulse],
    ["Risk Appetite", GAUGE_EXPLAINERS.risk_appetite],
    ["Crypto Cycle", GAUGE_EXPLAINERS.crypto_cycle],
  ].map(([t, b]) => `<div class="method-card"><h3>${t}</h3><p>${esc(b)}</p></div>`);
  cards.push(`<div class="method-card"><h3>Freshness &amp; failure</h3>
    <p>A scheduled pipeline refreshes all data several times a day, validates every series
    (freshness + plausibility) and keeps the last good copy when a source hiccups —
    each card's footer shows exactly how recent its data is. If something breaks for real,
    the repository opens an alert automatically.</p></div>`);
  grid.innerHTML = cards.join("");
}

/* -------------------------------------------------------------- status --- */
function renderStatus() {
  const gen = DATA.meta?.generated_at || DATA.signals?.generated_at;
  const dot = document.getElementById("status-dot");
  const txt = document.getElementById("status-text");
  if (!gen) { txt.textContent = "No data"; dot.classList.add("stale"); return; }
  const ageH = (Date.now() - new Date(gen).getTime()) / 36e5;
  const bad = Object.values(DATA.meta?.sources || {}).filter(s => s && s.ok === false);
  if (ageH > 26 || bad.length) {
    dot.classList.add("stale");
    txt.textContent = ageH > 26 ? `Updated ${relTime(gen)}` : `Updated ${relTime(gen)} · ${bad.length} source issue`;
  } else {
    txt.textContent = `Updated ${relTime(gen)}`;
  }
  document.getElementById("foot-status").textContent =
    `Pipeline last ran ${relTime(gen)}` + (bad.length ? ` · degraded: ${bad.map(([k]) => k).join(", ")}` : "");
  document.getElementById("repo-link").href = REPO_URL;
}

/* ---------------------------------------------------------------- main --- */
(async function main() {
  const names = ["macro", "crypto", "derivs", "newscal", "signals", "meta"];
  const docs = await Promise.all(names.map(loadJSON));
  names.forEach((n, i) => DATA[n] = docs[i]);

  for (const [key, txt] of Object.entries(SECTION_INTROS)) {
    const el = document.getElementById(`intro-${key}`);
    if (el) el.textContent = txt;
  }
  renderStatus();
  renderRegime();
  renderGauges();
  renderTiles();
  renderPlaybook();
  for (const cfg of CHARTS) renderCard(cfg);
  renderMajors();
  renderSectors();
  renderWeek();
  renderMethod();
})();
