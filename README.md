# Toss Invest Python Trading Library (`quant_libs.toss_trade`)

A lightweight, robust Python library for interacting with the Toss Invest Open API. This library handles OAuth2 authentication, token caching, automatic token refresh, default brokerage account resolution, order placement (market/limit), order modifications, cancellations, and detailed order history retrieval.

## Installation

This package requires Python 3.7+ and the `requests` library.

To install dependencies:
```bash
pip install -r requirements.txt
```

## Setup & Credentials

Before initializing the client, define your API keys as environment variables:

- `TOSS_API_KEY`: Your Toss Invest Open API Client ID.
- `TOSS_SECRET_KEY`: Your Toss Invest Open API Client Secret.

### Windows (PowerShell)
```powershell
$env:TOSS_API_KEY="your_api_key"
$env:TOSS_SECRET_KEY="your_secret_key"
```

### Windows (CMD)
```cmd
set TOSS_API_KEY=your_api_key
set TOSS_SECRET_KEY=your_secret_key
```

### Linux / macOS
```bash
export TOSS_API_KEY="your_api_key"
export TOSS_SECRET_KEY="your_secret_key"
```

---

## Quick Start

### Basic Usage

You can import and use the library from the parent folder (e.g. `Dev/Finance`):

```python
from quant_libs.toss_trade import TossTrade, TossAPIError

try:
    # Initializing client (automatically fetches token and default account sequence)
    trade = TossTrade()
    print(f"Connected. Account Seq: {trade.account_seq}")

    # Submit a limit BUY order (price > 0)
    order_id = trade.buy(ticker="AAPL", quantity=10, price=150.0)
    print(f"Limit buy placed. Order ID: {order_id}")

    # Submit a market BUY order (price == 0)
    market_order_id = trade.buy(ticker="AAPL", quantity=5, price=0)
    print(f"Market buy placed. Order ID: {market_order_id}")

    # Modify the limit order (e.g., change price to $148.0)
    new_order_id = trade.modifyOrder(order_id, price=148.0)
    print(f"Order modified. New Order ID: {new_order_id}")

    # Cancel the modified order
    trade.cancelOrder(new_order_id)
    print("Order cancelled.")

except TossAPIError as e:
    print(f"API Error ({e.code}): {e.message}")
except Exception as e:
    print(f"Error: {e}")
```

---

## API Reference

### `TossTrade` Class

#### `__init__(self, account_seq=None)`
Initializes the client, sets up the connection session, and performs token resolution.
- `account_seq` (int, optional): Explicit account sequence identifier. If not provided, it will automatically query `/api/v1/accounts` and select the first available `BROKERAGE` account.

#### `buy(self, ticker, quantity, price)`
Places a buy order.
- `ticker` (str): Stock ticker (e.g. `"AAPL"` for US stocks or `"005930"` for KR stocks).
- `quantity` (int/float): Order quantity.
- `price` (int/float): Limit price. Pass `0` to execute a **Market Order**.
- **Returns**: `str` representing the server-generated `orderId`.

#### `sell(self, ticker, quantity, price)`
Places a sell order.
- `ticker` (str): Stock ticker (e.g. `"AAPL"` or `"005930"`).
- `quantity` (int/float): Order quantity.
- `price` (int/float): Limit price. Pass `0` to execute a **Market Order**.
- **Returns**: `str` representing the server-generated `orderId`.

#### `modifyOrder(self, order_id, quantity=None, price=None, order_type=None)`
Modifies an active order's price and/or quantity.
- `order_id` (str): ID of the order to modify.
- `quantity` (int, optional): New quantity (Required for KR stocks, prohibited for US stocks).
- `price` (float, optional): New price.
- `order_type` (str, optional): `"LIMIT"` or `"MARKET"`. Deduced from price if omitted.
- **Returns**: `str` representing the *new* `orderId` of the modified order.

#### `cancelOrder(self, order_id)`
Cancels an active order.
- `order_id` (str): ID of the order to cancel.
- **Returns**: `str` representing the cancelled `orderId`.

#### `getAccounts(self)`
Retrieves all brokerage accounts associated with the credentials.
- **Returns**: `list` of account dictionaries.

#### `getOrder(self, order_id)`
Fetches details of a specific order by ID.
- **Returns**: `dict` containing order details.

#### `getOrders(self, status=None, symbol=None, from_date=None, to_date=None, cursor=None, limit=20)`
Retrieves a paginated list of orders matching the filters.
- `status` (str, optional): `"OPEN"` (pending/partial) or `"CLOSED"` (filled/cancelled/rejected).
- `symbol` (str, optional): Filter by stock symbol.
- `from_date` (str, optional): KST start date (e.g., `'2026-07-01'`).
- `to_date` (str, optional): KST end date (e.g., `'2026-07-02'`).
- `cursor` (str, optional): Pagination cursor.
- `limit` (int, optional): Page size (default 20, max 100).
- **Returns**: `dict` containing `"orders"`, `"nextCursor"`, and `"hasNext"`.

---

## Error Handling

When the Toss API returns a non-2xx status code, the library raises a `TossAPIError` exception.

```python
try:
    trade.buy("AAPL", 10, 150.0)
except TossAPIError as e:
    print(f"HTTP Status: {e.status_code}")
    print(f"Error Code:  {e.code}")
    print(f"Message:     {e.message}")
    print(f"Request ID:  {e.request_id}")
    print(f"Error Data:  {e.data}")
```