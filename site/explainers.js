/* Static educational content for every chart: what you're looking at and what
 * a move in each direction has historically meant. Original text, written to be
 * read by a human in a hurry. The live "Right now" line comes from signals.json.
 */
const EXPLAINERS = {
  net_liquidity: {
    what: "Dollars the Fed system is effectively supplying to markets: its balance sheet minus the Treasury's checking account (TGA) and money parked back at the Fed (reverse repo). Many traders watch this as the tide that floats or sinks all risk assets.",
    up: "More dollars sloshing around → historically supportive for stocks and especially crypto, often with a few weeks' lag.",
    down: "Liquidity is being drained (QT, Treasury rebuilding its account) → risk assets fight a headwind and rallies get sold.",
  },
  global_cb: {
    what: "The combined balance sheets of the Fed, ECB and Bank of Japan, converted to dollars. This is the closest simple proxy for 'global money printing'.",
    up: "Global easing → more money chasing assets. Bitcoin and gold have historically been the biggest beneficiaries of this impulse.",
    down: "Global tightening → the world's liquidity pool shrinks; expensive, speculative assets usually feel it first and hardest.",
  },
  m2_yoy: {
    what: "How fast the US money supply (cash + deposits + money-market funds) is growing versus a year ago. The long-run fuel gauge for both asset prices and inflation.",
    up: "Accelerating money growth → supportive for asset prices over the following year, and eventually inflationary if it runs hot.",
    down: "Decelerating or negative growth (rare) → disinflationary and restrictive; 2022's crypto/equity bear happened as M2 growth collapsed.",
  },
  cpi: {
    what: "US consumer price inflation, year over year — headline (everything) and core (excluding volatile food and energy). This is the number that dictates how friendly the Fed can be.",
    up: "Re-accelerating inflation → the Fed must stay tight or tighten more; bad for bonds first, then usually stocks and crypto.",
    down: "Cooling toward 2% → gives the Fed cover to cut rates. Falling inflation with okay growth is the sweet spot for risk assets.",
  },
  policy_rates: {
    what: "The Fed's overnight policy rate alongside 2-year and 10-year Treasury yields. The 2Y is the market's forecast of Fed policy; the 10Y prices growth and inflation further out and sets the discount rate for everything else.",
    up: "Rising yields → borrowing costs up, future profits worth less today. Long-duration assets (tech, crypto) are the most sensitive.",
    down: "Falling yields → easier conditions and richer valuations — as long as the fall is about cooling inflation, not collapsing growth.",
  },
  unrate: {
    what: "The US unemployment rate. It moves slowly — until it doesn't. What matters most is not the level but a rise off the lows.",
    up: "A rise of ~0.5pp off the 12-month low has historically meant a recession is beginning (the Sahm rule) — the signal that turns bad news into actually-bad news.",
    down: "Low and stable unemployment → incomes and spending hold up; recession risk stays dormant.",
  },
  yield_curve: {
    what: "The gap between long and short Treasury yields (10Y−2Y and 10Y−3M). Inversion (below zero) means investors accept less for lending longer — a bet that rates will be cut because something breaks.",
    up: "Steepening from inversion is late-cycle behavior: watch WHY — cuts into weakness (bad) vs. growth repricing (fine). A normal upward slope is healthy.",
    down: "Inverting → the bond market is pricing a downturn. Every US recession since the 1970s was preceded by inversion, typically 6–18 months ahead.",
  },
  hy_oas: {
    what: "The extra yield junk-rated companies must pay over Treasuries. Credit investors are professionally paranoid, which makes this one of the best early-warning gauges in finance.",
    up: "Widening spreads → default risk is being repriced; equity and crypto weakness usually follows or accelerates. Above ~5% is genuine stress.",
    down: "Tight spreads → confidence (or complacency). Very tight spreads mean markets are priced for perfection — fragile, but not bearish by itself.",
  },
  dollar: {
    what: "The dollar's value against other major currencies. Most global debt and trade is priced in dollars, so a strong dollar tightens conditions for the whole world.",
    up: "Stronger dollar → global headwind; commodities, emerging markets and crypto have historically struggled in strong-dollar phases.",
    down: "Weaker dollar → the classic tailwind. Bitcoin's biggest bull runs (2017, 2020–21) coincided with a falling dollar.",
  },
  spx: {
    what: "The S&P 500 with its 200-day moving average — the simplest trend line professionals actually use. Above it, the market is innocent until proven guilty; below it, the opposite.",
    up: "Price above a rising 200-day → healthy uptrend; buying dips has historically been the right playbook in this state.",
    down: "Price below the 200-day → the regime where crashes and extended bear markets have happened. Risk management matters more than being right.",
  },
  nasdaq: {
    what: "The Nasdaq Composite with its 200-day average — the risk-appetite end of the equity market and the closest equity cousin to crypto.",
    up: "Tech leading upward → risk appetite is broad; crypto rarely does badly while the Nasdaq is trending up.",
    down: "Tech breaking down → the speculative end is being sold; crypto typically feels the same pressure, amplified.",
  },
  vix: {
    what: "The market's expectation of S&P 500 volatility over the next 30 days — the 'fear gauge'. Low = calm, high = panic.",
    up: "A spike means forced selling and fear. Counterintuitively, extreme spikes (>30) have historically happened near tradeable bottoms, not tops.",
    down: "Sub-14 calm is comfortable but breeds leverage and complacency — shocks hit harder from a low-VIX starting point.",
  },
  gold: {
    what: "The oldest hedge against currency debasement and geopolitical mess. Gold competes with bonds: it shines when real yields fall and when trust in the system weakens.",
    up: "Rising gold → markets are paying up for insurance — expecting easier policy, sticky inflation, or trouble. Often a leading signal for Bitcoin.",
    down: "Falling gold → confidence in real yields and the dollar; insurance is being sold off.",
  },
  oil: {
    what: "WTI crude — the price of energy, which is embedded in the price of everything else. Oil is a tax when it rises and a stimulus check when it falls.",
    up: "An oil spike squeezes consumers and re-ignites inflation — one of the few things that can force central banks to stay hawkish in a slowdown.",
    down: "Cheap oil is disinflationary stimulus — it quietly does rate-cuts' job for the Fed.",
  },
  btc: {
    what: "Bitcoin against its three most-watched reference lines: the 200-day average (trend), the 200-week average (the historical bear-market floor), and the realized price (the network's average cost basis).",
    up: "Holding above all three → bull-market structure. The 200-week line has marked the bottom zone of every previous cycle.",
    down: "Losing the 200-day is a warning; trading below realized price means the average holder is underwater — historically max-pain, max-opportunity territory.",
  },
  rainbow: {
    what: "Bitcoin's full price history on a log scale, with bands drawn around its long-term growth path (a regression fitted to all history). Not physics — just a disciplined way to see 'cheap vs. expensive' relative to Bitcoin's own trajectory.",
    up: "Price climbing into the upper bands → froth building; previous visits to the top band were 2013/2017/2021-style manias.",
    down: "Price in the lower bands → historically the zone where patient accumulation was rewarded, even though headlines were at their worst.",
  },
  mvrv: {
    what: "Market value ÷ realized value: how much profit the average bitcoin is sitting on. At 2.0, the average coin has doubled since it last moved. The single most-cited on-chain valuation gauge.",
    up: "High MVRV (>3) → enormous paper profits waiting to be taken; every previous cycle top formed in that zone.",
    down: "MVRV near or below 1 → the market trades at or under its cost basis; capitulation. These readings marked the 2015, 2018 and 2022 bottoms.",
  },
  mayer: {
    what: "Price divided by the 200-day moving average. A one-number answer to 'how stretched is Bitcoin right now?'",
    up: "Above ~2.4 → price is 140%+ above trend; historically unsustainable, mean-reversion usually followed.",
    down: "Below ~0.8 → deeply below trend; historically among the best long-term entry zones ever measured.",
  },
  fng: {
    what: "A 0–100 composite of crypto sentiment (volatility, momentum, social buzz, dominance). Useful mostly at the extremes — as a contrarian signal.",
    up: "Extreme greed (>75) → the crowd is all-in and upside is borrowed from the future; discipline beats FOMO here.",
    down: "Extreme fear (<25) → the crowd has given up. Historically the zone where long-term buyers were paid for their nerve.",
  },
  stables: {
    what: "Total supply of dollar stablecoins (USDT, USDC, …) — the cash sitting inside the crypto system, one click away from buying. Think of it as crypto's dry powder.",
    up: "Growing supply → fresh dollars entering the ecosystem; fuel for the next leg up.",
    down: "Shrinking supply → capital is exiting crypto entirely, not rotating — rallies without stablecoin growth run on fumes.",
  },
  eth: {
    what: "Ether, the second-largest crypto asset — the market's proxy for smart-contract platforms and higher-beta crypto risk generally.",
    up: "ETH strength usually means risk appetite is extending beyond Bitcoin into the rest of the market.",
    down: "ETH weakness while BTC holds → the market is playing defense inside crypto.",
  },
  ethbtc: {
    what: "Ether priced in bitcoin — crypto's internal risk dial. It answers one question: is money flowing out along the risk curve, or huddling in BTC?",
    up: "Rising ETH/BTC → risk-seeking rotation; historically this is when altcoin seasons happened.",
    down: "Falling ETH/BTC → defensive rotation into Bitcoin; alt-heavy portfolios underperform in this state.",
  },
  hashrate: {
    what: "Total computing power securing Bitcoin. Miners commit hardware and electricity months in advance — hashrate is their real-money bet on Bitcoin's future.",
    up: "New highs → miners keep investing; network security and miner conviction at maximum.",
    down: "A sustained drop (>10–15% from peak) → miners are capitulating, usually near cycle lows when price no longer covers their costs.",
  },
  active_addr: {
    what: "Unique Bitcoin addresses active on-chain each day — a rough gauge of actual network usage rather than price speculation.",
    up: "Rising usage alongside rising price → the move has fundamental participation behind it.",
    down: "Falling usage during a rally → price is moving on leverage and thin participation; treat the move with more suspicion.",
  },
  costbasis: {
    what: "Bitcoin against the market's cost-basis ladder: the realized price (what the average coin was last bought for) and the short-term holder (STH) cost basis (what recent buyers paid). This is the market-structure view — who is in profit, and by how much.",
    up: "Price pulling far above both lines → everyone is in profit, and eventually that profit becomes selling pressure. A moderate premium over the STH line is what a healthy bull looks like.",
    down: "Losing the STH line traps recent buyers and turns rallies into exits; losing the realized price is full capitulation — historically where cycle bottoms formed.",
  },
  dominance: {
    what: "Bitcoin's share of the majors (BTC vs BTC+ETH+stablecoins — a proxy that tracks the same turns as headline BTC dominance). Cycles have a rotation rhythm: capital moves into BTC first, then down the risk curve.",
    up: "Rising off a cycle low → the early-bull pattern: money favors Bitcoin before it trusts anything else.",
    down: "Falling during an uptrend → rotation into ETH and alts (mid/late-bull behavior, historically when altseasons happened). Falling in a downtrend just means BTC is weak.",
  },
  etf: {
    what: "Daily net flows into US spot-Bitcoin ETFs — the institutional pipe. This is the structural demand channel this cycle has that earlier cycles didn't.",
    up: "Sustained net inflows → advisers and institutions are allocating; a persistent bid under the market that doesn't read Crypto Twitter.",
    down: "Sustained outflows → the marginal big buyer is gone; rallies need retail and leverage to carry them, which makes them more fragile.",
  },
  dex: {
    what: "Total daily trading volume on decentralized exchanges across all chains — a clean, un-fakeable proxy for real on-chain activity.",
    up: "Volume expanding with price → the reflexive loop is on: usage confirms the rally. Prior cycles saw activity multiply many-fold in the wealth-creation phase.",
    down: "Volume fading while price rises → the move is running on leverage and thin conviction — lower-quality rally.",
  },
  tvl: {
    what: "Total value locked in DeFi across all chains — crypto's internal credit system. Together with stablecoin supply, it's the closest thing to an on-chain money supply.",
    up: "Capital being redeployed into DeFi → the credit rebuild that historically powers the wealth-creation phase.",
    down: "TVL draining → risk appetite inside crypto contracting; the internal money supply is shrinking.",
  },
  funding: {
    what: "What perpetual-futures longs pay shorts (or vice versa) every 8 hours to keep their leveraged bets open. The purest real-time read on which side is crowded.",
    up: "High positive funding → leveraged longs are crowded and paying heavily; fuel for violent long-squeeze corrections.",
    down: "Negative funding → shorts pay longs; pessimism is crowded, and short squeezes become the path of least resistance.",
  },
  open_interest: {
    what: "The total dollar value of open BTC futures bets. More open interest = more leverage in the system = bigger moves in both directions.",
    up: "OI climbing fast → leverage building; combined with high funding it's the classic pre-liquidation-cascade setup.",
    down: "A sharp OI drop → a flush just happened; positioning is cleaner and moves become more 'honest' afterward.",
  },
  long_short: {
    what: "How many retail accounts are long versus short on OKX. Retail crowds are a reliable fade at extremes.",
    up: "Heavily long-skewed → the crowd is leaning one way; sharp moves against the crowd (down) hurt the most people.",
    down: "Short-skewed → fear is crowded; squeezes upward become easier to trigger.",
  },
};

const SECTION_INTROS = {
  liquidity: "The tide. Central-bank money creation is the slowest-moving but most powerful force under every market. Get the liquidity direction right and most other calls get easier.",
  rates: "The price of money. Rates, credit spreads and the dollar decide how expensive risk-taking is — and how much pain the system can absorb.",
  assets: "The scoreboard. What the big, liquid markets are actually doing — trend first, story second.",
  crypto: "The high-beta end. Bitcoin's valuation gauges, cycle position, and the flows inside the crypto ecosystem.",
  derivs: "The leverage check. Who is over-extended right now? Funding, open interest and positioning tell you where the forced selling (or buying) will come from.",
  week: "The calendar and the tape — what's scheduled and what just happened.",
};

const GAUGE_EXPLAINERS = {
  liquidity_impulse: "Direction of the money tide: is dollar liquidity being added or drained? Averages the 13-week change in Fed net liquidity, big-3 central-bank assets, and the 6-month trend in M2 growth — each scored against its own history.",
  risk_appetite: "How much risk markets are embracing: calm VIX, tight credit spreads and equities above trend all score high. Extremes in either direction are information.",
  crypto_cycle: "Where Bitcoin sits in its boom-bust cycle: MVRV and Mayer Multiple percentiles, sentiment, and stretch above the 200-week base. 0 = generational bottom territory, 100 = mania.",
};

window.DASH_CONTENT = { EXPLAINERS, SECTION_INTROS, GAUGE_EXPLAINERS };
