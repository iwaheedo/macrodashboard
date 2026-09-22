/* Waypoint — War Risk page. Loads data/war.json (+ macro.json for context
 * stats) and renders the divergence banner, flows-vs-price tracker,
 * chokepoint monitor, theater playbooks and the war wire.
 * Shares design tokens with app.js; helpers are duplicated on purpose to
 * keep both pages dependency-free (no build step). */
"use strict";

const C = {
  ink: "#2A2014", ink2: "#6E5C49", ink3: "#A08D77",
  line: "#E7DFD1", accent: "#8A5731", camel: "#C3A583",
  deep: "#5F3A1E", clay: "#A9713F", stone: "#8C7A66",
  good: "#3F7352", warn: "#B95C33",
  goodSoft: "rgba(63,115,82,.14)", warnSoft: "rgba(185,92,51,.13)",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const tickLabel = iso => MONTHS[+iso.slice(5, 7) - 1] + " ’" + iso.slice(2, 4);
const fullDate = iso => MONTHS[+iso.slice(5, 7) - 1] + " " + (+iso.slice(8, 10)) + ", " + iso.slice(0, 4);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function relTime(iso) {
  const t = new Date(iso).getTime();
  if (!isFinite(t)) return "";
  const m = Math.max(0, (Date.now() - t) / 60000);
  return m < 60 ? Math.round(m) + "m ago" : m < 2160 ? Math.round(m / 60) + "h ago" : Math.round(m / 1440) + "d ago";
}
function asof(dates, values, iso) {
  let lo = 0, hi = dates.length - 1, ans = -1;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (dates[m] <= iso) { ans = m; lo = m + 1; } else hi = m - 1; }
  return ans < 0 ? null : values[ans];
}

Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
Chart.defaults.font.size = 11.5;
Chart.defaults.color = C.ink3;
Chart.defaults.animation = false;
Chart.defaults.elements.point.radius = 0;
Chart.defaults.elements.point.hoverRadius = 4;
Chart.defaults.plugins.legend.display = false;

/* ------------------------------------------------------------ theaters --- */
const THEATERS = [
  {
    id: "iran", title: "Iran — Gulf & Strait of Hormuz",
    stakes: "Roughly a fifth of the world's oil and a quarter of its LNG normally exits through Hormuz, a strait ~30km wide at its narrowest. There is no full workaround: Saudi and Emirati bypass pipelines can reroute only a fraction of it.",
    channels: [
      ["Oil & LNG", "The main channel. Any credible threat to Hormuz puts a premium on every barrel, everywhere."],
      ["Shipping & insurance", "War-risk premiums on Gulf routes reprice within days and pass through into goods prices."],
      ["Inflation → rates", "An oil spike is inflation the Fed cannot cut against — it tightens policy expectations at the worst moment."],
    ],
    escalate: "Escalation (strikes on export infrastructure, tanker attacks, mining attempts) → oil gaps higher, equities fall with energy the lone green sector, gold and the dollar catch the safety bid, yields whipsaw between growth fear and inflation fear. Crypto has historically traded as pure risk-off in the first move — it sells with equities, not with gold.",
    deescalate: "De-escalation (talks, verified flow recovery) → the premium bleeds out of oil in weeks; equities recover led by the sectors that were sold hardest; the safety bid in gold fades slowly rather than instantly.",
    watch: ["hormuz", "brent"],
  },
  {
    id: "redsea", title: "Red Sea — Bab el-Mandeb & Suez",
    stakes: "The Suez–Red Sea route normally carries ~12–15% of global trade and nearly a third of container traffic. Houthi attacks since 2023 pushed much of it around the Cape of Good Hope: 10–14 extra days and higher freight per voyage.",
    channels: [
      ["Freight & goods inflation", "Rerouting is a slow-burn cost shock — it shows up in goods prices with a lag, not in a single headline."],
      ["Oil (moderate)", "Crude can reroute; the bigger oil story is always Hormuz. Watch products and LNG timing instead."],
      ["Europe first", "Asia–Europe lanes bear the cost; European industry feels it before the US does."],
    ],
    escalate: "Escalation (attacks widening, insurers withdrawing cover) → Cape traffic surges, freight indices jump, European inflation prints firm up, and the market treats it as a growth tax rather than a panic event.",
    deescalate: "De-escalation (safe-passage deals holding) → Suez transits recover within weeks — that recovery is visible in this page's Suez and Cape lines before it reaches official trade data.",
    watch: ["bab_el_mandeb", "suez", "cape_good_hope"],
  },
  {
    id: "ukraine", title: "Russia — Ukraine & the Black Sea",
    stakes: "The channels are energy (European gas above all), Black Sea grain and fertilizer, and the sanctions regime on Russian crude. Markets have largely adapted since 2022 — the tail risk is direct NATO involvement or attacks on export infrastructure.",
    channels: [
      ["European gas & power", "The dominant channel for Europe: TTF gas prices set the continent's industrial cost base."],
      ["Food & fertilizer", "Black Sea disruption feeds straight into global food inflation — an emerging-markets stress channel."],
      ["Sanctions & the shadow fleet", "Tightening enforcement squeezes Russian barrels back out of the market and firms up crude."],
    ],
    escalate: "Escalation (energy infrastructure strikes, Black Sea corridor closure, NATO incident) → European equities and the euro lead the downside, gas and wheat spike, and the safe-haven bid runs to the dollar, gold and Treasuries.",
    deescalate: "A durable ceasefire → European assets re-rate higher, gas premium collapses, and the 'peace trade' historically favors beaten-down European industrials and EM food importers.",
    watch: ["bosporus", "kerch"],
  },
  {
    id: "taiwan", title: "China — Taiwan Strait",
    stakes: "The biggest tail risk on the board. Taiwan fabricates ~90% of leading-edge chips; the strait and the surrounding lanes carry a large share of East Asian trade. There is no rerouting a blockade of chips.",
    channels: [
      ["Semiconductors", "A supply cutoff would be a global tech shock with no substitute capacity for years."],
      ["Everything China", "Sanctions spirals would hit the largest trade relationships on earth simultaneously."],
      ["Shipping", "Taiwan, Luzon and Korea strait flows are the early physical tell — blockade drills show up there first."],
    ],
    escalate: "Escalation (blockade, quarantine, live-fire closures) → this is the scenario markets cannot hedge cheaply: tech and semis gap down globally, safe havens are bid indiscriminately, and correlations go to one. Even drills that close lanes for days move chip stocks.",
    deescalate: "Status-quo reaffirmation → the risk premium never fully leaves, but markets revert to pricing earnings, not geography.",
    watch: ["taiwan_strait"],
  },
];

/* ------------------------------------------------------------- loading --- */
const DATA = {};
async function loadJSON(name) {
  try {
    const r = await fetch(`data/${name}.json`, { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch (e) { console.warn(`missing data/${name}.json`, e); return null; }
}

const chipWords = { good: "Supportive", caution: "Caution", neutral: "Neutral", info: "Context" };
const chip = sig => `<span class="chip ${sig}">${chipWords[sig] || sig}</span>`;
const nowBox = r => r ? `<div class="now ${r.signal}"><span class="now-tag">Right now</span>${esc(r.text)}</div>` : "";

/* ---------------------------------------------------------- banner ------ */
function renderBanner() {
  const d = DATA.war?.divergence;
  const el = document.getElementById("divergence-banner");
  if (!d) { el.innerHTML = ""; return; }
  const tone = d.signal === "good" ? "good" : d.signal === "caution" ? "caution" : "info";
  el.innerHTML = `
    <div class="banner ${tone}">
      <div class="banner-eyebrow">Flows ↔ price divergence check</div>
      <div class="banner-title">${esc(d.title)}</div>
      <div class="banner-stats">
        <div class="bstat"><span>Corridor tanker flow vs pre-war</span><b>${d.corridor_dev_pct == null ? "–" : (d.corridor_dev_pct > 0 ? "+" : "") + d.corridor_dev_pct + "%"}</b></div>
        <div class="bstat"><span>Brent, 30-day change</span><b>${d.brent_chg30_pct == null ? "–" : (d.brent_chg30_pct > 0 ? "+" : "") + d.brent_chg30_pct + "%"}</b></div>
        <div class="bstat"><span>Brent</span><b>$${DATA.war.brent.values.at(-1).toFixed(0)}</b></div>
      </div>
      <p class="banner-text">${esc(d.text)}</p>
    </div>`;
}

/* ---------------------------------------------------------- tracker ----- */
function renderTracker() {
  const grid = document.getElementById("grid-tracker");
  const w = DATA.war;
  if (!w) {
    grid.innerHTML = `<div class="card full unavailable"><div class="chart-box">Flow data unavailable — auto-retries on next refresh.</div></div>`;
    return;
  }
  const el = document.createElement("div");
  el.className = "card full";
  el.innerHTML = `
    <div class="card-top"><div>
      <h3 class="card-title">Middle-East Corridor: Tankers vs Brent</h3>
      <p class="card-sub">14-day average tanker transits per day (left) against Brent crude (right)</p>
    </div></div>
    <div class="chart-box full-h"><canvas id="cv-corridor"></canvas></div>
    ${["hormuz", "bab_el_mandeb", "suez"].map(k => nowBox(w.reads[k])).join("")}
    ${nowBox(w.reads.brent)}
    <div class="explain">
      <div class="e-what"><h4>What you're looking at</h4><p>Ships broadcast their position (AIS); the IMF counts tanker transits through each strait daily. This is the closest free proxy for barrels physically leaving the Gulf and Red Sea — plotted against the price the market charges for those barrels.</p></div>
      <div><h4><span class="arrow-down">↓</span> If flows fall</h4><p>Physical supply is being disrupted — or tankers are hiding their signals in a war zone. Either reading raises real supply risk, and a price that ignores it is complacent.</p></div>
      <div><h4><span class="arrow-up">↑</span> If price runs without flows falling</h4><p>That's a fear premium, not a shortage. Premia without physical follow-through have historically bled out within weeks.</p></div>
    </div>
    <div class="card-foot"><span>Data through ${fullDate(w.chokepoints.hormuz.dates.at(-1))}</span><span>IMF PortWatch · FRED (Brent)</span></div>`;
  grid.appendChild(el);

  const cps = w.chokepoints;
  const labels = cps.hormuz.dates;
  const brentVals = labels.map(d => asof(w.brent.dates, w.brent.values, d));
  const mk = (key, color, dash) => ({
    label: cps[key].label, data: cps[key].tankers_ma14, borderColor: color,
    borderDash: dash || [], borderWidth: 2, yAxisID: "y",
  });
  new Chart(document.getElementById("cv-corridor"), {
    type: "line",
    data: { labels, datasets: [
      mk("hormuz", C.deep),
      mk("bab_el_mandeb", C.clay, [6, 4]),
      mk("suez", C.camel, [2, 3]),
      { label: "Brent ($)", data: brentVals, borderColor: C.warn, borderWidth: 2,
        yAxisID: "y2" },
    ]},
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { grid: { display: false }, border: { color: C.line },
             ticks: { maxTicksLimit: 6, maxRotation: 0, autoSkipPadding: 28,
                      callback(v) { return tickLabel(this.getLabelForValue(v)); } } },
        y: { position: "left", title: { display: true, text: "tankers / day", color: C.ink3 },
             grid: { color: "rgba(231,223,209,.55)", drawTicks: false },
             border: { display: false }, ticks: { maxTicksLimit: 6 } },
        y2: { position: "right", title: { display: true, text: "Brent $/bbl", color: C.warn },
              grid: { display: false }, border: { display: false },
              ticks: { maxTicksLimit: 6, color: C.warn, callback: v => "$" + v } },
      },
      plugins: {
        legend: { display: true, position: "top", align: "start",
                  labels: { boxWidth: 14, boxHeight: 2, padding: 14, color: C.ink2, font: { size: 12 } } },
        tooltip: { backgroundColor: "#FFF", titleColor: C.ink, bodyColor: C.ink2,
                   borderColor: C.line, borderWidth: 1, cornerRadius: 10, padding: 10,
                   callbacks: { title: items => items.length ? fullDate(items[0].label) : "" } },
      },
    },
  });
}

/* -------------------------------------------------------- chokepoints --- */
function renderChokepoints() {
  const grid = document.getElementById("grid-chokepoints");
  const w = DATA.war;
  if (!w) return;
  for (const [key, cp] of Object.entries(w.chokepoints)) {
    const read = w.reads[key];
    const dev = cp.dev_pct;
    const devTxt = dev == null ? "–" : (dev > 0 ? "+" : "") + dev.toFixed(0) + "%";
    const devCls = dev == null ? "flat" : (key === "cape_good_hope" ? (dev > 25 ? "neg" : "pos")
                                                                    : (dev < -25 ? "neg" : dev < -10 ? "flat" : "pos"));
    const el = document.createElement("div");
    el.className = "card";
    el.innerHTML = `
      <div class="card-top"><div>
        <h3 class="card-title">${esc(cp.label)}</h3>
        <p class="card-sub">14-day avg: <b>${cp.ma14_last ?? "–"}</b> tankers/day · norm: ${cp.baseline ?? "–"}<br>${esc(cp.baseline_label || "")}</p>
      </div><span class="t-delta ${devCls}" style="font-size:15px">${devTxt}</span></div>
      <div class="chart-box mini"><canvas id="cv-cp-${key}"></canvas></div>
      ${nowBox(read)}`;
    grid.appendChild(el);
    new Chart(document.getElementById(`cv-cp-${key}`), {
      type: "line",
      data: { labels: cp.dates, datasets: [{
        data: cp.tankers_ma14, borderColor: key === "cape_good_hope" ? C.stone : C.accent,
        borderWidth: 1.8, fill: false,
      }]},
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: {
          x: { grid: { display: false }, border: { color: C.line },
               ticks: { maxTicksLimit: 4, maxRotation: 0,
                        callback(v) { return tickLabel(this.getLabelForValue(v)); } } },
          y: { position: "right", grid: { color: "rgba(231,223,209,.5)", drawTicks: false },
               border: { display: false }, ticks: { maxTicksLimit: 4 } },
        },
        plugins: { tooltip: { backgroundColor: "#FFF", titleColor: C.ink, bodyColor: C.ink2,
                              borderColor: C.line, borderWidth: 1, cornerRadius: 8, padding: 8,
                              callbacks: { title: items => items.length ? fullDate(items[0].label) : "" } } },
        interaction: { mode: "index", intersect: false },
      },
    });
  }
}

/* ----------------------------------------------------------- theaters --- */
function watchChips(t) {
  const w = DATA.war;
  const bits = [];
  for (const key of t.watch) {
    if (key === "brent") {
      bits.push(`Brent <b>$${w.brent.values.at(-1).toFixed(0)}</b>`);
    } else {
      const cp = w.chokepoints[key];
      if (cp && cp.dev_pct != null)
        bits.push(`${esc(cp.label)} <b>${cp.dev_pct > 0 ? "+" : ""}${cp.dev_pct.toFixed(0)}%</b> vs pre-war`);
    }
  }
  const vix = DATA.macro?.series?.vix;
  if (vix) bits.push(`VIX <b>${vix.values.at(-1).toFixed(1)}</b>`);
  const gold = DATA.macro?.series?.gold;
  if (gold) bits.push(`Gold <b>$${Math.round(gold.values.at(-1)).toLocaleString()}</b>`);
  return bits.map(b => `<span class="watch-chip">${b}</span>`).join("");
}

function renderTheaters() {
  const grid = document.getElementById("grid-theaters");
  if (!DATA.war) return;
  for (const t of THEATERS) {
    const el = document.createElement("div");
    el.className = "card";
    el.innerHTML = `
      <div class="card-top"><div><h3 class="card-title">${esc(t.title)}</h3></div></div>
      <p class="theater-stakes">${esc(t.stakes)}</p>
      <div class="risk-rows">
        ${t.channels.map(([name, txt]) => `<div class="risk-row"><span class="risk-name">${esc(name)}</span><span class="risk-txt">${esc(txt)}</span></div>`).join("")}
      </div>
      <div class="explain" style="border-top:1px solid var(--line-soft); padding-top:12px;">
        <div><h4><span class="arrow-down">▲</span> If it escalates</h4><p>${esc(t.escalate)}</p></div>
        <div><h4><span class="arrow-up">▼</span> If it de-escalates</h4><p>${esc(t.deescalate)}</p></div>
      </div>
      <div class="watch-row"><span class="watch-label">Live watch</span>${watchChips(t)}</div>`;
    grid.appendChild(el);
  }
}

/* ---------------------------------------------------------- war news ---- */
function renderWarNews() {
  const grid = document.getElementById("grid-warnews");
  const news = DATA.war?.news || [];
  const el = document.createElement("div");
  el.className = "card list-card full";
  el.innerHTML = `
    <div class="rowlist">${news.length ? news.map(n => `
      <div class="rowitem"><span class="impact-dot" style="background:${n.kind === "maritime" ? C.camel : C.warn}"></span>
        <span><a href="${esc(n.link)}" target="_blank" rel="noopener">${esc(n.title)}</a>
        <div class="row-meta">${esc(n.source)} · ${relTime(n.published)}</div></span></div>`).join("")
      : '<div class="rowitem">War wire unavailable — auto-retries on next refresh.</div>'}</div>
    <div class="card-foot"><span>Filtered for conflict &amp; chokepoint relevance; links go to the original source</span><span>Al Jazeera · BBC · gCaptain · market feeds</span></div>`;
  grid.appendChild(el);
}

/* ------------------------------------------------------------- method --- */
function renderMethod() {
  document.getElementById("grid-method").innerHTML = `
    <div class="method-card"><h3>The flows &amp; pre-war baselines</h3>
      <p>IMF PortWatch estimates daily transit counts per chokepoint from satellite AIS ship
      signals, with a ~2–4 day lag. Each strait is measured against its own last-normal
      period, not a global year: Hormuz vs Nov ’24–Oct ’25 (its last calm year before the
      current crisis), the Red Sea routes vs Jan–Oct ’23 (before the Houthi campaign), the
      Black Sea straits vs 2019–Jan ’22 (before the invasion of Ukraine), Taiwan vs its
      recent calm norm. "Corridor flow" is the average deviation of Hormuz, Bab el-Mandeb
      and Suez from those baselines.</p></div>
    <div class="method-card"><h3>The divergence check</h3>
      <p>Flows more than 25% below norm counts as disruption; Brent up more than 10% in 30 days
      counts as a hot price. The four combinations produce the banner above. Thresholds are
      deliberately simple and fixed — the point is catching disagreement, not precision.</p></div>
    <div class="method-card"><h3>Where this can be wrong</h3>
      <p>AIS is self-reported: in war zones, jamming, spoofing and deliberate "dark sailing"
      reduce observed counts below real traffic — so a flow collapse can overstate the physical
      shortfall. Pipelines (Saudi East–West, UAE Fujairah) can bypass part of Hormuz. Treat
      flow readings as a strong signal to investigate, never as a settled fact.</p></div>
    <div class="method-card"><h3>Refresh cadence</h3>
      <p>The pipeline refreshes every 4 hours (data, reads, and this banner). Chokepoint data
      carries the IMF's own publication lag; each card shows its data-through date. No AI/LLM
      is involved anywhere — every sentence that changes is deterministic, rule-based text.</p></div>`;
}

/* -------------------------------------------------------------- status -- */
function renderStatus() {
  const gen = DATA.war?.fetched_at || DATA.meta?.generated_at;
  const txt = document.getElementById("status-text");
  const dot = document.getElementById("status-dot");
  if (!gen) { txt.textContent = "No data"; dot.classList.add("stale"); return; }
  const ageH = (Date.now() - new Date(gen).getTime()) / 36e5;
  if (ageH > 26) dot.classList.add("stale");
  txt.textContent = `Updated ${relTime(gen)}`;
  document.getElementById("foot-status").textContent =
    `War-risk data last refreshed ${relTime(gen)} · flows lag ~2–4 days (IMF publication schedule)`;
}

/* ---------------------------------------------------------------- main --- */
(async function main() {
  const [war, macro, meta] = await Promise.all([loadJSON("war"), loadJSON("macro"), loadJSON("meta")]);
  DATA.war = war; DATA.macro = macro; DATA.meta = meta;
  renderStatus();
  renderBanner();
  renderTracker();
  renderChokepoints();
  renderTheaters();
  renderWarNews();
  renderMethod();
})();
