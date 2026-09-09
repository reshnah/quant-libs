# quant_libs

A comprehensive Python quantitative trading, algorithmic research, and execution library. `quant_libs` provides unified tools for multi-asset automated trading (Toss Invest, Binance, MetaTrader 5), market data crawling, technical indicators, genetic algorithm strategy optimization, unsupervised machine learning, trade journaling, and robust file/utility helpers.

---

## Table of Contents

- [Overview](#overview)
- [Architecture & Modules](#architecture--modules)
- [Installation](#installation)
- [Configuration & Credentials](#configuration--credentials)
- [Modules & API Reference](#modules--api-reference)
  - [1. Toss Invest Trading (`quant_libs.toss_trade`)](#1-toss-invest-trading-quant_libstoss_trade)
  - [2. Binance Crypto Trading (`quant_libs.binance_api`)](#2-binance-crypto-trading-quant_libsbinance_api)
  - [3. MetaTrader 5 Forex/CFD Trading (`quant_libs.mt5_api`)](#3-metatrader-5-forexcfd-trading-quant_libsmt5_api)
  - [4. Market Data Crawling (`quant_libs.crawler`)](#4-market-data-crawling-quant_libscrawler)
  - [5. Technical Indicators & Performance Metrics (`quant_libs.indicators`)](#5-technical-indicators--performance-metrics-quant_libsindicators)
  - [6. Genetic Algorithm Optimization (`quant_libs.genetic`)](#6-genetic-algorithm-optimization-quant_libsgenetic)
  - [7. Data Science & Clustering (`quant_libs.dsci`)](#7-data-science--clustering-quant_libsdsci)
  - [8. Trade & Portfolio Journaling (`quant_libs.deposit_manager`)](#8-trade--portfolio-journaling-quant_libsdeposit_manager)
  - [9. Safe File I/O & Chart Serialization (`quant_libs.file_io`)](#9-safe-file-io--chart-serialization-quant_libsfile_io)
  - [10. Mathematical & Market Utilities (`quant_libs.utils`)](#10-mathematical--market-utilities-quant_libsutils)
  - [11. Logging & Singleton Utilities (`quant_libs.logger`, `quant_libs.singleton`)](#11-logging--singleton-utilities-quant_libslogger-quant_libssingleton)
- [License](#license)

---

## Overview

`quant_libs` is designed for quant traders, algorithmic researchers, and software engineers who manage end-to-end trading pipelines:
- **Brokers & Exchanges**: Execute orders and stream data on Toss Invest (KR/US equities), Binance (Spot, USD-M/COIN-M Futures, Options), and MetaTrader 5 (Forex & CFD).
- **Market Data**: Scrape current and survivorship-bias-free historical constituents (S&P 500, Dow Jones, Nasdaq-100, KOSPI 200), KRX rankings, company fundamentals, and historical OHLCV.
- **Analytics & Math**: Calculate verified technical indicators (RSI, MACD, Bollinger Bands, Ichimoku, VWAP) and strategy backtesting metrics (MDD, Sharpe ratio, Time-Under-Water, leverage solver).
- **Machine Learning & Genetic Algorithms**: Optimize trading rule parameters with multi-type chromosome genetic algorithms, or classify market regimes using custom-distance K-Means and K-Medoids clustering.
- **Production Hardening**: Concurrency-safe file access with process detection, daily rolling loggers, timezone/DST normalization, and real-time execution countdown timers.

---

## Architecture & Modules

```
quant_libs/
├── __init__.py          # Package root exports
├── toss_trade.py        # Toss Invest Open API client (OAuth2, equities execution)
├── binance_api.py       # Binance REST & WebSocket client (Spot, Margin, Futures, Options)
├── mt5_api.py           # MetaTrader 5 Python bridge (Forex, CFDs, spread monitoring)
├── crawler.py           # Web scrapers & financial data loaders (FDR, PyKRX, yfinance)
├── indicators.py        # Technical indicators and quant performance evaluation
├── genetic.py           # Genetic algorithm framework (Chromosome, Species)
├── dsci.py              # Clustering (K-Means, K-Medoids, K-Means++) and data distribution tools
├── deposit_manager.py   # Trade record management and auto-saved CSV portfolio journal
├── file_io.py           # Concurrency-aware file I/O (open_wait) and chart format conversion
├── utils.py             # Math helpers, DST calculations, timeframe converters, market clock
├── logger.py            # Daily rotating file and console logger
└── singleton.py         # Thread-safe in-memory singleton decorator
```

---

## Installation

### 1. Requirements

- Python 3.7+ (Python 3.8+ recommended)
- Windows OS (Required if using `MetaTrader5`; other modules are cross-platform on Windows/Linux/macOS)

### 2. Install Dependencies

Install core dependencies via `requirements.txt`:
```bash
pip install -r requirements.txt
```

To enable all features across all modules, ensure the following ecosystem packages are installed:
```bash
pip install requests numpy pandas matplotlib scipy psutil dill pykrx FinanceDataReader yfinance websocket-client
```

*Note for MetaTrader 5*: On Windows, install MetaTrader5 via:
```bash
pip install MetaTrader5
```

### 3. Install `quant_libs` as a Package

Install locally in editable mode:
```bash
pip install -e .
```

Or install directly from GitHub:
```bash
pip install git+https://github.com/reshnah/quant-libs.git
```

---

## Configuration & Credentials

### Environment Variables

Set credentials for the respective exchange APIs:

#### Toss Invest
- `TOSS_API_KEY`: Client ID issued by Toss Invest Open API.
- `TOSS_SECRET_KEY`: Client Secret issued by Toss Invest Open API.

#### Binance
- `BINANCE_API_KEY`: Binance API Key (or pass directly via constructor/key file).
- `BINANCE_SECRET_KEY`: Binance API Secret.

#### Windows (PowerShell)
```powershell
$env:TOSS_API_KEY="your_toss_api_key"
$env:TOSS_SECRET_KEY="your_toss_secret_key"
$env:BINANCE_API_KEY="your_binance_api_key"
$env:BINANCE_SECRET_KEY="your_binance_secret_key"
```

#### Windows (CMD)
```cmd
set TOSS_API_KEY=your_toss_api_key
set TOSS_SECRET_KEY=your_toss_secret_key
set BINANCE_API_KEY=your_binance_api_key
set BINANCE_SECRET_KEY=your_binance_secret_key
```

#### Linux / macOS
```bash
export TOSS_API_KEY="your_toss_api_key"
export TOSS_SECRET_KEY="your_toss_secret_key"
export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_SECRET_KEY="your_binance_secret_key"
```

---

## Modules & API Reference

---

### 1. Toss Invest Trading (`quant_libs.toss_trade`)

A production-ready client for the Toss Invest Open API supporting Korean and US stock trading, OAuth2 token caching/refresh, order modification/cancellation, and paginated order history.

#### Key Classes

- `TossTrade(account_seq=None)`: Main trading interface.
  - Automatically fetches an OAuth2 access token and resolves the primary `BROKERAGE` account sequence if `account_seq` is omitted.
- `TossAPIError`: Custom exception containing `code`, `message`, `request_id`, `data`, and `status_code`.

#### Core Methods

| Method | Description |
|---|---|
| `buy(ticker, quantity, price)` | Submits a buy order. Pass `price=0` for Market order; `price > 0` for Limit order. |
| `sell(ticker, quantity, price)` | Submits a sell order. Pass `price=0` for Market order; `price > 0` for Limit order. |
| `modifyOrder(order_id, quantity=None, price=None, order_type=None)` | Modifies price and/or quantity of an open order. Returns new `order_id`. |
| `cancelOrder(order_id)` | Cancels an open order by ID. |
| `getOrder(order_id)` | Retrieves detailed status for a specific order. |
| `getOrders(status=None, symbol=None, from_date=None, to_date=None, cursor=None, limit=20)` | Queries order history with pagination (`"OPEN"` or `"CLOSED"`). |
| `getAccounts()` | Returns all brokerage accounts associated with the credentials. |
| `setLogLevel(level)` | Adjusts internal logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

#### Example

```python
from quant_libs.toss_trade import TossTrade, TossAPIError

try:
    trade = TossTrade()
    print(f"Connected to Toss account sequence: {trade.account_seq}")

    # Limit buy: 10 shares of Apple at $150
    order_id = trade.buy(ticker="AAPL", quantity=10, price=150.0)
    print(f"Limit buy order placed: {order_id}")

    # Modify limit price
    new_order_id = trade.modifyOrder(order_id=order_id, price=148.5)

    # Cancel order
    trade.cancelOrder(new_order_id)
    print("Order cancelled successfully.")

except TossAPIError as e:
    print(f"Toss API error [{e.code}]: {e.message} (Status: {e.status_code})")
```

---

### 2. Binance Crypto Trading (`quant_libs.binance_api`)

Comprehensive client supporting Binance Spot, Margin, USD-M Futures (`USDM`), COIN-M Futures (`COINM`), and Options (`OPTION`), with real and testnet environments.

#### Key Features

- **Multi-market Support**: `SPOT`, `USDM` (Futures), `COINM` (Delivery/Futures), and `OPTION`.
- **Environments**: Real (`"REAL"`), Binance Testnet (`"DEMO"`), and paper trading mode (`"FAKE"`).
- **Execution & Precision**: Automatically fetches exchange rules (lot sizes, tick sizes, min notional) and handles precision rounding (`priceRound`, `qtyRound`, `qtyRoundUp`, `qtyRoundDown`).
- **Advanced Order Routing**: Market, Limit, PriceMatch (`"QUEUE"`, `"OPPONENT"`), Chase maker orders (`BuyChase`, `SellChase`), and stop-loss triggers.
- **WebSocket Streaming**: Multi-symbol real-time price updates for USD-M futures.

#### Core Methods

| Category | Method | Description |
|---|---|---|
| **Market Data** | `getChart(symbol, interval, start_t, end_t)` | Retrieves OHLCV candlestick data. |
| | `getLongChart(symbol, interval, start_t, min_length)` | Fetches long historical candle series across pagination limits. |
| | `getBook(symbol)` | Retrieves current order book depth. |
| | `getLastPrice(symbol)` | Returns the cached/latest price of a symbol. |
| **Order Placement** | `Buy(symbol, quantity, price, leverage=0, reduce_only=False)` | Places a buy order (Limit if `price > 0`, Market if `price=0`). |
| | `Sell(symbol, quantity, price, leverage=0, reduce_only=False)` | Places a sell order. |
| | `BuyChase(symbol, quantity, ...)` | Places a limit buy at current best bid and chases the market until filled. |
| | `SellChase(symbol, quantity, ...)` | Places a limit sell at current best ask and chases the market until filled. |
| | `OrderModify(side, symbol, orderId, quantity, price, ...)` | Modifies an existing open order. |
| | `OrderCancel(symbol, orderId)` | Cancels an order. |
| | `OrderWait(symbol, orderId)` | Blocks until an order is completely filled or cancelled. |
| **Margin & Futures** | `USDMChangeLeverage(symbol, leverage)` | Sets futures position leverage. |
| | `USDMChangeMarginType(symbol, marginType)` | Sets margin type (`"ISOLATED"` or `"CROSSED"`). |
| | `USDMChangePositionMode(dualSide)` | Switches between One-Way and Hedge mode. |
| | `BuyMargin(...)` / `SellMargin(...)` | Executes cross/isolated margin orders. |
| **Account & Balances** | `SpotAccount()` / `USDMAccount()` | Fetches full account state for Spot or Futures. |
| | `getSpotBalanceQuantity(symbol)` | Returns free spot balance for a coin (e.g. `"USDT"`). |
| | `getUSDMMarginBalance()` | Returns total futures margin balance (including unrealized PnL). |
| | `getUSDMWalletBalance()` | Returns total futures wallet balance before position entry. |
| | `getUsdmAvailableBalance()` | Returns capital available for opening new futures positions. |

#### Example

```python
from quant_libs.binance_api import Binance

# Initialize USD-M Futures on Testnet
client = Binance(exchange="USDM", test="DEMO")

symbol = "BTCUSDT"
client.USDMChangeLeverage(symbol, leverage=10)

# Submit limit buy order
order = client.Buy(symbol=symbol, quantity=0.01, price=60000.0)
print(f"Order ID: {order['orderId']}")

# Wait for execution or cancel
filled, order_info = client.OrderWait(symbol, order["orderId"])
if filled:
    print(f"Executed at price: {order_info.get('executedPrice')}")
```

---

### 3. MetaTrader 5 Forex/CFD Trading (`quant_libs.mt5_api`)

Direct Python bridge to MetaTrader 5 for institutional Forex and CFD trading. Provides spread filtering, automatic timezone/daylight saving adjustment, position tracking, and execution with Take Profit and Stop Loss.

#### Core Methods

| Method | Description |
|---|---|
| `MT5(login=None, server=None, password=None)` | Initializes the MT5 terminal session (or attaches to active terminal). |
| `buy(symbol, qty, price, take_profit=None, stop_loss=None)` | Sends Buy order (Market if `price=0`, Limit if `price > 0`). |
| `sell(symbol, qty, price, take_profit=None, stop_loss=None)` | Sends Sell order. |
| `getPositions(symbol=None, order_id=None)` | Returns open positions with directional volume. |
| `getSpread(pair)` / `getUsualSpread(pair, usuality=0.99)` | Computes current and 99th percentile historical spread. |
| `isSpreadNormalized(symbol)` / `waitSpreadNormalization(symbol)` | Detects abnormal spread expansion (news spikes/rollover) and waits for normalization. |
| `isMarketOpen()` | Checks whether the global Forex market is currently open. |
| `getChart(symbol, interval, start_t, end_t, ...)` | Fetches OHLC bars with spread adjustment and timezone offset. |
| `getTickChart(symbol, length)` | Retrieves raw bid/ask tick data. |

#### Example

```python
from quant_libs.mt5_api import MT5

client = MT5()

# Wait for spread to normalize after session open
client.waitSpreadNormalization("EURUSD", timeout=60)

# Execute 0.1 lot market buy with Stop Loss and Take Profit
ticket, price = client.buy(
    symbol="EURUSD",
    qty=0.1,
    price=0,
    stop_loss=1.0750,
    take_profit=1.0900,
    comment="Quant Strategy"
)
print(f"Position opened. Ticket: {ticket}, Fill Price: {price}")
```

---

### 4. Market Data Crawling (`quant_libs.crawler`)

Data scraping and historical loading utilities covering Korean (KRX) and US equity markets.

#### Key Functions

- **Index Constituents**:
  - `getUsTickers(listed_idx=["DJ", "NQ100", "SP500"])`: Fetches live constituents of Dow Jones, Nasdaq 100, and S&P 500 from Wikipedia.
  - `getKospi200Tickers()`: Fetches KOSPI 200 constituents from Wikipedia.
  - `getSnp500Tickers(tick: datetime.datetime)`: Returns **point-in-time historical S&P 500 constituents** for any given date to prevent survivorship bias in backtesting.
- **Korean Market Analytics (`pykrx`)**:
  - `getEtfList()` / `getKrxEtfName(code)`: Lists all active Korean ETFs and names.
  - `getKrxTopCapList(num, date=None)`: Top $N$ stocks by market capitalization.
  - `getKrxTopForeignRatioList(num, date=None)`: Top $N$ stocks by foreign ownership ratio.
  - `getKrxTopVolumeList(num, date=None)`: Top $N$ stocks by daily trading value.
- **Historical Data Downloads**:
  - `getChart(ticker, from_date, to_date=None)`: Fetches OHLCV chart data using `FinanceDataReader` with automatic retry and ticker normalization.
  - `exportCharts(dst_dir, tickers, from_date, to_date, ...)`: Batch-exports CSV chart datasets with caching and modification timestamp checking.
  - `getUsHistoricalEpsBvps(ticker_symbol, freq="quarterly")`: Fetches historical quarterly or annual Diluted EPS and calculates Book Value per Share (BVPS) via `yfinance`.

#### Example

```python
import datetime
from quant_libs.crawler import getSnp500Tickers, exportCharts

# Survivorship-bias-free S&P 500 universe as of January 1, 2020
historical_sp500 = getSnp500Tickers(datetime.datetime(2020, 1, 1))
print(f"S&P 500 count in 2020: {len(historical_sp500)}")

# Batch export charts
exportCharts(
    dst_dir="data/charts/",
    tickers=["AAPL", "MSFT", "NVDA"],
    from_date="2022-01-01"
)
```

---

### 5. Technical Indicators & Performance Metrics (`quant_libs.indicators`)

Pure Python, high-performance implementations of essential trading indicators and portfolio evaluation statistics.

#### Technical Indicators

Indicators accept standard chart dictionaries (`{"o": [], "h": [], "l": [], "c": [], "v": []}`) and can return lists, tuples, or dictionaries (controlled via `IndicatorSetting().return_dict = True`):

| Function | Default Parameters | Returns |
|---|---|---|
| `rsi(chart, params=[14])` | Period: 14 | RSI array (0-100) |
| `stochastic(chart, params=[12, 26, 9])` | %K: 12, %D: 26, Smooth: 9 | `(%K, %D)` |
| `stochasticRsi(chart, params=[14])` | Period: 14 | StochRSI array (0-100) |
| `macd(chart, params=[12, 26, 9])` | Fast: 12, Slow: 26, Signal: 9 | `(MACD, Signal, Histogram)` |
| `bollingerBand(chart, params=[14, 2])` | Period: 14, Multiplier: 2 | `(Upper, Lower, %b)` |
| `atr(chart, params=[14])` | Period: 14 | Average True Range |
| `adx(chart, params=[14])` | Period: 14 | `(ADX, +DI, -DI)` |
| `cci(chart, params=[9])` | Period: 9 | Commodity Channel Index |
| `williamsPR(chart, params=[14])` | Period: 14 | Williams %R (-100 to 0) |
| `ultimateOsc(chart, params=[14, 21, 28])` | Short: 14, Med: 21, Long: 28 | Ultimate Oscillator |
| `awesomeOsc(chart, params=[5, 34])` | Fast: 5, Slow: 34 | Awesome Oscillator (AO) |
| `bullBearPower(chart, params=[7])` | Period: 7 | `(Bulls, Bears)` |
| `ichimokuCloud(chart, params=[9, 26, 52, 26])` | Conversion: 9, Base: 26, Span: 52, Lag: 26 | `(Span A, Span B)` or `{"spanA", "spanB", "base", "conv"}` |
| `moneyFlowIndex(chart, params=[14])` | Period: 14 | Money Flow Index (0-100) |
| `obvOscillator(chart, params=[20])` | Period: 20 | On-Balance Volume Oscillator |
| `ema(closes, period)` | Period: $N$ | Exponential Moving Average |
| `vwap(chart)` | Intraday | Volume Weighted Average Price with daily reset |

#### Performance & Quantitative Metrics

| Function | Description |
|---|---|
| `getMdd(profits, leverage=1.0, geometric=True)` | Computes Maximum Drawdown (MDD) for arithmetic or geometric compounding. |
| `getMaxTuw(profits, leverage=1.0, geometric=True)` | Computes Maximum Time Under Water (longest recovery duration in bars/trades). |
| `getSharpe(profits, ticks, trange, tunit)` | Computes periodic Sharpe Ratio binned by time unit (`tunit`). |
| `getCProfit(profits, leverage=1.0, geometric=True)` | Generates cumulative equity curve. |
| `getPeriodicProfit(...)` / `getPeriodicNumSum(...)` | Evaluates returns and trade count distribution sliced across time intervals. |
| `getPeriodicBNB(...)` | Breaks down trades into bull (winning), bear (losing), and neutral counts. |
| `findLeverage(profits, target_profit, leverage_range=(1, 1000))` | Solves the exact leverage multiplier needed to achieve a target return using binary search. |

#### Example

```python
from quant_libs.file_io import importCsvChartDict
from quant_libs.indicators import rsi, macd, getMdd, getCProfit

chart = importCsvChartDict("data/charts/AAPL.csv")

# Compute technical indicators
rsi_series = rsi(chart, params=[14])
macd_line, macd_signal, macd_hist = macd(chart, params=[12, 26, 9])

# Strategy evaluation
trade_returns = [0.02, -0.01, 0.035, -0.02, 0.015]  # 2%, -1%, 3.5% ...
mdd = getMdd(trade_returns, leverage=1.0, geometric=True)
equity_curve = getCProfit(trade_returns, leverage=1.0, geometric=True)

print(f"Max Drawdown: {mdd * 100:.2f}% | Final Equity: {equity_curve[-1]:.4f}x")
```

---

### 6. Genetic Algorithm Optimization (`quant_libs.genetic`)

A modular framework designed for calibrating trading strategy parameters using genetic search.

#### Key Classes

- `Chromosome(tag, chromosome_group, domains, ranges, eval_func)`: Represents an individual parameter vector.
  - **Supported Gene Types**:
    - `Chromosome.INT` (`"I"`): Integer parameters.
    - `Chromosome.FLOAT` (`"F"`): Continuous floating-point parameters.
    - `Chromosome.LABEL` (`"L"`): Categorical categorical integer choices.
    - `Chromosome.BOOL` (`"B"`): Boolean flags (`True`/`False`).
    - `Chromosome.TRISTATE` (`"T"`): Directional switch (`-1`, `0`, `1`).
  - **Mutability**: `MUTANTABLE` (`"M"`) or `CONSTANT` (`"C"`).
  - **Methods**: `randomize()`, `genMutant()`, `mutate()`, `evaluate(*args)`.
- `Species`: An organism containing multiple chromosome groups.
  - Supports uniform multi-parent crossover (`Species.crossover(child, parents)`), group-targeted mutation, and string serialization.

#### Example

```python
from quant_libs.genetic import Species, Chromosome

def my_eval(genes):
    # Example objective: maximize -( (x-5)^2 + (y-10)^2 )
    x, y = genes[0], genes[1]
    return -((x - 5.0)**2 + (y - 10.0)**2)

# Create a species with 2 float genes in range [0, 20]
sp = Species()
sp.addChromosome(
    tag="Optimizer",
    chromosome_group="core",
    domains=[Chromosome.FLOAT + Chromosome.MUTANTABLE] * 2,
    ranges=[[0.0, 20.0], [0.0, 20.0]],
    eval_func=my_eval
)

sp.randomize()
score = sp.evaluate("core")[0]
print(f"Initial score: {score} with genes: {sp.getChromosome(0).genes}")
```

---

### 7. Data Science & Clustering (`quant_libs.dsci`)

Unsupervised clustering algorithms and distribution analysis tools tailored for quantitative regime identification.

#### Key Classes & Functions

- `Kmeans`: Standard K-Means clustering with customizable distance metrics, distance median/maxima tracking, confidence scoring (`getLabelAndConfidence`), and model persistence (`exportKMeans`, `importKMeans`).
- `Kmedoids`: Partitioning Around Medoids (PAM) clustering. Uses actual data points as exemplars, making it highly robust against market outliers.
- `kMeansPp(data_input, num_cluster, distance_func)`: K-Means++ centroid initialization algorithm.
- `testDistribution(data, interval, title, ...)`: Plots a frequency polygon histogram with annotated overall mean and 50%, 80%, 90% trimmed means.
- `linearRegression1d(ys)`: Computes 1-dimensional slope and intercept for trend estimation.

#### Example

```python
from quant_libs.dsci import Kmeans

def euclidean_dist(a, b):
    return sum((x - y)**2 for x, y in zip(a, b))**0.5

features = [
    [0.12, 0.05], [0.15, 0.04], [0.10, 0.06],  # Low-vol cluster
    [0.85, 0.70], [0.90, 0.75], [0.80, 0.68]   # High-vol cluster
]

km = Kmeans()
labels = km.kMeans(features, num_cluster=2, distance_func=euclidean_dist, iteration=15)
label, confidence = km.getLabelAndConfidence([0.13, 0.048])

print(f"Assigned Cluster: {label} (Confidence: {confidence:.2%})")
```

---

### 8. Trade & Portfolio Journaling (`quant_libs.deposit_manager`)

Persistent journal for live execution tracking, active position monitoring, stop-loss / take-profit triggers, and PnL logging.

#### Key Classes

- `TradeRecord`: Dataclass capturing:
  - `ticker`, `direction` (1 for Buy/Long, -1 for Sell/Short), `quantity`.
  - `entry_price`, `entry_date`, `close_price`, `close_date`, `stoploss_price`.
  - `executed` (bool), `closed` (bool), `order_id`.
  - `getPnl(current_price)`: Calculates realized or unrealized percentage return.
  - `needToClose(cur_price)`: Evaluates time-based exit (`close_date`) or price stop-loss / take-profit conditions.
- `TradeRecords(fname=None)`: Container managing active and closed records.
  - `auto_backup`: Automatically persists state to CSV on every change.
  - `newRecord(...)`, `markExecuted(...)`, `close(...)`.
  - Filter queries: `getWaiting()`, `getHolding()`, `getClosed()`, `getExpired()`.

#### Example

```python
from quant_libs.deposit_manager import TradeRecords

# Auto-backing up to trade_history.csv
journal = TradeRecords(fname="trade_history.csv")

# Record a new pending limit order
journal.newRecord(
    ticker="AAPL",
    quantity=10,
    direction=1,
    entry_price=150.0,
    order_id="ORD_1001"
)

# Mark as executed once filled
journal.markExecuted(order_id="ORD_1001", entry_price=150.0)

# Query open positions
open_positions = journal.getHolding()
print(f"Holding {len(open_positions)} active position(s).")
```

---

### 9. Safe File I/O & Chart Serialization (`quant_libs.file_io`)

Utilities for safe file operations in concurrent environments and OHLCV data conversions.

#### Key Functions

- `open_wait(filename, mode)`: Context manager that safely opens files. If a `PermissionError` occurs (e.g. another process or Excel is locking the file), it detects the locking process name and PID via `psutil`, warns the user, and retries until unlocked.
- `importCsvChartDict(csv_path)`: Reads CSV files into standard OHLCV dictionary format:
  `{"t": [datetime, ...], "o": [...], "h": [...], "l": [...], "c": [...], "v": [...], "ac": [...]}`.
- `importReversedCsvChartDict(csv_path)`: Imports price data inverted as $1 / \text{price}$ (useful for currency pair analysis or synthetic short assets).
- `exportCsvChart(chart, csv_path)`: Exports an OHLCV dict into standardized CSV format.
- `appendChartToDf(dst, chart, symbol, how="inner")`: Converts chart dict to a pandas DataFrame with symbol-prefixed columns and merges on timestamp `"t"`.
- `getFileUpdateDatetime(fname)`: Returns the last modification timestamp as a `datetime` object.

#### Example

```python
from quant_libs.file_io import open_wait, importCsvChartDict, exportCsvChart

# Safe file opening under concurrent scripts
with open_wait("shared_signals.txt", "a") as f:
    f.write("BUY AAPL\n")

# Load and serialize chart data
chart = importCsvChartDict("data/AAPL.csv")
exportCsvChart(chart, "data/AAPL_backup.csv")
```

---

### 10. Mathematical & Market Utilities (`quant_libs.utils`)

Math, statistical, and time utilities built specifically for algorithmic trading systems.

#### Key Functions

- **Statistical & Math Functions**:
  - `avg(l)` / `stdev(l)`: Mean and sample standard deviation.
  - `min_n(data_list, n)`: Finds the $N$-th smallest unique element in $O(N)$ single-pass time.
  - `interquartile(l)`: Computes $[Q_1, Q_2, Q_3]$ quartiles.
  - `wAvg(l, ws)` / `wStdev(l, ws)`: Weighted average and weighted standard deviation.
  - `positiveRatio(l)`: Calculates win rate / percentage of positive values.
  - `sign(n)` / `softThreshold(x, a)` / `sigmoid(x, a)` / `entropy(a, b)`.
  - `addElementSorted(...)`: Maintains sorted parallel lists.
- **Market Time & DST Helpers**:
  - `getDst(region, tick)`: Accurately checks Daylight Saving Time status for `"US"`, `"EU"`, `"AU"`, and `"NZ"`.
  - `isKrHoliday(dt)`: Returns `True` if the date falls on a known Korean stock market holiday.
  - `trimDictChart(chart, from_date, to_date)`: Trims an OHLCV dict to a specified date window.
  - `convResDictChart_30mto1h(chart_30m, phase=0)`: Resamples 30-minute bar dictionaries into 1-hour candles.
  - `getNextMonthFirstDate(dt)`: Advances date to the 1st of the next month.
  - `waitForHms(h, m, s)` / `waitSeconds(s)`: Real-time blocking sleep with dynamic console countdown for synchronized market openings.

#### Example

```python
import datetime
from quant_libs.utils import getDst, isKrHoliday, waitForHms

# Check market conditions
now = datetime.datetime.now()
print(f"Is US DST active? {getDst('US', now)}")
print(f"Is today a Korean holiday? {isKrHoliday(now)}")

# Synchronize bot execution for 09:00:00 KST market open
# waitForHms(9, 0, 0)
```

---

### 11. Logging & Singleton Utilities (`quant_libs.logger`, `quant_libs.singleton`)

Lightweight infrastructure for production trading daemons.

#### Key Functions

- `@singleton`: Decorator ensuring only a single instance of a configuration class exists across the application runtime.
- `LoggerSetting`: Singleton class holding global `log_path` and `log_level`.
- `stdLog(s)`: Prints timestamped string `[HH:MM:SS] ...` to console and appends to daily log file `log<YYMMDD>.txt`.
- `strNow()`, `strToday(length=6)`, `datetimeToday()`: Formatted timestamp helpers.

#### Example

```python
from quant_libs.logger import stdLog, LoggerSetting

LoggerSetting().log_path = "logs/"
stdLog("Strategy initialized successfully.")
# Output: [12:30:05] Strategy initialized successfully.
# Appended to: logs/log260909.txt
```

---

## License

This project is licensed under the MIT License. See [setup.py](file:///C:/Users/reshn/OneDrive/문서/Dev/Finance/quant_libs/setup.py) for package distribution details.