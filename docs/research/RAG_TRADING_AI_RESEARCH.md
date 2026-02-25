<!-- Bond: private document, do not sync to educational repo -->
# RAG AI for Day Trading: Research Findings

Date: 2026-02-24
Source: Multi-agent research (5 parallel agents, 60+ web sources)

---

## Executive Summary

Research into whether retail/offline AI RAG systems can profitably predict
stock trades. Covers data sources, sentiment analysis, novel signals, and
honest profitability evidence. Key finding: **no verified RAG trading system
has documented sustained live profit**. The viable path is AI-assisted
research (human decides), not AI-automated trading (bot decides).

---

## Part 1: Top 20 Data Sources for a Trading RAG System

### Tier 1: Free Bulk Dumps (Index Immediately)

| # | Source | Data | Format | Size | URL |
|---|--------|------|--------|------|-----|
| 1 | SEC EDGAR Full-Text | 10-K, 10-Q, 8-K filings (1993-present) | XBRL/JSON/HTML | ~1.73 TB | sec.gov/edgar/search/ |
| 2 | FRED | 840K+ economic series (CPI, GDP, rates) | CSV/JSON API | Decades | fred.stlouisfed.org |
| 3 | Financial News Multisource (HuggingFace) | 24 news datasets (Yahoo, DJIA, NYT, Reddit) 1990-2025 | Parquet | 57.1M rows | huggingface.co/datasets/Brianferrell787/financial-news-multisource |
| 4 | Stooq Historical | 21K securities, 30+ year daily OHLCV | CSV zip | 1.4 GB | stooq.com/db/h/ |
| 5 | TroveLedger (HuggingFace) | S&P 500/FTSE/HSI minute-level OHLCV | Parquet | 40M+ rows | huggingface.co/datasets/Traders-Lab/TroveLedger |
| 6 | FINRA Short Interest | Official short positions, all US exchanges | CSV/JSON API | 8K+ equities | finra.org/finra-data/browse-catalog/equity-short-interest |
| 7 | OpenInsider | SEC Form 3/4/5 insider buys/sells (2004-present) | CSV/Web | 15+ years | openinsider.com |
| 8 | SimFin | Income/balance/cashflow, 4K+ stocks, 20yr | CSV zip | ~200 MB | simfin.com/en/fundamental-data-download/ |

### Tier 2: Free APIs (Rate-Limited, Good for Live Updates)

| # | Source | Data | Rate Limit | URL |
|---|--------|------|------------|-----|
| 9 | Finnhub | Earnings transcripts, fundamentals, insider trades, news | 60 req/min | finnhub.io |
| 10 | Alpha Vantage | News + AI sentiment scoring, earnings transcripts | 25 calls/day | alphavantage.co |
| 11 | EODHD Bulk API | 150K tickers, 70 exchanges, bulk download | Full exchange/1 call | eodhd.com |
| 12 | Polygon.io | 50K US tickers, 10yr EOD OHLCV | 5 calls/min | polygon.io |
| 13 | World Bank | Global GDP, inflation, trade for 200+ countries | Unlimited | data.worldbank.org |

### Tier 3: Paid (High-Alpha Signal Sources)

| # | Source | Data | Cost |
|---|--------|------|------|
| 14 | Databento | Level 2 order book (10-depth), nanosecond tick data | $125 free credit |
| 15 | Unusual Whales | Options flow + dark pool activity, 6M+ daily contracts | $49-299/mo |
| 16 | Quartr | Speaker-identified earnings transcripts, 14K companies | Custom pricing |
| 17 | FMP | Analyst estimates, price targets, 30K tickers bulk | $29-499/mo |
| 18 | Quiver Quantitative | WallStreetBets sentiment, 6K equities tracked | $10-75/mo |

### Tier 4: Training Sets (Kaggle / HuggingFace)

| # | Source | Data | Size |
|---|--------|------|------|
| 19 | Stock Tweets Sentiment (Kaggle) | Pre-labeled stock tweets for sentiment classification | Variable |
| 20 | Financial PhraseBank (HuggingFace) | 4,840 expert-annotated financial sentences | 2.7 MB |

### Recommended Stack (Minimal Cost)

- Layer 1 (free, weekly batch): EDGAR + SimFin + Stooq + Financial News Multisource
- Layer 2 (free APIs, daily): Finnhub (60/min) + Alpha Vantage (25/day) + FINRA
- Layer 3 ($125 one-time + ~$50/mo): Databento order book + Unusual Whales options flow
- Total startup: $0 for layers 1-2, ~$175 for layer 3

---

## Part 2: Does AI Trading Actually Make Money?

### Hard Statistics

- 70-90% of retail traders lose money overall
- 38% of retail algo traders have significant losses in year 1
- Over 90% of academically-published strategies fail when deployed live
- Backtested returns are typically 30-50% worse in live trading
- No RAG system has documented verified live trading profit

### Why Most AI Trading Systems Fail

1. **Backtesting Mirage**: 150ms execution delay costs 0.5-1 pip per trade.
   1,000 trades/year = 500-1,000 pips hidden cost. AQR found a strategy
   with Sharpe 1.2 in backtest dropped to -0.2 live.

2. **Overfitting**: Optimizing parameters for perfect historical results
   creates patterns that don't exist forward. Red flags: Sharpe >3.0,
   annualized returns in thousands of percent, profit factor >2.0.

3. **Institutional Asymmetry**: HFT firms execute in 10ms (retail: 150ms+).
   2% of firms control 73% of equity volume. Better leverage, rebates, data.

4. **Transaction Costs**: Retail pays 0.4% more slippage than institutions.
   50 monthly transactions at 0.3% slippage = 1.8% annual return reduction.
   Many strategies profitable before costs are net-loss after.

5. **Sentiment Time Lag**: LLMs provide delayed data. News is already priced
   in by the time the model processes it.

### What Actually Works (With Evidence)

| Strategy | Returns | Source |
|----------|---------|--------|
| Earnings call NLP sentiment | 355% (2021-2023 backtest) | Academic study |
| SEC 10-Q filing text analysis | Sharpe 1.5 annually | Academic study |
| Combined sentiment + technical | 50.63% over 28 months (backtest) | Academic study |
| Micro-arbitrage on prediction markets | $150K captured | CoinDesk report |
| LLM-augmented analysis | $628K from $100K (backtest) | Simulation only |

**Critical caveat**: All documented successes are backtests or very short-term.
None show sustained multi-year live outperformance.

### Realistic Retail AI Edge

| Can Do | Cannot Do |
|--------|-----------|
| Medium-frequency trades (minutes to hours) | High-frequency (microseconds) |
| Deep document analysis (10-K, earnings) | Real-time order flow arbitrage |
| Niche/small-cap research institutions skip | Dark pool front-running |
| Sentiment aggregation across free sources | Premium data feeds ($50K+/mo) |
| 5-15% annual returns with discipline | Consistent 30%+ returns |

### Bottom Line

Do NOT build a fully automated trading bot. It will lose money.

DO build an AI research assistant that:
1. Ingests SEC filings + earnings transcripts + news + sentiment
2. Surfaces anomalies humans would miss
3. Presents findings to YOU for the final trade decision
4. Tracks which signals preceded wins vs losses (feedback loop)

Realistic expectation: 1-5% annual alpha above market with discipline.

---

## Part 3: Twitter Sentiment Analysis

### Does It Work?

| Metric | Result |
|--------|--------|
| Directional prediction accuracy | 55-85% (varies by method) |
| Best predictive window | 1-10 days (not minutes) |
| Profitable after transaction costs? | Rarely (+23% before, -2.7% after) |
| Bot contamination | 71% of suspicious financial tweets |
| Famous Bollen 2011 study (86.7%) | Failed rigorous replication |
| StockTwits backtested improvement | +4% annual, +15% cumulative |

### Core Problems

1. Transaction costs destroy thin margins
2. 71% bot manipulation poisons data
3. 1-10 day lag -- institutions already trade on it faster
4. Sarcasm/irony detection still unreliable
5. The canonical proof (Bollen 2011) didn't replicate cleanly

### When Twitter Sentiment Works

- As a secondary confirmation signal, not primary
- On retail-dominated stocks (high retail ownership)
- In daily aggregation windows (20-27% correlation to 2-week returns)
- Combined with 2+ other sources (multi-source: 87% vs 60% single)

---

## Part 4: Novel Sentiment Sources Ranked by Evidence

### Tier 1: Strong Academic Evidence

| Source | Edge | Evidence | Cost |
|--------|------|----------|------|
| Glassdoor Reviews | +0.74%/mo rising ratings; Best Places +115.6% since 2009 | Georgetown study | Free (scrape) |
| Patent Filings (USPTO) | +2.2% annualized; 72.5% 1yr outperformance | O'Shaughnessy | Free (public) |
| Congressional Trading | Pelosi: +160.7% total, 81.2% win rate | Quiver Quantitative | Free API |
| Google Trends | +326% (2004-2011) "debt" keyword vs +16% buy-hold | Multiple studies | Free API |

### Tier 2: Works With Careful Implementation

| Source | Edge | Cost |
|--------|------|------|
| Satellite Imagery | Used by tier-1 hedge funds; UBS analyzed 4.8M images | $10K-$100K+/yr |
| LinkedIn Job Postings | Hiring precedes earnings revisions | Free (scrape) |
| SimilarWeb Traffic | R-squared 0.96 for revenue prediction | $500+/mo |
| Reddit Multi-Sub Sentiment | 87% accuracy with multi-source; predicted GME squeeze | Free (PRAW) |

### Tier 3: Mixed or Emerging

| Source | Status |
|--------|--------|
| YouTube Comments | One study found NO relationship to stock prices |
| App Store Reviews | Predicts app revenue, indirect stock link |
| TikTok Finfluencers | High pump-and-dump risk |
| Podcast Transcripts | Tools available, predictive power unclear |
| Discord/Telegram | 20-60 min lag behind Twitter, crypto-dominated |

### Tier 4: No Evidence

| Source | Status |
|--------|--------|
| GitHub Commit Activity | Zero published research linking to returns |
| Amazon Product Reviews | Predicts return rates, not stock price |

---

## Part 5: Multi-Source Ensemble (Where the Real Edge Lives)

### Accuracy by Approach

| Approach | Accuracy |
|----------|----------|
| Twitter alone | ~60% |
| Twitter + expanded volume (20K tweets) | 85% |
| Multi-source (Twitter + Reddit + News) | 87% |
| Sentiment + Technical + Fundamental | Best documented |

### Platform Timing Chain

```
Breaking news hits Twitter          =  0 minutes
Discord/Telegram picks it up        =  20-60 minutes
Reddit discussions develop          =  1-4 hours
Analyst reports published           =  4-24 hours
Market fully prices it in           =  1-10 days
```

Twitter for speed, Reddit for confirmation, news for context.

### Sentiment Decay Rules

- Fresh (0-2 days): Full weight, actionable signal
- Aging (3-7 days): Half weight, confirmation only
- Stale (>7 days): Zero weight, archive for backtesting
- Alpha half-life overall: 18 months (was 36 months a decade ago)

---

## Part 6: Recommended RAG Architecture

### Pipeline Design

```
LAYER 1: Free Data Ingestion (Daily Batch)
  - Glassdoor reviews (scrape quarterly)
  - USPTO patent filings (free bulk download)
  - Congressional trades (CapitolTrades/Quiver API)
  - Google Trends (free API, daily)
  - Reddit via PRAW (free, generous limits)
  - Finnhub news + sentiment (60 req/min free)

LAYER 2: Sentiment Scoring
  - FinBERT for fast classification (<100ms)
  - Local Ollama model for deep context analysis
  - VADER for Reddit slang ("moon," "tendies," rocket emoji)
  - Ensemble: weight news 40%, social 30%, filings 30%

LAYER 3: RAG Index (Ollama nomic-embed-text, 768-dim)
  - Chunk by: company + date + source type
  - Example: "AAPL [2026-02-24]: Glassdoor +0.8,
    patent filings +12% YoY, Reddit bullish 67%,
    congressional buy (Pelosi, Feb 10)"
  - Decay: weight by age (>2 days = half, >7 days = zero)

LAYER 4: Human Decision Layer
  - RAG query: "Show all bullish signals for MSFT past 7 days"
  - System surfaces ranked signals with sources
  - Human makes final trade decision
  - Track which signals preceded wins vs losses
```

### Sentiment Model Comparison

| Model | Speed | Accuracy | Context | Best For |
|-------|-------|----------|---------|----------|
| FinBERT | <100ms | F1 93.27% | 512 tokens | Fast real-time scoring |
| FinGPT | Slower | +9.68% vs FinBERT | 8K-200K tokens | Full transcripts |
| VADER | Instant | Lower | N/A | Reddit/social slang |
| GPT-4o-mini | API call | 87.79% fine-tuned | 128K | Deep nuance |

Recommendation: FinBERT for speed + local Ollama for depth. Use both.

### Key Technical Decisions

| Decision | Recommendation | Why |
|----------|---------------|-----|
| Sentiment model | FinBERT + Ollama (dual) | Speed + depth |
| Twitter access | Skip or Old Bird V2 ($180/mo) | Bot noise vs cost |
| Aggregation window | Daily close | 20-27% correlation |
| Vector DB | Ollama nomic-embed-text (768-dim) | Already in stack |
| Multi-source? | Yes, minimum 3 sources | 87% vs 60% accuracy |

---

## Part 7: Key Conclusions

### The Real Edge

The edge is NOT any single data source or model. It is combining 4-5 weak
signals that nobody else is combining in exactly your way. A local RAG
system is uniquely positioned to ingest, cross-reference, and surface
patterns across diverse sources that no single API or platform provides.

### What to Build

An AI research assistant that reads 10,000 documents per day that no
human can, then presents the 3 signals worth acting on. Human decides.

### What NOT to Build

A fully automated trading bot. 70-90% of retail traders lose money.
90% of published strategies fail live. Transaction costs eat thin margins.

### The 4 Best Novel Signals (Free, Under-Exploited)

1. Glassdoor employee reviews (+0.74%/mo, free, Georgetown-backed)
2. Patent filings (+2.2% annualized, free public data)
3. Congressional trades (Pelosi +160.7%, free API)
4. Multi-source sentiment ensemble (87% accuracy when combining 3+ sources)

### Realistic Expectation

1-5% annual alpha above market with discipline. Compounded over 10 years
on $100K, that is $16K-$63K in extra returns from a system with $0 in
API fees running locally.

---

## Sources

Over 60 sources consulted across academic papers, Reddit communities,
trading forums, and financial research. Key references:

- Bollen et al. 2011, "Twitter Mood Predicts the Stock Market" (arXiv)
- Lachanski 2017, replication study (Econ Journal Watch)
- Georgetown faculty, "Crowdsourced Employer Reviews and Stock Returns"
- O'Shaughnessy, "Mispriced Innovation" (patent analysis)
- ACL 2021, "Predicting GME Stock Price Using Reddit Sentiment"
- AI4Finance Foundation, FinGPT (GitHub)
- ProsusAI, FinBERT (HuggingFace)
- SSRN, "Financial Market Sentiment Analysis Using LLM and RAG"
- Quiver Quantitative (congressional trading data)
- Nature, "Container Ports Satellite Analysis Predicts World Stock Returns"
- FINRA, SEC EDGAR, FRED (official government data portals)
