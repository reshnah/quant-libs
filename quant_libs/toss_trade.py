import os
import time
import datetime
import requests

class TossAPIError(Exception):
    """
    Custom exception raised for errors returned by the Toss Invest Open API.
    """
    def __init__(self, code, message, request_id=None, data=None, status_code=None):
        self.code = code
        self.message = message
        self.request_id = request_id
        self.data = data
        self.status_code = status_code
        super().__init__(f"TossAPIError (Status {status_code}, Code: {code}): {message} (Request ID: {request_id})")

    @classmethod
    def from_response(cls, response):
        """
        Creates a TossAPIError from an HTTP response.
        """
        status_code = response.status_code
        try:
            err_data = response.json()
            if isinstance(err_data, dict) and "error" in err_data:
                err = err_data["error"]
                return cls(
                    code=err.get("code", "unknown_error"),
                    message=err.get("message", ""),
                    request_id=err.get("requestId", response.headers.get("X-Request-Id")),
                    data=err.get("data"),
                    status_code=status_code
                )
            elif isinstance(err_data, dict) and "error" in err_data and isinstance(err_data["error"], str):
                # Handle OAuth2 error standard format: {"error": "...", "error_description": "..."}
                return cls(
                    code=err_data.get("error", "oauth_error"),
                    message=err_data.get("error_description", ""),
                    request_id=response.headers.get("X-Request-Id"),
                    data=None,
                    status_code=status_code
                )
        except ValueError:
            pass

        # Fallback to standard requests exception representation
        return cls(
            code="http_error",
            message=response.text or "HTTP request failed",
            request_id=response.headers.get("X-Request-Id"),
            data=None,
            status_code=status_code
        )


class TossTrade:
    """
    Trading system client for Toss Invest Open API.
    """
    def __init__(self, account_seq=None):
        # Read keys from environment variables
        self.api_key = os.environ.get("TOSS_API_KEY")
        self.secret_key = os.environ.get("TOSS_SECRET_KEY")

        if not self.api_key or not self.secret_key:
            raise ValueError(
                "Authorization keys must be defined in environment variables: "
                "TOSS_API_KEY and TOSS_SECRET_KEY."
            )

        self.base_url = "https://openapi.tossinvest.com"
        self.session = requests.Session()

        # Token caching state
        self._access_token = None
        self._token_expiry = 0

        self.account_seq = account_seq

        # If account_seq is not provided, fetch the default brokerage account
        if self.account_seq is None:
            self.resolve_default_account()

    def _get_token(self):
        """
        Retrieves a valid OAuth2 access token, executing the token client credentials
        flow if necessary or if the token is close to expiring (within 60 seconds).
        """
        now = time.time()
        # If token is still valid (with 60 seconds buffer), reuse it
        if self._access_token and now < self._token_expiry - 60:
            return self._access_token

        url = f"{self.base_url}/oauth2/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        data = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.secret_key
        }

        response = self.session.post(url, headers=headers, data=data)
        if response.status_code != 200:
            raise TossAPIError.from_response(response)

        res_json = response.json()
        self._access_token = res_json["access_token"]
        self._token_expiry = now + int(res_json["expires_in"])
        return self._access_token

    def _get_headers(self):
        """
        Builds the request headers, automatically ensuring the token is valid.
        """
        token = self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

    def _request(self, method, path, headers=None, params=None, json=None):
        """
        Helper method to make HTTP requests with automatic header injection and error handling.
        """
        url = f"{self.base_url}{path}"
        req_headers = self._get_headers()
        if headers:
            req_headers.update(headers)

        response = self.session.request(method, url, headers=req_headers, params=params, json=json)

        if not (200 <= response.status_code < 300):
            raise TossAPIError.from_response(response)

        return response.json()

    def resolve_default_account(self):
        """
        Fetches the user's accounts list and selects the first active brokerage account
        to use as the default account sequence.
        """
        accounts = self.getAccounts()
        if not accounts:
            raise ValueError("No Toss brokerage accounts found for this user context.")
        self.account_seq = accounts[0]["accountSeq"]

    def getAccounts(self):
        """
        Retrieves the list of accounts associated with the user.
        
        Returns:
            list: List of accounts containing accountNo, accountSeq, accountType.
        """
        response = self._request("GET", "/api/v1/accounts")
        return response.get("result", [])

    def buy(self, ticker, quantity, price):
        """
        Submits a buy order.
        If price is 0, a market order is submitted. Otherwise, a limit order is submitted.

        Args:
            ticker (str): The symbol of the stock (e.g., "AAPL" or "005930").
            quantity (float/int): The quantity to buy.
            price (float/int): The purchase price limit. 0 for market order.

        Returns:
            str: The generated order ID.
        """
        order_type = "MARKET" if price == 0 else "LIMIT"
        payload = {
            "symbol": ticker,
            "side": "BUY",
            "orderType": order_type,
            "quantity": quantity
        }
        if order_type == "LIMIT":
            payload["price"] = price

        headers = {
            "X-Tossinvest-Account": str(self.account_seq),
            "Content-Type": "application/json"
        }
        response = self._request("POST", "/api/v1/orders", headers=headers, json=payload)
        return response["result"]["orderId"]

    def sell(self, ticker, quantity, price):
        """
        Submits a sell order.
        If price is 0, a market order is submitted. Otherwise, a limit order is submitted.

        Args:
            ticker (str): The symbol of the stock (e.g., "AAPL" or "005930").
            quantity (float/int): The quantity to sell.
            price (float/int): The sale price limit. 0 for market order.

        Returns:
            str: The generated order ID.
        """
        order_type = "MARKET" if price == 0 else "LIMIT"
        payload = {
            "symbol": ticker,
            "side": "SELL",
            "orderType": order_type,
            "quantity": quantity
        }
        if order_type == "LIMIT":
            payload["price"] = price

        headers = {
            "X-Tossinvest-Account": str(self.account_seq),
            "Content-Type": "application/json"
        }
        response = self._request("POST", "/api/v1/orders", headers=headers, json=payload)
        return response["result"]["orderId"]

    def modifyOrder(self, order_id, quantity=None, price=None, order_type=None):
        """
        Modifies an existing order's quantity or price.

        Args:
            order_id (str): The ID of the order to modify.
            quantity (float/int, optional): The new quantity. Required for KR, Prohibited for US.
            price (float/int, optional): The new price limit. Required if LIMIT.
            order_type (str, optional): "LIMIT" or "MARKET". Deduced from price if omitted.

        Returns:
            str: The new generated order ID.
        """
        payload = {}
        if order_type is not None:
            payload["orderType"] = order_type
        elif price is not None:
            payload["orderType"] = "LIMIT" if price > 0 else "MARKET"

        if quantity is not None:
            payload["quantity"] = quantity

        if price is not None and price > 0:
            payload["price"] = price

        headers = {
            "X-Tossinvest-Account": str(self.account_seq),
            "Content-Type": "application/json"
        }
        path = f"/api/v1/orders/{order_id}/modify"
        response = self._request("POST", path, headers=headers, json=payload)
        return response["result"]["orderId"]

    def cancelOrder(self, order_id):
        """
        Cancels an existing order.

        Args:
            order_id (str): The ID of the order to cancel.

        Returns:
            str: The order ID of the cancelled order.
        """
        headers = {
            "X-Tossinvest-Account": str(self.account_seq),
            "Content-Type": "application/json"
        }
        path = f"/api/v1/orders/{order_id}/cancel"
        response = self._request("POST", path, headers=headers, json={})
        return response["result"]["orderId"]

    def getOrder(self, order_id):
        """
        Retrieves detailed information of a specific order.

        Args:
            order_id (str): The ID of the order.

        Returns:
            dict: The detailed order information.
        """
        headers = {
            "X-Tossinvest-Account": str(self.account_seq)
        }
        path = f"/api/v1/orders/{order_id}"
        response = self._request("GET", path, headers=headers)
        return response.get("result", {})

    def getOrders(self, status=None, symbol=None, from_date=None, to_date=None, cursor=None, limit=20):
        """
        Retrieves list of orders filtered by status, symbol, and dates.

        Args:
            status (str, optional): Filter by order group status ('OPEN' or 'CLOSED').
            symbol (str, optional): Filter by stock symbol.
            from_date (str, optional): Filter by start date (KST, e.g., '2026-07-01').
            to_date (str, optional): Filter by end date (KST, e.g., '2026-07-02').
            cursor (str, optional): Pagination cursor.
            limit (int, optional): Page size (default 20, max 100).

        Returns:
            dict: Dictionary with 'orders' list, 'nextCursor' string, and 'hasNext' boolean.
        """
        headers = {
            "X-Tossinvest-Account": str(self.account_seq)
        }
        params = {}
        if status is not None:
            params["status"] = status
        if symbol is not None:
            params["symbol"] = symbol
        if from_date is not None:
            params["from"] = from_date
        if to_date is not None:
            params["to"] = to_date
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = limit

        response = self._request("GET", "/api/v1/orders", headers=headers, params=params)
        return response.get("result", {})

    def getPrice(self, ticker):
        """
        Fetches the mid-price between the nearest bid and nearest ask.
        """
        book = self.getBook(ticker)
        if not book["bids_p"] or not book["asks_p"]:
            raise ValueError(f"Cannot calculate mid-price; orderbook for {ticker} is empty.")
        return (book["bids_p"][0] + book["asks_p"][0]) / 2.0

    def getBook(self, ticker):
        """
        Retrieves the orderbook for a stock.
        
        Args:
            ticker (str): Stock ticker.

        Returns:
            dict: Dict of bids/asks prices and quantities, sorted by nearest to farthest.
        """
        response = self._request("GET", "/api/v1/orderbook", params={"symbol": ticker})
        result = response.get("result", {})
        bids = result.get("bids", [])
        asks = result.get("asks", [])

        # In Toss API:
        # bids is sorted highest price to lowest price (highest is nearest)
        # asks is sorted lowest price to highest price (lowest is nearest)
        return {
            "bids_p": [float(b["price"]) for b in bids],
            "bids_n": [float(b["volume"]) for b in bids],
            "asks_p": [float(a["price"]) for a in asks],
            "asks_n": [float(a["volume"]) for a in asks]
        }

    def getChart(self, ticker, timeframe, to_date=None, adjusted=False):
        """
        Retrieves historical candle chart data for a stock.

        Args:
            ticker (str): Stock ticker.
            timeframe (str): "1m" or "1d".
            to_date (datetime.datetime or str, optional): Fetch candles before this date.
            adjusted (bool, optional): Whether to apply split/dividend adjustment.

        Returns:
            dict: OHLCVT lists sorted in ascending order of time.
        """
        params = {
            "symbol": ticker,
            "interval": timeframe,
            "adjusted": "true" if adjusted else "false",
            "count": 200  # Default to max count to return maximum available history
        }
        if to_date is not None:
            if hasattr(to_date, "isoformat"):
                params["before"] = to_date.isoformat()
            else:
                params["before"] = str(to_date)

        response = self._request("GET", "/api/v1/candles", params=params)
        result = response.get("result", {})
        candles = result.get("candles", [])

        parsed_candles = []
        for c in candles:
            ts_str = c["timestamp"]
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            dt = datetime.datetime.fromisoformat(ts_str)
            parsed_candles.append({
                "t": dt,
                "o": float(c["openPrice"]),
                "h": float(c["highPrice"]),
                "l": float(c["lowPrice"]),
                "c": float(c["closePrice"]),
                "v": float(c["volume"])
            })

        # Ensure sorting in ascending order of time
        parsed_candles.sort(key=lambda x: x["t"])

        return {
            "o": [x["o"] for x in parsed_candles],
            "h": [x["h"] for x in parsed_candles],
            "l": [x["l"] for x in parsed_candles],
            "c": [x["c"] for x in parsed_candles],
            "v": [x["v"] for x in parsed_candles],
            "t": [x["t"] for x in parsed_candles]
        }

    def getLongChart(self, ticker, timeframe, from_date, adjusted=False):
        """
        Retrieves a long historical chart by repeatedly calling getChart() and merging
        results, fetching backwards in time until from_date is reached.

        Each getChart() call returns up to 200 candles ending at (and including) to_date.
        The earliest candle's timestamp is used as the next to_date so batches are
        stitched together without gaps or duplicates.

        Args:
            ticker (str): Stock ticker.
            timeframe (str): "1m" or "1d".
            from_date (datetime.datetime): Earliest candle to include (inclusive).
            adjusted (bool, optional): Whether to apply split/dividend adjustment.

        Returns:
            dict: Merged OHLCVT lists in ascending order of time, starting at or after
                  from_date.

        Raises:
            ValueError: If the API returns no data on the very first request.
            Warning: Printed if the API history is exhausted before reaching from_date
                     (i.e., the returned chart starts later than from_date).
        """
        all_candles = []   # list of per-candle dicts: {"t", "o", "h", "l", "c", "v"}
        to_date = None     # None means "up to now" for the first call

        while True:
            batch = self.getChart(ticker, timeframe, to_date=to_date, adjusted=adjusted)
            time.sleep(0.2)

            if not batch["t"]:
                if not all_candles:
                    raise ValueError(
                        f"getChart() returned no data for {ticker} ({timeframe})."
                    )
                # API has no more history; stop here and warn the caller
                import warnings
                warnings.warn(
                    f"API history exhausted before reaching from_date={from_date}. "
                    f"Earliest available candle is {all_candles[0]['t']}.",
                    UserWarning
                )
                break

            # Convert batch dict-of-lists into a list-of-dicts for easier handling
            batch_candles = [
                {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}
                for t, o, h, l, c, v in zip(
                    batch["t"], batch["o"], batch["h"],
                    batch["l"], batch["c"], batch["v"]
                )
            ]

            # Determine the oldest timestamp in this batch
            earliest_in_batch = batch_candles[0]["t"]

            # Filter out candles that are already covered by a previous batch (dedup)
            if all_candles:
                existing_oldest = all_candles[0]["t"]
                batch_candles = [c for c in batch_candles if c["t"] < existing_oldest]

            if not batch_candles:
                # No new candles were fetched; API returned the same range — stop
                import warnings
                warnings.warn(
                    f"API returned no earlier data. "
                    f"Earliest available candle is {all_candles[0]['t']}.",
                    UserWarning
                )
                break

            # Prepend batch (it goes further back in time)
            all_candles = batch_candles + all_candles

            # Stop if we have reached from_date
            if all_candles[0]["t"] <= from_date:
                break

            # Next fetch should end just before the earliest candle we have so far
            to_date = all_candles[0]["t"]

        # Filter to only include candles at or after from_date
        all_candles = [c for c in all_candles if c["t"] >= from_date]

        return {
            "o": [c["o"] for c in all_candles],
            "h": [c["h"] for c in all_candles],
            "l": [c["l"] for c in all_candles],
            "c": [c["c"] for c in all_candles],
            "v": [c["v"] for c in all_candles],
            "t": [c["t"] for c in all_candles],
        }

    def getHoldings(self):
        """
        Retrieves all held stock positions in the account.

        Returns:
            dict: Mapping of ticker symbol to holding info.
                  e.g. {"AAPL": {"exchange": "US", "quantity": 10, "price": 178.5},
                         "005930": {"exchange": "KR", "quantity": 10, "price": 200000}}
                  - exchange: "KR" for domestic, "US" for US stocks.
                  - quantity: number of shares held.
                  - price: current last price in the stock's native currency.
        """
        headers = {"X-Tossinvest-Account": str(self.account_seq)}
        response = self._request("GET", "/api/v1/holdings", headers=headers)
        items = response.get("result", {}).get("items", [])

        result = {}
        for item in items:
            symbol = item["symbol"]
            market = item.get("marketCountry", "")
            # marketCountry is "KR" or "US" per the API spec
            exchange = market if market in ("KR", "US") else market
            result[symbol] = {
                "exchange": exchange,
                "quantity": float(item["quantity"]),
                "price": float(item["lastPrice"]),
            }
        return result

    def getKrwDeposit(self):
        """
        Retrieves the available KRW cash buying power in the account.

        Returns:
            float: KRW amount available for purchase (integer value, won units).
        """
        headers = {"X-Tossinvest-Account": str(self.account_seq)}
        response = self._request(
            "GET", "/api/v1/buying-power",
            headers=headers,
            params={"currency": "KRW"}
        )
        return float(response.get("result", {}).get("cashBuyingPower", 0))

    def getUsdDeposit(self):
        """
        Retrieves the available USD cash buying power in the account.

        Returns:
            float: USD amount available for purchase (decimal, dollar units).
        """
        headers = {"X-Tossinvest-Account": str(self.account_seq)}
        response = self._request(
            "GET", "/api/v1/buying-power",
            headers=headers,
            params={"currency": "USD"}
        )
        return float(response.get("result", {}).get("cashBuyingPower", 0))

    def buyChase(self, ticker, quantity, refresh_period=3.):
        """
        Places a buy order at current bid price and periodically adjusts it if the bid price rises.
        """
        # Initial order at current bid price
        book = self.getBook(ticker)
        if not book["bids_p"]:
            raise ValueError(f"No bid price available for {ticker}")
        price = book["bids_p"][0]  # nearest bid price
        order_id = self.buy(ticker, quantity, price)

        while True:
            time.sleep(refresh_period)
            book = self.getBook(ticker)
            if not book["bids_p"]:
                continue
            new_price = book["bids_p"][0]
            if new_price > price:
                # modify order with new higher bid price
                self.modifyOrder(order_id, price=new_price)
                price = new_price

    def sellChase(self, ticker, quantity, refresh_period=3.):
        """
        Places a sell order at current ask price and periodically adjusts it if the ask price falls.
        """
        # Initial order at current ask price
        book = self.getBook(ticker)
        if not book["asks_p"]:
            raise ValueError(f"No ask price available for {ticker}")
        price = book["asks_p"][0]  # nearest ask price
        order_id = self.sell(ticker, quantity, price)

        while True:
            time.sleep(refresh_period)
            book = self.getBook(ticker)
            if not book["asks_p"]:
                continue
            new_price = book["asks_p"][0]
            if new_price < price:
                # modify order with new lower ask price
                self.modifyOrder(order_id, price=new_price)
                price = new_price
