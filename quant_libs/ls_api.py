import os
import sys
import time
import logging
import datetime
import warnings
import requests


class LSAPIError(Exception):
    """
    Custom exception raised for errors returned by the LS Securities (LS증권) Open API.
    """
    def __init__(self, code, message, request_id=None, data=None, status_code=None):
        self.code = code
        self.message = message
        self.request_id = request_id
        self.data = data
        self.status_code = status_code
        super().__init__(f"LSAPIError (Status {status_code}, Code: {code}): {message} (Request ID: {request_id})")

    @classmethod
    def from_response(cls, response):
        """
        Creates an LSAPIError from an HTTP response or API error message.
        """
        status_code = response.status_code
        request_id = response.headers.get("X-Request-Id") or response.headers.get("tr_cont_key")
        code = response.headers.get("rsp_cd")
        message = response.headers.get("rsp_msg")

        try:
            err_data = response.json()
            if isinstance(err_data, dict):
                # Format 1: {"error_code": "...", "error_description": "..."}
                if "error_code" in err_data or "error_description" in err_data:
                    return cls(
                        code=err_data.get("error_code", code or "unknown_error"),
                        message=err_data.get("error_description", message or ""),
                        request_id=request_id,
                        data=err_data,
                        status_code=status_code
                    )
                # Format 2: {"rsp_cd": "...", "rsp_msg": "..."}
                if "rsp_cd" in err_data or "rsp_msg" in err_data:
                    return cls(
                        code=err_data.get("rsp_cd", code or "unknown_error"),
                        message=err_data.get("rsp_msg", message or ""),
                        request_id=request_id,
                        data=err_data,
                        status_code=status_code
                    )
                # Format 3: {"error": "...", "message": "..."}
                if "error" in err_data:
                    err = err_data["error"]
                    if isinstance(err, dict):
                        return cls(
                            code=err.get("code", code or "unknown_error"),
                            message=err.get("message", message or ""),
                            request_id=request_id,
                            data=err.get("data"),
                            status_code=status_code
                        )
                    return cls(
                        code=str(err),
                        message=err_data.get("message") or err_data.get("error_description", message or ""),
                        request_id=request_id,
                        data=err_data,
                        status_code=status_code
                    )
        except ValueError:
            pass

        # Fallback using response headers or text
        return cls(
            code=code or "http_error",
            message=message or response.text or "HTTP request failed",
            request_id=request_id,
            data=None,
            status_code=status_code
        )


LSTradeError = LSAPIError


class LSTrade:
    """
    Trading system client for LS Securities (LS증권) Open API.
    Provides identical interface and capabilities to TossTrade, with seamless multi-asset
    support across Korean Equities (국내주식), Korean Futures/Options (국내선물옵션),
    and Overseas Equities (해외주식).
    """
    def __init__(self, account_no=None, appkey=None, appsecretkey=None):
        # --- Logger setup (default: INFO) ---
        self._logger = logging.getLogger(__name__)
        if not self._logger.handlers:
            _handler = logging.StreamHandler(sys.stdout)
            _handler.setFormatter(logging.Formatter(
                "[%(asctime)s] %(levelname)s [LSTrade] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
            self._logger.addHandler(_handler)
        self._logger.setLevel(logging.INFO)

        # Read API keys from parameters or environment variables
        self.appkey = appkey or os.environ.get("LS_APP_KEY") or os.environ.get("LS_API_KEY")
        self.appsecretkey = appsecretkey or os.environ.get("LS_APP_SECRET") or os.environ.get("LS_SECRET_KEY")

        if not self.appkey or not self.appsecretkey:
            raise ValueError(
                "Authorization keys must be defined in environment variables (LS_APP_KEY and LS_APP_SECRET) "
                "or passed to the constructor."
            )

        self.base_url = "https://openapi.ls-sec.co.kr:8080"
        self.session = requests.Session()

        # Token caching state
        self._access_token = None
        self._token_expiry = 0

        self.account_no = account_no or os.environ.get("LS_ACCOUNT_NO")
        self.account_type = "BROKERAGE"

        # If account_no is not provided, attempt to resolve default account
        if self.account_no is None:
            self._logger.debug("account_no not provided; resolving default account.")
            try:
                self.resolve_default_account()
            except Exception as e:
                self._logger.warning("Could not automatically resolve default account: %s", e)

        self._logger.info("LSTrade initialised (account_no=%s, account_type=%s).", self.account_no, self.account_type)

    # ------------------------------------------------------------------
    # Logging control
    # ------------------------------------------------------------------

    def setLogLevel(self, level):
        """
        Sets the logging verbosity for this LSTrade instance.

        Args:
            level: A logging level constant or string name.
                   e.g. logging.DEBUG, logging.INFO, "DEBUG", "INFO",
                        "WARNING", "ERROR", "CRITICAL".
        """
        if isinstance(level, str):
            numeric = getattr(logging, level.upper(), None)
            if numeric is None:
                raise ValueError(f"Unknown log level: {level!r}")
            level = numeric
        self._logger.setLevel(level)
        self._logger.info("Log level set to %s.", logging.getLevelName(level))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_token(self):
        """
        Retrieves a valid OAuth2 access token, executing the token client credentials
        flow if necessary or if the token is close to expiring (within 60 seconds).
        """
        now = time.time()
        # If token is still valid (with 60 seconds buffer), reuse it
        if self._access_token and now < self._token_expiry - 60:
            self._logger.debug("Reusing cached OAuth2 token (expires in %.0fs).", self._token_expiry - now)
            return self._access_token

        self._logger.debug("Fetching new OAuth2 access token from LS Open API.")
        url = f"{self.base_url}/oauth2/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "client_credentials",
            "appkey": self.appkey,
            "appsecretkey": self.appsecretkey,
            "scope": "oob"
        }

        response = self.session.post(url, headers=headers, data=data)
        if response.status_code != 200:
            self._logger.error("OAuth2 token request failed (HTTP %s).", response.status_code)
            raise LSAPIError.from_response(response)

        res_json = response.json()
        if "access_token" not in res_json:
            raise LSAPIError.from_response(response)

        self._access_token = res_json["access_token"]
        self._token_expiry = now + int(res_json.get("expires_in", 86400))
        self._logger.debug("OAuth2 token obtained; expires in %ss.", res_json.get("expires_in", 86400))
        return self._access_token

    def _get_headers(self, tr_cd, tr_cont="N", tr_cont_key=""):
        """
        Builds the request headers required by LS Open API for a given transaction code.
        """
        token = self._get_token()
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
            "tr_cd": str(tr_cd),
            "tr_cont": tr_cont,
            "tr_cont_key": tr_cont_key or "",
            "mac_address": ""
        }
        return headers

    def _request(self, method, path, tr_cd=None, tr_cont="N", tr_cont_key="", headers=None, params=None, json=None):
        """
        Helper method to make HTTP requests with automatic header injection and error handling.
        """
        url = f"{self.base_url}{path}"
        req_headers = {}
        if tr_cd:
            req_headers = self._get_headers(tr_cd=tr_cd, tr_cont=tr_cont, tr_cont_key=tr_cont_key)
        else:
            token = self._get_token()
            req_headers = {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {token}"
            }

        if headers:
            req_headers.update(headers)

        self._logger.debug("%s %s  tr_cd=%s  params=%s  body=%s", method, path, tr_cd, params, json)
        response = self.session.request(method, url, headers=req_headers, params=params, json=json)
        self._logger.debug("Response HTTP %s from %s (tr_cd=%s).", response.status_code, path, tr_cd)

        if not (200 <= response.status_code < 300):
            self._logger.error(
                "API error on %s %s - HTTP %s: %s",
                method, path, response.status_code, response.text[:200]
            )
            raise LSAPIError.from_response(response)

        res_json = response.json()

        # Check for business-level errors returned with HTTP 200
        rsp_cd = response.headers.get("rsp_cd") or (res_json.get("rsp_cd") if isinstance(res_json, dict) else None)
        if rsp_cd and rsp_cd not in ("00000", "0", "00136"):
            rsp_msg = response.headers.get("rsp_msg") or (res_json.get("rsp_msg") if isinstance(res_json, dict) else "")
            if not ("완료" in rsp_msg or "정상" in rsp_msg):
                self._logger.error("API response error code: %s, headers=%s", rsp_cd, dict(response.headers))
                raise LSAPIError.from_response(response)

        return res_json

    def _classify_ticker(self, ticker, asset_type=None):
        """
        Classifies a ticker into "KR" (domestic stock), "FO" (futures/options), or "US" (overseas stock).

        Args:
            ticker (str): Ticker symbol.
            asset_type (str, optional): Explicit asset type ("KR", "FO", "US").

        Returns:
            str: "KR", "FO", or "US".
        """
        if asset_type:
            a = str(asset_type).upper()
            if a in ("KR", "KOREA", "STOCK", "DOMESTIC"):
                return "KR"
            if a in ("FO", "FUTURES", "OPTIONS", "FUTURE", "OPTION", "KR_FO"):
                return "FO"
            if a in ("US", "OVERSEAS", "GLOBAL", "USA"):
                return "US"

        if not ticker:
            return "FO" if getattr(self, "account_type", "") == "FUTURES_OPTIONS" else "KR"

        t = str(ticker).strip()

        # Korean index/stock futures & options: 8 characters (e.g. A016C000, 1016C000, 201TC350, 301TC350)
        if len(t) == 8 and (t[0] in ("1", "2", "3", "4", "A", "B", "C", "D") or not t.isalpha()):
            return "FO"

        # KR stock: 6 digits (e.g. 005930) or 'A' + 6 digits (e.g. A005930)
        if (len(t) == 6 and t.isdigit()) or (len(t) == 7 and t.startswith("A") and t[1:].isdigit()):
            return "KR"

        # US stock: 1 to 5 alphabetical characters (or containing '.' like BRK.B)
        clean_t = t.replace(".", "").replace("-", "")
        if clean_t.isalpha() and 1 <= len(clean_t) <= 6:
            return "US"

        if len(t) == 8:
            return "FO"

        return "KR"

    # ------------------------------------------------------------------
    # Account helpers
    # ------------------------------------------------------------------

    def resolve_default_account(self):
        """
        Fetches the user's account and sets the default account number.
        """
        self._logger.debug("Resolving default account.")
        accounts = self.getAccounts()
        if not accounts:
            raise ValueError("No LS brokerage accounts found for this user context.")
        self.account_no = accounts[0]["accountNo"]
        self.account_type = accounts[0].get("accountType", "BROKERAGE")
        self._logger.info("Default account resolved: account_no=%s (%s).", self.account_no, self.account_type)

    def getAccounts(self):
        """
        Retrieves the list of accounts associated with the user credentials.

        Returns:
            list: List of accounts containing accountNo, accountNm, accountType.
        """
        self._logger.debug("getAccounts() called.")
        # If user explicitly specified account_no, return it
        if self.account_no and self.account_no != "DEFAULT":
            acnt_str = str(self.account_no)
            acnt_type = "FUTURES_OPTIONS" if (acnt_str.startswith("200") or acnt_str.endswith("03")) else "BROKERAGE"
            self.account_type = acnt_type
            return [{
                "accountNo": acnt_str,
                "accountNm": "LS증권 계좌",
                "accountType": acnt_type
            }]

        # 1. Query CSPAQ12200 to discover brokerage account number tied to this AppKey
        try:
            payload = {
                "CSPAQ12200InBlock1": {
                    "BalCreTp": "0"
                }
            }
            res = self._request("POST", "/stock/accno", tr_cd="CSPAQ12200", json=payload)
            out1 = res.get("CSPAQ12200OutBlock1") or {}
            out2 = res.get("CSPAQ12200OutBlock2") or {}
            acnt_no = out1.get("AcntNo") or ""
            acnt_nm = out2.get("AcntNm") or "LS증권 위탁계좌"
            if acnt_no:
                self.account_no = acnt_no
                self.account_type = "BROKERAGE"
                accounts = [{
                    "accountNo": acnt_no,
                    "accountNm": acnt_nm,
                    "accountType": "BROKERAGE"
                }]
                self._logger.info("getAccounts() discovered brokerage account: %s", acnt_no)
                return accounts
        except Exception as e:
            self._logger.debug("CSPAQ12200 inquiry during getAccounts failed: %s", e)

        # 2. Query CFOBQ10500 to discover futures & options account tied to this AppKey
        try:
            payload = {
                "CFOBQ10500InBlock1": {
                    "RecCnt": 1
                }
            }
            res = self._request("POST", "/futureoption/accno", tr_cd="CFOBQ10500", json=payload)
            out1 = res.get("CFOBQ10500OutBlock1") or {}
            out2 = res.get("CFOBQ10500OutBlock2") or {}
            acnt_no = out1.get("AcntNo") or ""
            acnt_nm = out2.get("AcntNm") or "LS증권 선물옵션계좌"
            if acnt_no:
                self.account_no = acnt_no
                self.account_type = "FUTURES_OPTIONS"
                accounts = [{
                    "accountNo": acnt_no,
                    "accountNm": acnt_nm,
                    "accountType": "FUTURES_OPTIONS"
                }]
                self._logger.info("getAccounts() discovered futures/options account: %s", acnt_no)
                return accounts
        except Exception as e:
            self._logger.debug("CFOBQ10500 inquiry during getAccounts failed: %s", e)

        # 3. Fallback to CSPAQ22200
        try:
            payload = {
                "CSPAQ22200InBlock1": {
                    "BalCreTp": "0"
                }
            }
            res = self._request("POST", "/stock/accno", tr_cd="CSPAQ22200", json=payload)
            out2 = res.get("CSPAQ22200OutBlock2") or {}
            acnt_nm = out2.get("AcntNm") or "LS증권 계좌"
            acnt_no = self.account_no or "DEFAULT"
            self.account_type = "BROKERAGE"
            return [{
                "accountNo": acnt_no,
                "accountNm": acnt_nm,
                "accountType": "BROKERAGE"
            }]
        except Exception as e:
            self._logger.debug("CSPAQ22200 inquiry during getAccounts failed: %s", e)

        return [{
            "accountNo": self.account_no or "DEFAULT",
            "accountNm": "LS증권 계좌",
            "accountType": "BROKERAGE"
        }]

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def buy(self, ticker, quantity, price, asset_type=None):
        """
        Submits a buy order.
        If price is 0, a market order is submitted. Otherwise, a limit order is submitted.
        Supports KR Equities, KR Futures/Options, and Overseas (US) Equities.

        Args:
            ticker (str): The symbol of the stock/contract (e.g., "005930", "A016C000", "AAPL").
            quantity (float/int): The quantity to buy.
            price (float/int): The purchase price limit. 0 for market order.
            asset_type (str, optional): Explicit asset class ("KR", "FO", "US").

        Returns:
            str: The generated order ID.
        """
        if quantity < 0:
            return self.sell(ticker, -quantity, price, asset_type=asset_type)

        asset = self._classify_ticker(ticker, asset_type)
        order_type_str = "MARKET" if price == 0 else "LIMIT"
        self._logger.info(
            "buy() %s (%s)  qty=%s  price=%s  type=%s", ticker, asset, quantity, price, order_type_str
        )

        if asset == "FO":
            # KR Futures/Options order via CFOAT00100
            # FnoOrdprcPtnCode: "00" 지정가, "03" 시장가
            ord_prc_ptn = "03" if price == 0 else "00"
            payload = {
                "CFOAT00100InBlock1": {
                    "FnoIsuNo": ticker,
                    "BnsTpCode": "2",  # 2: 매수
                    "FnoOrdprcPtnCode": ord_prc_ptn,
                    "FnoOrdPrc": float(price),
                    "OrdQty": int(quantity)
                }
            }
            res = self._request("POST", "/futureoption/order", tr_cd="CFOAT00100", json=payload)
            out2 = res.get("CFOAT00100OutBlock2") or {}
            order_id = str(out2.get("OrdNo") or "")
            self._logger.info("buy() futures/options order placed: orderId=%s.", order_id)
            return order_id

        elif asset == "US":
            # Overseas (US) stock order via COSAT00301
            # OrdprcPtnCode: "00" 지정가, "03" 시장가
            ord_prc_ptn = "03" if price == 0 else "00"
            payload = {
                "COSAT00301InBlock1": {
                    "OrdPtnCode": "00",
                    "OrgOrdNo": 0,
                    "OrdMktCode": "82",  # 82: NASDAQ, 81: NYSE
                    "IsuNo": ticker,
                    "OrdQty": int(quantity),
                    "OvrsOrdPrc": float(price),
                    "OrdprcPtnCode": ord_prc_ptn,
                    "BrkTpCode": "1"  # 1: 매수
                }
            }
            res = self._request("POST", "/overseas-stock/order", tr_cd="COSAT00301", json=payload)
            out2 = res.get("COSAT00301OutBlock2") or {}
            order_id = str(out2.get("OrdNo") or "")
            self._logger.info("buy() overseas order placed: orderId=%s.", order_id)
            return order_id

        else:
            # KR domestic stock order via CSPAT00601
            # OrdprcPtnCode: "00" 보통(지정가), "03" 시장가
            clean_ticker = ticker[1:] if (len(ticker) == 7 and ticker.startswith("A")) else ticker
            ord_prc_ptn = "03" if price == 0 else "00"
            payload = {
                "CSPAT00601InBlock1": {
                    "IsuNo": clean_ticker,
                    "OrdQty": int(quantity),
                    "OrdPrc": float(price),
                    "BnsTpCode": "2",  # 2: 매수
                    "OrdprcPtnCode": ord_prc_ptn,
                    "MgntrnCode": "000",
                    "LoanDt": "",
                    "OrdCndiTpCode": "0"
                }
            }
            res = self._request("POST", "/stock/order", tr_cd="CSPAT00601", json=payload)
            out2 = res.get("CSPAT00601OutBlock2") or {}
            order_id = str(out2.get("OrdNo") or "")
            self._logger.info("buy() stock order placed: orderId=%s.", order_id)
            return order_id

    def sell(self, ticker, quantity, price, asset_type=None):
        """
        Submits a sell order.
        If price is 0, a market order is submitted. Otherwise, a limit order is submitted.
        Supports KR Equities, KR Futures/Options, and Overseas (US) Equities.

        Args:
            ticker (str): The symbol of the stock/contract (e.g., "005930", "A016C000", "AAPL").
            quantity (float/int): The quantity to sell.
            price (float/int): The sale price limit. 0 for market order.
            asset_type (str, optional): Explicit asset class ("KR", "FO", "US").

        Returns:
            str: The generated order ID.
        """
        if quantity < 0:
            return self.buy(ticker, -quantity, price, asset_type=asset_type)

        asset = self._classify_ticker(ticker, asset_type)
        order_type_str = "MARKET" if price == 0 else "LIMIT"
        self._logger.info(
            "sell() %s (%s)  qty=%s  price=%s  type=%s", ticker, asset, quantity, price, order_type_str
        )

        if asset == "FO":
            # KR Futures/Options sell order via CFOAT00100 (BnsTpCode="1")
            ord_prc_ptn = "03" if price == 0 else "00"
            payload = {
                "CFOAT00100InBlock1": {
                    "FnoIsuNo": ticker,
                    "BnsTpCode": "1",  # 1: 매도
                    "FnoOrdprcPtnCode": ord_prc_ptn,
                    "FnoOrdPrc": float(price),
                    "OrdQty": int(quantity)
                }
            }
            res = self._request("POST", "/futureoption/order", tr_cd="CFOAT00100", json=payload)
            out2 = res.get("CFOAT00100OutBlock2") or {}
            order_id = str(out2.get("OrdNo") or "")
            self._logger.info("sell() futures/options order placed: orderId=%s.", order_id)
            return order_id

        elif asset == "US":
            # Overseas (US) stock sell order via COSAT00301 (BrkTpCode="2")
            ord_prc_ptn = "03" if price == 0 else "00"
            payload = {
                "COSAT00301InBlock1": {
                    "OrdPtnCode": "00",
                    "OrgOrdNo": 0,
                    "OrdMktCode": "82",
                    "IsuNo": ticker,
                    "OrdQty": int(quantity),
                    "OvrsOrdPrc": float(price),
                    "OrdprcPtnCode": ord_prc_ptn,
                    "BrkTpCode": "2"  # 2: 매도
                }
            }
            res = self._request("POST", "/overseas-stock/order", tr_cd="COSAT00301", json=payload)
            out2 = res.get("COSAT00301OutBlock2") or {}
            order_id = str(out2.get("OrdNo") or "")
            self._logger.info("sell() overseas order placed: orderId=%s.", order_id)
            return order_id

        else:
            # KR domestic stock sell order via CSPAT00601 (BnsTpCode="1")
            clean_ticker = ticker[1:] if (len(ticker) == 7 and ticker.startswith("A")) else ticker
            ord_prc_ptn = "03" if price == 0 else "00"
            payload = {
                "CSPAT00601InBlock1": {
                    "IsuNo": clean_ticker,
                    "OrdQty": int(quantity),
                    "OrdPrc": float(price),
                    "BnsTpCode": "1",  # 1: 매도
                    "OrdprcPtnCode": ord_prc_ptn,
                    "MgntrnCode": "000",
                    "LoanDt": "",
                    "OrdCndiTpCode": "0"
                }
            }
            res = self._request("POST", "/stock/order", tr_cd="CSPAT00601", json=payload)
            out2 = res.get("CSPAT00601OutBlock2") or {}
            order_id = str(out2.get("OrdNo") or "")
            self._logger.info("sell() stock order placed: orderId=%s.", order_id)
            return order_id

    def modifyOrder(self, order_id, quantity=None, price=None, order_type=None, ticker=None, asset_type=None):
        """
        Modifies an existing order's quantity or price.
        Supports KR Equities, KR Futures/Options, and Overseas (US) Equities.

        Args:
            order_id (str): The ID of the order to modify.
            quantity (float/int, optional): The new quantity. If None, uses remaining unfilled quantity.
            price (float/int, optional): The new price limit.
            order_type (str, optional): "LIMIT" or "MARKET". Deduced from price if omitted.
            ticker (str, optional): Ticker symbol if known.
            asset_type (str, optional): Explicit asset class ("KR", "FO", "US").

        Returns:
            str: The new generated order ID.
        """
        self._logger.info(
            "modifyOrder() orderId=%s  qty=%s  price=%s  type=%s",
            order_id, quantity, price, order_type
        )

        if not ticker or quantity is None:
            order_info = self.getOrder(order_id)
            if not ticker:
                ticker = order_info.get("symbol", "")
            if quantity is None:
                total_qty = float(order_info.get("quantity") or 0)
                execution = order_info.get("execution") or {}
                filled_qty = float(execution.get("filledQuantity") or 0)
                quantity = total_qty - filled_qty
                self._logger.debug("modifyOrder() filled quantity with unfilled amount: %s", quantity)

        asset = self._classify_ticker(ticker, asset_type)

        ord_prc_ptn = "00"
        if order_type == "MARKET" or (price is not None and price == 0):
            ord_prc_ptn = "03"

        if asset == "FO":
            # KR Futures/Options order modification via CFOAT00200
            payload = {
                "CFOAT00200InBlock1": {
                    "OrgOrdNo": int(order_id),
                    "FnoIsuNo": ticker,
                    "FnoOrdprcPtnCode": ord_prc_ptn,
                    "FnoOrdPrc": float(price) if price is not None else 0.0,
                    "MdfyQty": int(quantity or 0)
                }
            }
            res = self._request("POST", "/futureoption/order", tr_cd="CFOAT00200", json=payload)
            out2 = res.get("CFOAT00200OutBlock2") or {}
            new_order_id = str(out2.get("OrdNo") or "")
            self._logger.info("modifyOrder() FO new orderId=%s.", new_order_id)
            return new_order_id

        elif asset == "US":
            # Overseas stock order modification via COSAT00400 (TrxTpCode="1")
            payload = {
                "COSAT00400InBlock1": {
                    "RecCnt": 1,
                    "TrxTpCode": "1",  # 1: 정정
                    "CntryCode": "US",
                    "RsvOrdInptDt": "",
                    "RsvOrdNo": int(order_id),
                    "BnsTpCode": "",
                    "AcntNo": str(self.account_no or ""),
                    "Pwd": "",
                    "FcurrMktCode": "82",
                    "IsuNo": ticker,
                    "OrdQty": int(quantity or 0),
                    "OvrsOrdPrc": float(price) if price is not None else 0.0,
                    "OrdprcPtnCode": ord_prc_ptn,
                    "RsvOrdSrtDt": "",
                    "RsvOrdEndDt": "",
                    "RsvOrdCndiCode": "00",
                    "MgntrnCode": "000",
                    "LoanDt": "",
                    "LoanDtlClssCode": ""
                }
            }
            res = self._request("POST", "/overseas-stock/order", tr_cd="COSAT00400", json=payload)
            out1 = res.get("COSAT00400OutBlock1") or {}
            new_order_id = str(out1.get("RsvOrdNo") or order_id)
            self._logger.info("modifyOrder() overseas new orderId=%s.", new_order_id)
            return new_order_id

        else:
            # KR domestic stock order modification via CSPAT00701
            clean_ticker = ticker[1:] if (len(ticker) == 7 and ticker.startswith("A")) else ticker
            payload = {
                "CSPAT00701InBlock1": {
                    "OrgOrdNo": int(order_id),
                    "IsuNo": clean_ticker,
                    "OrdQty": int(quantity or 0),
                    "OrdprcPtnCode": ord_prc_ptn,
                    "OrdCndiTpCode": "0",
                    "OrdPrc": float(price) if price is not None else 0.0
                }
            }
            res = self._request("POST", "/stock/order", tr_cd="CSPAT00701", json=payload)
            out2 = res.get("CSPAT00701OutBlock2") or {}
            new_order_id = str(out2.get("OrdNo") or "")
            self._logger.info("modifyOrder() new orderId=%s.", new_order_id)
            return new_order_id

    def cancelOrder(self, order_id, ticker=None, quantity=None, asset_type=None):
        """
        Cancels an existing order.
        Supports KR Equities, KR Futures/Options, and Overseas (US) Equities.

        Args:
            order_id (str): The ID of the order to cancel.
            ticker (str, optional): Stock symbol (looked up if not specified).
            quantity (float/int, optional): Quantity to cancel (all remaining if not specified).
            asset_type (str, optional): Explicit asset class ("KR", "FO", "US").

        Returns:
            str: The order ID of the cancelled order.
        """
        self._logger.info("cancelOrder() orderId=%s.", order_id)

        if not ticker or quantity is None:
            order_info = self.getOrder(order_id)
            if not ticker:
                ticker = order_info.get("symbol", "")
            if quantity is None:
                total_qty = float(order_info.get("quantity") or 0)
                execution = order_info.get("execution") or {}
                filled_qty = float(execution.get("filledQuantity") or 0)
                quantity = total_qty - filled_qty

        asset = self._classify_ticker(ticker, asset_type)

        if asset == "FO":
            # KR Futures/Options cancellation via CFOAT00300
            payload = {
                "CFOAT00300InBlock1": {
                    "OrgOrdNo": int(order_id),
                    "FnoIsuNo": ticker,
                    "CancQty": int(quantity or 0)
                }
            }
            res = self._request("POST", "/futureoption/order", tr_cd="CFOAT00300", json=payload)
            out2 = res.get("CFOAT00300OutBlock2") or {}
            cancelled_id = str(out2.get("OrdNo") or order_id)
            self._logger.info("cancelOrder() FO cancelled orderId=%s.", cancelled_id)
            return cancelled_id

        elif asset == "US":
            # Overseas stock cancellation via COSAT00400 (TrxTpCode="2")
            payload = {
                "COSAT00400InBlock1": {
                    "RecCnt": 1,
                    "TrxTpCode": "2",  # 2: 취소
                    "CntryCode": "US",
                    "RsvOrdInptDt": "",
                    "RsvOrdNo": int(order_id),
                    "BnsTpCode": "",
                    "AcntNo": str(self.account_no or ""),
                    "Pwd": "",
                    "FcurrMktCode": "82",
                    "IsuNo": ticker,
                    "OrdQty": int(quantity or 0),
                    "OvrsOrdPrc": 0.0,
                    "OrdprcPtnCode": "00",
                    "RsvOrdSrtDt": "",
                    "RsvOrdEndDt": "",
                    "RsvOrdCndiCode": "00",
                    "MgntrnCode": "000",
                    "LoanDt": "",
                    "LoanDtlClssCode": ""
                }
            }
            res = self._request("POST", "/overseas-stock/order", tr_cd="COSAT00400", json=payload)
            out1 = res.get("COSAT00400OutBlock1") or {}
            cancelled_id = str(out1.get("RsvOrdNo") or order_id)
            self._logger.info("cancelOrder() overseas cancelled orderId=%s.", cancelled_id)
            return cancelled_id

        else:
            # KR domestic stock cancellation via CSPAT00801
            clean_ticker = ticker[1:] if (len(ticker) == 7 and ticker.startswith("A")) else ticker
            payload = {
                "CSPAT00801InBlock1": {
                    "OrgOrdNo": int(order_id),
                    "IsuNo": clean_ticker,
                    "OrdQty": int(quantity or 0)
                }
            }
            res = self._request("POST", "/stock/order", tr_cd="CSPAT00801", json=payload)
            out2 = res.get("CSPAT00801OutBlock2") or {}
            cancelled_id = str(out2.get("OrdNo") or order_id)
            self._logger.info("cancelOrder() stock cancelled orderId=%s.", cancelled_id)
            return cancelled_id

    def getOrder(self, order_id, symbol=None, asset_type=None):
        """
        Retrieves detailed information of a specific order.
        Supports KR Equities, KR Futures/Options, and Overseas (US) Equities.

        Args:
            order_id (str): The ID of the order.
            symbol (str, optional): The symbol if known.
            asset_type (str, optional): Explicit asset class ("KR", "FO", "US").

        Returns:
            dict: The detailed order information formatted identically to TossTrade.
        """
        self._logger.debug("getOrder() orderId=%s.", order_id)
        # 1. Search in cached recent orders
        orders_res = self.getOrders(limit=100, symbol=symbol, asset_type=asset_type)
        orders = orders_res.get("orders", [])
        for o in orders:
            if str(o.get("orderId")).strip() == str(order_id).strip():
                self._logger.debug("getOrder() found order: status=%s", o.get("status"))
                return o

        asset = self._classify_ticker(symbol, asset_type)

        # 2. Query respective order history TR directly
        if asset == "FO":
            payload = {
                "t0434InBlock": {
                    "expcode": symbol or "",
                    "chegb": "0",
                    "sortgb": "1",
                    "cts_ordno": str(order_id)
                }
            }
            try:
                res = self._request("POST", "/futureoption/accno", tr_cd="t0434", json=payload)
                items = res.get("t0434OutBlock1") or []
                for it in items:
                    if str(it.get("ordno")).strip() == str(order_id).strip():
                        return self._parse_order_item(it)
            except Exception as e:
                self._logger.debug("t0434 query in getOrder failed: %s", e)

        elif asset == "US":
            payload = {
                "COSAQ00102InBlock1": {
                    "RecCnt": 1,
                    "QryTpCode": "1",
                    "BkseqTpCode": "2",
                    "OrdMktCode": "00",
                    "BnsTpCode": "0",
                    "IsuNo": symbol or "",
                    "SrtOrdNo": 0,
                    "OrdDt": "",
                    "ExecYn": "0",
                    "CrcyCode": "USD",
                    "ThdayBnsAppYn": "0",
                    "LoanBalHldYn": "0"
                }
            }
            try:
                res = self._request("POST", "/overseas-stock/accno", tr_cd="COSAQ00102", json=payload)
                items = res.get("COSAQ00102OutBlock3") or []
                for it in items:
                    if str(it.get("OrdNo")).strip() == str(order_id).strip():
                        return self._parse_us_order_item(it)
            except Exception as e:
                self._logger.debug("COSAQ00102 query in getOrder failed: %s", e)

        else:
            payload = {
                "t0425InBlock": {
                    "expcode": symbol or "",
                    "chegb": "0",
                    "medosu": "0",
                    "sortgb": "1",
                    "cts_ordno": str(order_id)
                }
            }
            try:
                res = self._request("POST", "/stock/accno", tr_cd="t0425", json=payload)
                items = res.get("t0425OutBlock1") or []
                for it in items:
                    if str(it.get("ordno")).strip() == str(order_id).strip():
                        return self._parse_order_item(it)
            except Exception as e:
                self._logger.debug("t0425 query in getOrder failed: %s", e)

        # Return minimal default structure if not found
        return {
            "orderId": str(order_id),
            "symbol": symbol or "",
            "side": "BUY",
            "status": "OPEN",
            "quantity": 0.0,
            "price": 0.0,
            "execution": {
                "filledQuantity": 0.0,
                "averageFilledPrice": 0.0
            }
        }

    def _parse_order_item(self, item):
        """
        Normalizes an LS order item from t0425 (Stock) or t0434 (FO) into a dictionary compatible with TossTrade.
        """
        ordno = str(item.get("ordno") or "").strip()
        expcode = str(item.get("expcode") or "").strip()
        medosu = str(item.get("medosu") or "").strip()
        side = "SELL" if medosu in ("1", "매도") else "BUY"

        qty = float(item.get("qty") or 0)
        price = float(item.get("price") or 0)
        cheqty = float(item.get("cheqty") or 0)
        cheprice = float(item.get("cheprice") or 0)
        ordrem = float(item.get("ordrem") or 0)
        status_raw = str(item.get("status") or "").strip()

        # Normalize status to "OPEN", "FILLED", "PARTIALLY_FILLED", "CANCELLED", "REJECTED"
        if cheqty >= qty and qty > 0:
            status = "FILLED"
        elif "취소" in status_raw or (ordrem == 0 and cheqty < qty and "취소" in str(item.get("ordgb", ""))):
            status = "CANCELLED"
        elif "거부" in status_raw:
            status = "REJECTED"
        elif cheqty > 0 and ordrem > 0:
            status = "PARTIALLY_FILLED"
        else:
            status = "OPEN"

        return {
            "orderId": ordno,
            "symbol": expcode,
            "side": side,
            "status": status,
            "quantity": qty,
            "price": price,
            "execution": {
                "filledQuantity": cheqty,
                "averageFilledPrice": cheprice
            },
            "raw": item
        }

    def _parse_us_order_item(self, item):
        """
        Normalizes an LS overseas order item from COSAQ00102 into a dictionary compatible with TossTrade.
        """
        ordno = str(item.get("OrdNo") or "").strip()
        symbol = str(item.get("ShtnIsuNo") or item.get("IsuNo") or "").strip()
        bns_tp = str(item.get("BnsTpCode") or "").strip()
        side = "SELL" if bns_tp in ("1", "매도") else "BUY"

        qty = float(item.get("OrdQty") or 0)
        price = float(item.get("OvrsOrdPrc") or 0)
        exec_qty = float(item.get("ExecQty") or item.get("AllExecQty") or 0)
        exec_price = float(item.get("OvrsExecPrc") or 0)
        unerc_qty = float(item.get("UnercQty") or 0)
        status_raw = str(item.get("OrdTrxPtnNm") or item.get("MrcTpNm") or "").strip()

        if exec_qty >= qty and qty > 0:
            status = "FILLED"
        elif "취소" in status_raw or (unerc_qty == 0 and exec_qty < qty):
            status = "CANCELLED"
        elif "거부" in status_raw:
            status = "REJECTED"
        elif exec_qty > 0 and unerc_qty > 0:
            status = "PARTIALLY_FILLED"
        else:
            status = "OPEN"

        return {
            "orderId": ordno,
            "symbol": symbol,
            "side": side,
            "status": status,
            "quantity": qty,
            "price": price,
            "execution": {
                "filledQuantity": exec_qty,
                "averageFilledPrice": exec_price
            },
            "raw": item
        }

    def getOrders(self, status=None, symbol=None, from_date=None, to_date=None, cursor=None, limit=20, asset_type=None):
        """
        Retrieves list of orders filtered by status, symbol, and dates.
        Supports KR Equities, KR Futures/Options, and Overseas (US) Equities.

        Args:
            status (str, optional): Filter by status ('OPEN' or 'CLOSED'/'FILLED').
            symbol (str, optional): Filter by stock symbol.
            from_date (str, optional): Filter start date (YYYYMMDD or YYYY-MM-DD).
            to_date (str, optional): Filter end date (YYYYMMDD or YYYY-MM-DD).
            cursor (str, optional): Pagination cursor (cts_ordno).
            limit (int, optional): Page size (default 20, max 100).
            asset_type (str, optional): Explicit asset class ("KR", "FO", "US").

        Returns:
            dict: Dictionary with 'orders' list, 'nextCursor' string, and 'hasNext' boolean.
        """
        self._logger.debug(
            "getOrders() status=%s  symbol=%s  from=%s  to=%s  limit=%s  asset_type=%s",
            status, symbol, from_date, to_date, limit, asset_type
        )

        asset = self._classify_ticker(symbol, asset_type)

        # chegb: 0: 전체, 1: 체결, 2: 미체결
        chegb = "0"
        if status:
            s_upper = status.upper()
            if s_upper == "OPEN":
                chegb = "2"
            elif s_upper in ("CLOSED", "FILLED"):
                chegb = "1"

        parsed_orders = []
        next_cursor = None
        has_next = False

        if asset == "FO":
            # KR Futures/Options order inquiry via t0434
            payload = {
                "t0434InBlock": {
                    "expcode": symbol or "",
                    "chegb": chegb,
                    "sortgb": "1",
                    "cts_ordno": cursor or ""
                }
            }
            res = self._request("POST", "/futureoption/accno", tr_cd="t0434", json=payload)
            items = res.get("t0434OutBlock1") or []
            out = res.get("t0434OutBlock") or {}
            next_cursor = out.get("cts_ordno", "").strip()

            for it in items:
                o = self._parse_order_item(it)
                if symbol and o["symbol"] != symbol:
                    continue
                if status:
                    s_upper = status.upper()
                    if s_upper == "OPEN" and o["status"] not in ("OPEN", "PARTIALLY_FILLED"):
                        continue
                    if s_upper in ("CLOSED", "FILLED") and o["status"] not in ("FILLED", "CANCELLED", "REJECTED"):
                        continue
                parsed_orders.append(o)

            has_next = bool(next_cursor and len(items) >= 20)

        elif asset == "US":
            # Overseas stock order inquiry via COSAQ00102
            payload = {
                "COSAQ00102InBlock1": {
                    "RecCnt": 1,
                    "QryTpCode": "1",
                    "BkseqTpCode": "2",
                    "OrdMktCode": "00",
                    "BnsTpCode": "0",
                    "IsuNo": symbol or "",
                    "SrtOrdNo": 0,
                    "OrdDt": "",
                    "ExecYn": chegb,
                    "CrcyCode": "USD",
                    "ThdayBnsAppYn": "0",
                    "LoanBalHldYn": "0"
                }
            }
            res = self._request("POST", "/overseas-stock/accno", tr_cd="COSAQ00102", json=payload)
            items = res.get("COSAQ00102OutBlock3") or []

            for it in items:
                o = self._parse_us_order_item(it)
                if symbol and o["symbol"] != symbol:
                    continue
                if status:
                    s_upper = status.upper()
                    if s_upper == "OPEN" and o["status"] not in ("OPEN", "PARTIALLY_FILLED"):
                        continue
                    if s_upper in ("CLOSED", "FILLED") and o["status"] not in ("FILLED", "CANCELLED", "REJECTED"):
                        continue
                parsed_orders.append(o)

        else:
            # KR domestic stock order inquiry via t0425
            payload = {
                "t0425InBlock": {
                    "expcode": symbol or "",
                    "chegb": chegb,
                    "medosu": "0",
                    "sortgb": "1",
                    "cts_ordno": cursor or ""
                }
            }
            res = self._request("POST", "/stock/accno", tr_cd="t0425", json=payload)
            items = res.get("t0425OutBlock1") or []
            out = res.get("t0425OutBlock") or {}
            next_cursor = out.get("cts_ordno", "").strip()

            for it in items:
                o = self._parse_order_item(it)
                if symbol and o["symbol"] != symbol:
                    continue
                if status:
                    s_upper = status.upper()
                    if s_upper == "OPEN" and o["status"] not in ("OPEN", "PARTIALLY_FILLED"):
                        continue
                    if s_upper in ("CLOSED", "FILLED") and o["status"] not in ("FILLED", "CANCELLED", "REJECTED"):
                        continue
                parsed_orders.append(o)

            has_next = bool(next_cursor and len(items) >= 20)

        if limit and len(parsed_orders) > limit:
            parsed_orders = parsed_orders[:limit]

        self._logger.debug("getOrders() returned %d order(s)  hasNext=%s.", len(parsed_orders), has_next)

        return {
            "orders": parsed_orders,
            "nextCursor": next_cursor or None,
            "hasNext": has_next
        }

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def getKrwUsd(self):
        """
        Retrieves exchange rate for KRW per 1 USD (USD/KRW, ~1300-1400 KRW).
        """
        try:
            # Query overseas balance TR COSOQ00201 which returns BaseXchrat (기준환율)
            payload = {
                "COSOQ00201InBlock1": {
                    "RecCnt": 1,
                    "BaseDt": "",
                    "CrcyCode": "USD",
                    "AstkBalTpCode": "0"
                }
            }
            res = self._request("POST", "/overseas-stock/accno", tr_cd="COSOQ00201", json=payload)
            out3 = res.get("COSOQ00201OutBlock3") or []
            if isinstance(out3, list) and out3:
                rate = float(out3[0].get("BaseXchrat") or 0)
                if rate > 0:
                    return rate
            elif isinstance(out3, dict):
                rate = float(out3.get("BaseXchrat") or 0)
                if rate > 0:
                    return rate
        except Exception as e:
            self._logger.debug("Could not fetch exchange rate from COSOQ00201: %s", e)

        # Fallback to public foreign exchange rate
        try:
            r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5)
            if r.status_code == 200:
                data = r.json()
                rate = float(data["rates"]["KRW"])
                return rate
        except Exception:
            pass

        return 1350.0

    def getUsdKrw(self):
        """
        Retrieves exchange rate for USD per 1 KRW (KRW/USD, ~0.0007 USD).
        """
        krw_usd = self.getKrwUsd()
        if krw_usd > 0:
            return 1.0 / krw_usd
        return 0.00074

    def getPrice(self, ticker, asset_type=None):
        """
        Fetches the mid-price between the nearest bid and nearest ask.
        If orderbook mid-price cannot be calculated, falls back to the last traded price.
        Supports KR Equities, KR Futures/Options, and Overseas (US) Equities.

        Args:
            ticker (str): Symbol (e.g. "005930", "A016C000", "AAPL").
            asset_type (str, optional): Explicit asset class ("KR", "FO", "US").

        Returns:
            float: Mid-price or latest trade price.
        """
        self._logger.debug("getPrice() %s.", ticker)
        asset = self._classify_ticker(ticker, asset_type)

        try:
            book = self.getBook(ticker, asset_type=asset)
            if book["bids_p"] and book["asks_p"]:
                mid = (book["bids_p"][0] + book["asks_p"][0]) / 2.0
                self._logger.debug("getPrice() %s -> %.6g (from orderbook mid).", ticker, mid)
                return mid
        except Exception as e:
            self._logger.debug("Orderbook mid-price failed for %s (%s); trying current price.", ticker, e)

        if asset == "FO":
            # KR Futures/Options current price via t2111
            payload = {
                "t2111InBlock": {
                    "focode": ticker
                }
            }
            res = self._request("POST", "/futureoption/market-data", tr_cd="t2111", json=payload)
            out = res.get("t2111OutBlock") or {}
            price = float(out.get("price") or 0)
            self._logger.debug("getPrice() %s -> %.6g (from t2111).", ticker, price)
            return price

        elif asset == "US":
            # Overseas stock current price via g3106
            for exch in ("82", "81"):
                try:
                    payload = {
                        "g3106InBlock": {
                            "delaygb": "0",
                            "keysymbol": "",
                            "exchcd": exch,
                            "symbol": ticker
                        }
                    }
                    res = self._request("POST", "/overseas-stock/market-data", tr_cd="g3106", json=payload)
                    out = res.get("g3106OutBlock") or {}
                    price = float(out.get("price") or 0)
                    if price > 0:
                        self._logger.debug("getPrice() %s -> %.6g (from g3106, exch=%s).", ticker, price, exch)
                        return price
                except Exception as e:
                    self._logger.debug("g3106 failed for %s (exch=%s): %s", ticker, exch, e)
            return 0.0

        else:
            # KR domestic stock current price via t1102
            clean_ticker = ticker[1:] if (len(ticker) == 7 and ticker.startswith("A")) else ticker
            payload = {
                "t1102InBlock": {
                    "shcode": clean_ticker
                }
            }
            res = self._request("POST", "/stock/market-data", tr_cd="t1102", json=payload)
            out = res.get("t1102OutBlock") or {}
            price = float(out.get("price") or 0)
            self._logger.debug("getPrice() %s -> %.6g (from t1102).", ticker, price)
            return price

    def getBook(self, ticker, asset_type=None):
        """
        Retrieves the orderbook for a stock or derivatives contract.
        Supports KR Equities (10-step), KR Futures/Options (5-step), and Overseas US Equities (10-step).

        Args:
            ticker (str): Ticker symbol (e.g., "005930", "A016C000", "AAPL").
            asset_type (str, optional): Explicit asset class ("KR", "FO", "US").

        Returns:
            dict: Dict of bids/asks prices and quantities, sorted by nearest to farthest:
                  - bids_p: descending (highest bid nearest)
                  - asks_p: ascending (lowest ask nearest)
        """
        self._logger.debug("getBook() %s.", ticker)
        asset = self._classify_ticker(ticker, asset_type)

        if asset == "FO":
            # KR Futures/Options orderbook via t2112 (5-step bid/ask)
            payload = {
                "t2112InBlock": {
                    "shcode": ticker
                }
            }
            res = self._request("POST", "/futureoption/market-data", tr_cd="t2112", json=payload)
            out = res.get("t2112OutBlock") or {}

            bids_p = []
            bids_n = []
            asks_p = []
            asks_n = []

            for i in range(1, 6):
                bp = float(out.get(f"bidho{i}") or 0)
                bv = float(out.get(f"bidrem{i}") or 0)
                if bp > 0:
                    bids_p.append(bp)
                    bids_n.append(bv)

                ap = float(out.get(f"offerho{i}") or 0)
                av = float(out.get(f"offerrem{i}") or 0)
                if ap > 0:
                    asks_p.append(ap)
                    asks_n.append(av)

            self._logger.debug("getBook() FO %s  bids=%d  asks=%d.", ticker, len(bids_p), len(asks_p))
            return {
                "bids_p": bids_p,
                "bids_n": bids_n,
                "asks_p": asks_p,
                "asks_n": asks_n
            }

        elif asset == "US":
            # Overseas US stock orderbook via g3106 (10-step bid/ask)
            out = {}
            for exch in ("82", "81"):
                try:
                    payload = {
                        "g3106InBlock": {
                            "delaygb": "0",
                            "keysymbol": "",
                            "exchcd": exch,
                            "symbol": ticker
                        }
                    }
                    res = self._request("POST", "/overseas-stock/market-data", tr_cd="g3106", json=payload)
                    temp_out = res.get("g3106OutBlock") or {}
                    if temp_out.get("price") or temp_out.get("bidho1") or temp_out.get("offerho1"):
                        out = temp_out
                        break
                except Exception as e:
                    self._logger.debug("g3106 getBook failed for %s (exch=%s): %s", ticker, exch, e)

            bids_p = []
            bids_n = []
            asks_p = []
            asks_n = []

            for i in range(1, 11):
                bp = float(out.get(f"bidho{i}") or 0)
                bv = float(out.get(f"bidrem{i}") or 0)
                if bp > 0:
                    bids_p.append(bp)
                    bids_n.append(bv)

                ap = float(out.get(f"offerho{i}") or 0)
                av = float(out.get(f"offerrem{i}") or 0)
                if ap > 0:
                    asks_p.append(ap)
                    asks_n.append(av)

            # Fallback to single last price if orderbook levels are empty
            if not bids_p and not asks_p:
                price = float(out.get("price") or 0)
                if price > 0:
                    bids_p = [price]
                    bids_n = [1.0]
                    asks_p = [price]
                    asks_n = [1.0]

            self._logger.debug("getBook() US %s  bids=%d  asks=%d.", ticker, len(bids_p), len(asks_p))
            return {
                "bids_p": bids_p,
                "bids_n": bids_n,
                "asks_p": asks_p,
                "asks_n": asks_n
            }

        else:
            # KR domestic stock orderbook via t1101 (10-step bid/ask)
            clean_ticker = ticker[1:] if (len(ticker) == 7 and ticker.startswith("A")) else ticker
            payload = {
                "t1101InBlock": {
                    "shcode": clean_ticker
                }
            }
            res = self._request("POST", "/stock/market-data", tr_cd="t1101", json=payload)
            out = res.get("t1101OutBlock") or {}

            bids_p = []
            bids_n = []
            asks_p = []
            asks_n = []

            for i in range(1, 11):
                bp = float(out.get(f"bidho{i}") or 0)
                bv = float(out.get(f"bidrem{i}") or 0)
                if bp > 0:
                    bids_p.append(bp)
                    bids_n.append(bv)

                ap = float(out.get(f"offerho{i}") or 0)
                av = float(out.get(f"offerrem{i}") or 0)
                if ap > 0:
                    asks_p.append(ap)
                    asks_n.append(av)

            self._logger.debug("getBook() KR %s  bids=%d  asks=%d.", ticker, len(bids_p), len(asks_p))
            return {
                "bids_p": bids_p,
                "bids_n": bids_n,
                "asks_p": asks_p,
                "asks_n": asks_n
            }

    def getChart(self, ticker, timeframe, to_date=None, adjusted=False, asset_type=None):
        """
        Retrieves historical candle chart data for a stock or derivatives contract.
        Supports KR Equities, KR Futures/Options, and Overseas (US) Equities.

        Args:
            ticker (str): Stock or contract ticker (e.g. "005930", "A016C000", "AAPL").
            timeframe (str): "1m" (1-minute) or "1d" (daily).
            to_date (datetime.datetime or str, optional): Fetch candles before/up to this date.
            adjusted (bool, optional): Whether to apply split/dividend adjustment.
            asset_type (str, optional): Explicit asset class ("KR", "FO", "US").

        Returns:
            dict: OHLCVT lists sorted in ascending order of time.
        """
        self._logger.debug(
            "getChart() %s  tf=%s  to_date=%s  adjusted=%s  asset_type=%s.",
            ticker, timeframe, to_date, adjusted, asset_type
        )

        asset = self._classify_ticker(ticker, asset_type)

        to_dt = None
        if to_date is not None:
            if isinstance(to_date, (datetime.datetime, datetime.date)):
                to_dt = to_date
            elif isinstance(to_date, str):
                try:
                    to_dt = datetime.datetime.fromisoformat(to_date.replace("Z", "+00:00"))
                except ValueError:
                    to_dt = datetime.datetime.strptime(to_date[:8], "%Y%m%d")

        if to_dt is None:
            to_dt = datetime.datetime.now()

        parsed_candles = []

        if asset == "FO":
            # KR Futures/Options chart
            if timeframe == "1m":
                # Minute chart via t8465
                edate = to_dt.strftime("%Y%m%d")
                etime = to_dt.strftime("%H%M%S") if isinstance(to_dt, datetime.datetime) else "154500"
                sdate = (to_dt - datetime.timedelta(days=7)).strftime("%Y%m%d")
                payload = {
                    "t8465InBlock": {
                        "shcode": ticker,
                        "ncnt": 1,
                        "qrycnt": 500,
                        "nday": "0",
                        "sdate": sdate,
                        "stime": "090000",
                        "edate": edate,
                        "etime": etime,
                        "cts_date": "",
                        "cts_time": "",
                        "comp_yn": "N"
                    }
                }
                res = self._request("POST", "/futureoption/chart", tr_cd="t8465", json=payload)
                candles = res.get("t8465OutBlock1") or []
                for c in candles:
                    d_str = str(c.get("date") or "").strip()
                    t_str = str(c.get("time") or "").strip().zfill(6)
                    if not d_str:
                        continue
                    try:
                        dt = datetime.datetime.strptime(f"{d_str}{t_str}", "%Y%m%d%H%M%S")
                    except ValueError:
                        dt = datetime.datetime.strptime(d_str, "%Y%m%d")

                    parsed_candles.append({
                        "t": dt,
                        "o": float(c.get("open") or 0),
                        "h": float(c.get("high") or 0),
                        "l": float(c.get("low") or 0),
                        "c": float(c.get("close") or 0),
                        "v": float(c.get("jdiff_vol") or c.get("value") or 0)
                    })
            else:
                # Daily chart via t8466
                edate = to_dt.strftime("%Y%m%d")
                sdate = (to_dt - datetime.timedelta(days=730)).strftime("%Y%m%d")
                payload = {
                    "t8466InBlock": {
                        "shcode": ticker,
                        "gubun": "2",  # 2: 일
                        "qrycnt": 500,
                        "sdate": sdate,
                        "edate": edate,
                        "cts_date": "",
                        "comp_yn": "N"
                    }
                }
                res = self._request("POST", "/futureoption/chart", tr_cd="t8466", json=payload)
                candles = res.get("t8466OutBlock1") or []
                for c in candles:
                    d_str = str(c.get("date") or "").strip()
                    if not d_str:
                        continue
                    dt = datetime.datetime.strptime(d_str, "%Y%m%d")
                    parsed_candles.append({
                        "t": dt,
                        "o": float(c.get("open") or 0),
                        "h": float(c.get("high") or 0),
                        "l": float(c.get("low") or 0),
                        "c": float(c.get("close") or 0),
                        "v": float(c.get("jdiff_vol") or c.get("value") or 0)
                    })

        elif asset == "US":
            # Overseas US stock chart
            if timeframe == "1m":
                # Minute chart via g3203
                candles = []
                for exch in ("82", "81"):
                    try:
                        payload = {
                            "g3203InBlock": {
                                "delaygb": "0",
                                "keysymbol": "",
                                "exchcd": exch,
                                "symbol": ticker,
                                "ncnt": 1,
                                "qrycnt": 500,
                                "comp_yn": "N",
                                "sdate": "",
                                "edate": "",
                                "cts_date": "",
                                "cts_time": ""
                            }
                        }
                        res = self._request("POST", "/overseas-stock/chart", tr_cd="g3203", json=payload)
                        temp_candles = res.get("g3203OutBlock1") or []
                        if temp_candles:
                            candles = temp_candles
                            break
                    except Exception as e:
                        self._logger.debug("g3203 failed for %s (exch=%s): %s", ticker, exch, e)

                for c in candles:
                    d_str = str(c.get("date") or "").strip()
                    t_str = str(c.get("loctime") or c.get("time") or "").strip().zfill(6)
                    if not d_str:
                        continue
                    try:
                        dt = datetime.datetime.strptime(f"{d_str}{t_str}", "%Y%m%d%H%M%S")
                    except ValueError:
                        dt = datetime.datetime.strptime(d_str, "%Y%m%d")

                    parsed_candles.append({
                        "t": dt,
                        "o": float(c.get("open") or 0),
                        "h": float(c.get("high") or 0),
                        "l": float(c.get("low") or 0),
                        "c": float(c.get("close") or 0),
                        "v": float(c.get("exevol") or c.get("amount") or 0)
                    })
            else:
                # Daily chart via g3204
                candles = []
                for exch in ("82", "81"):
                    try:
                        payload = {
                            "g3204InBlock": {
                                "sujung": "Y" if adjusted else "N",
                                "delaygb": "0",
                                "keysymbol": "",
                                "exchcd": exch,
                                "symbol": ticker,
                                "gubun": "2",  # 2: 일
                                "qrycnt": 500,
                                "comp_yn": "N",
                                "sdate": "",
                                "edate": "",
                                "cts_date": "",
                                "cts_info": ""
                            }
                        }
                        res = self._request("POST", "/overseas-stock/chart", tr_cd="g3204", json=payload)
                        temp_candles = res.get("g3204OutBlock1") or []
                        if temp_candles:
                            candles = temp_candles
                            break
                    except Exception as e:
                        self._logger.debug("g3204 failed for %s (exch=%s): %s", ticker, exch, e)

                for c in candles:
                    d_str = str(c.get("date") or "").strip()
                    if not d_str:
                        continue
                    dt = datetime.datetime.strptime(d_str, "%Y%m%d")
                    parsed_candles.append({
                        "t": dt,
                        "o": float(c.get("open") or 0),
                        "h": float(c.get("high") or 0),
                        "l": float(c.get("low") or 0),
                        "c": float(c.get("close") or 0),
                        "v": float(c.get("volume") or c.get("amount") or 0)
                    })

        else:
            # KR domestic stock chart
            clean_ticker = ticker[1:] if (len(ticker) == 7 and ticker.startswith("A")) else ticker
            if timeframe == "1m":
                # Minute chart via t8412
                edate = to_dt.strftime("%Y%m%d")
                etime = to_dt.strftime("%H%M%S") if isinstance(to_dt, datetime.datetime) else "153000"
                sdate = (to_dt - datetime.timedelta(days=7)).strftime("%Y%m%d")
                payload = {
                    "t8412InBlock": {
                        "shcode": clean_ticker,
                        "ncnt": 1,
                        "qrycnt": 500,
                        "nday": "0",
                        "sdate": sdate,
                        "stime": "090000",
                        "edate": edate,
                        "etime": etime,
                        "cts_date": "",
                        "cts_time": "",
                        "comp_yn": "N"
                    }
                }
                res = self._request("POST", "/stock/chart", tr_cd="t8412", json=payload)
                candles = res.get("t8412OutBlock1") or []
                for c in candles:
                    d_str = str(c.get("date") or "").strip()
                    t_str = str(c.get("time") or "").strip().zfill(6)
                    if not d_str:
                        continue
                    try:
                        dt = datetime.datetime.strptime(f"{d_str}{t_str}", "%Y%m%d%H%M%S")
                    except ValueError:
                        dt = datetime.datetime.strptime(d_str, "%Y%m%d")

                    parsed_candles.append({
                        "t": dt,
                        "o": float(c.get("open") or 0),
                        "h": float(c.get("high") or 0),
                        "l": float(c.get("low") or 0),
                        "c": float(c.get("close") or 0),
                        "v": float(c.get("jdiff_vol") or c.get("value") or 0)
                    })
            else:
                # Daily chart via t8410
                edate = to_dt.strftime("%Y%m%d")
                sdate = (to_dt - datetime.timedelta(days=730)).strftime("%Y%m%d")
                payload = {
                    "t8410InBlock": {
                        "shcode": clean_ticker,
                        "gubun": "2",  # 2: 일
                        "qrycnt": 500,
                        "sdate": sdate,
                        "edate": edate,
                        "cts_date": "",
                        "comp_yn": "N",
                        "sujung": "Y" if adjusted else "N"
                    }
                }
                res = self._request("POST", "/stock/chart", tr_cd="t8410", json=payload)
                candles = res.get("t8410OutBlock1") or []

                for c in candles:
                    d_str = str(c.get("date") or "").strip()
                    if not d_str:
                        continue
                    dt = datetime.datetime.strptime(d_str, "%Y%m%d")
                    parsed_candles.append({
                        "t": dt,
                        "o": float(c.get("open") or 0),
                        "h": float(c.get("high") or 0),
                        "l": float(c.get("low") or 0),
                        "c": float(c.get("close") or 0),
                        "v": float(c.get("jdiff_vol") or c.get("value") or 0)
                    })

        # Ensure sorting in ascending order of time
        parsed_candles.sort(key=lambda x: x["t"])

        self._logger.debug(
            "getChart() %s  tf=%s  -> %d candles.", ticker, timeframe, len(parsed_candles)
        )

        return {
            "o": [x["o"] for x in parsed_candles],
            "h": [x["h"] for x in parsed_candles],
            "l": [x["l"] for x in parsed_candles],
            "c": [x["c"] for x in parsed_candles],
            "v": [x["v"] for x in parsed_candles],
            "t": [x["t"] for x in parsed_candles]
        }

    def getLongChart(self, ticker, timeframe, from_date, adjusted=False, asset_type=None):
        """
        Retrieves a long historical chart by repeatedly calling getChart() and merging
        results, fetching backwards in time until from_date is reached.

        Args:
            ticker (str): Stock or derivatives ticker.
            timeframe (str): "1m" or "1d".
            from_date (datetime.datetime): Earliest candle to include (inclusive).
            adjusted (bool, optional): Whether to apply split/dividend adjustment.
            asset_type (str, optional): Explicit asset class ("KR", "FO", "US").

        Returns:
            dict: Merged OHLCVT lists in ascending order of time, starting at or after from_date.
        """
        self._logger.debug(
            "getLongChart() %s  tf=%s  from_date=%s  adjusted=%s  asset_type=%s.",
            ticker, timeframe, from_date, adjusted, asset_type
        )
        all_candles = []
        to_date = None
        batch_count = 0

        while True:
            batch = self.getChart(ticker, timeframe, to_date=to_date, adjusted=adjusted, asset_type=asset_type)
            time.sleep(0.3)
            batch_count += 1

            if not batch["t"]:
                if not all_candles:
                    raise ValueError(
                        f"getChart() returned no data for {ticker} ({timeframe})."
                    )
                self._logger.warning(
                    "getLongChart() API history exhausted after %d batch(es). "
                    "Earliest candle is %s (requested from_date=%s).",
                    batch_count, all_candles[0]["t"], from_date
                )
                warnings.warn(
                    f"API history exhausted before reaching from_date={from_date}. "
                    f"Earliest available candle is {all_candles[0]['t']}.",
                    UserWarning
                )
                break

            batch_candles = [
                {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}
                for t, o, h, l, c, v in zip(
                    batch["t"], batch["o"], batch["h"],
                    batch["l"], batch["c"], batch["v"]
                )
            ]

            if all_candles:
                existing_oldest = all_candles[0]["t"]
                batch_candles = [c for c in batch_candles if c["t"] < existing_oldest]

            if not batch_candles:
                self._logger.warning(
                    "getLongChart() no new candles in batch %d — stopping. "
                    "Earliest candle is %s.",
                    batch_count, all_candles[0]["t"]
                )
                warnings.warn(
                    f"API returned no earlier data. "
                    f"Earliest available candle is {all_candles[0]['t']}.",
                    UserWarning
                )
                break

            all_candles = batch_candles + all_candles
            self._logger.debug(
                "getLongChart() batch %d: prepended %d candles (oldest=%s, total=%d).",
                batch_count, len(batch_candles), all_candles[0]["t"], len(all_candles)
            )

            if all_candles[0]["t"] <= from_date:
                self._logger.debug(
                    "getLongChart() reached from_date after %d batch(es).", batch_count
                )
                break

            to_date = all_candles[0]["t"]

        all_candles = [c for c in all_candles if c["t"] >= from_date]
        self._logger.debug(
            "getLongChart() %s  tf=%s  -> %d total candles over %d batch(es).",
            ticker, timeframe, len(all_candles), batch_count
        )

        return {
            "o": [c["o"] for c in all_candles],
            "h": [c["h"] for c in all_candles],
            "l": [c["l"] for c in all_candles],
            "c": [c["c"] for c in all_candles],
            "v": [c["v"] for c in all_candles],
            "t": [c["t"] for c in all_candles],
        }

    # ------------------------------------------------------------------
    # Account / deposit queries
    # ------------------------------------------------------------------

    def getHoldings(self):
        """
        Retrieves all held stock and derivatives positions in the account.

        Returns:
            dict: Mapping of ticker symbol to holding info.
                  e.g. {"005930": {"exchange": "KR", "quantity": 10, "price": 70000},
                        "A016C000": {"exchange": "KR_FO", "quantity": 1, "price": 944.8},
                        "AAPL": {"exchange": "US", "quantity": 5, "price": 220.5}}
        """
        self._logger.debug("getHoldings() called.")
        result = {}

        # 1. Domestic holdings via t0424 (주식잔고2)
        try:
            payload = {
                "t0424InBlock": {
                    "prcgb": "1",
                    "chegb": "2",
                    "dangb": "0",
                    "charge": "0",
                    "cts_expcode": ""
                }
            }
            res = self._request("POST", "/stock/accno", tr_cd="t0424", json=payload)
            items = res.get("t0424OutBlock1") or []
            for item in items:
                symbol = str(item.get("expcode") or "").strip()
                if not symbol:
                    continue
                qty = float(item.get("janqty") or 0)
                price = float(item.get("price") or item.get("pamt") or 0)
                result[symbol] = {
                    "exchange": "KR",
                    "quantity": qty,
                    "price": price
                }
        except Exception as e:
            self._logger.debug("getHoldings() error fetching domestic positions: %s", e)

        # 2. Futures & Options holdings via t0441
        try:
            payload = {
                "t0441InBlock": {
                    "cts_expcode": "",
                    "cts_medocd": ""
                }
            }
            res = self._request("POST", "/futureoption/accno", tr_cd="t0441", json=payload)
            items = res.get("t0441OutBlock1") or []
            for item in items:
                symbol = str(item.get("expcode") or "").strip()
                if not symbol:
                    continue
                qty = float(item.get("janqty") or item.get("qty") or 0)
                price = float(item.get("price") or item.get("pamt") or 0)
                result[symbol] = {
                    "exchange": "KR_FO",
                    "quantity": qty,
                    "price": price
                }
        except Exception as e:
            self._logger.debug("getHoldings() t0441 check: %s", e)

        # 3. Overseas holdings via COSOQ00201
        try:
            payload = {
                "COSOQ00201InBlock1": {
                    "RecCnt": 1,
                    "BaseDt": "",
                    "CrcyCode": "",
                    "AstkBalTpCode": "0"
                }
            }
            res = self._request("POST", "/overseas-stock/accno", tr_cd="COSOQ00201", json=payload)
            items = res.get("COSOQ00201OutBlock4") or []
            for item in items:
                symbol = str(item.get("ShtnIsuNo") or item.get("IsuNo") or "").strip()
                if not symbol:
                    continue
                qty = float(item.get("AstkBalQty") or 0)
                price = float(item.get("FcstckUprc") or 0)
                result[symbol] = {
                    "exchange": "US",
                    "quantity": qty,
                    "price": price
                }
        except Exception as e:
            self._logger.debug("getHoldings() overseas query check: %s", e)

        self._logger.debug("getHoldings() returned %d position(s).", len(result))
        return result

    def getKrwDeposit(self):
        """
        Retrieves the available KRW cash buying power in the account.

        Returns:
            float: KRW amount available for purchase.
        """
        self._logger.debug("getKrwDeposit() called.")
        # 1. CSPAQ22200 (위탁계좌 예수금및주문가능금액조회2)
        try:
            payload = {
                "CSPAQ22200InBlock1": {
                    "BalCreTp": "0"
                }
            }
            res = self._request("POST", "/stock/accno", tr_cd="CSPAQ22200", json=payload)
            out2 = res.get("CSPAQ22200OutBlock2") or {}
            amount = float(out2.get("MnyOrdAbleAmt") or out2.get("Dps") or 0)
            self._logger.debug("getKrwDeposit() -> %.0f KRW.", amount)
            return amount
        except Exception as e:
            self._logger.debug("CSPAQ22200 failed: %s; trying CSPAQ12200 / CFOBQ10500.", e)

        # 2. CSPAQ12200
        try:
            payload = {
                "CSPAQ12200InBlock1": {
                    "BalCreTp": "0"
                }
            }
            res = self._request("POST", "/stock/accno", tr_cd="CSPAQ12200", json=payload)
            out2 = res.get("CSPAQ12200OutBlock2") or {}
            amount = float(out2.get("MnyOrdAbleAmt") or out2.get("Dps") or 0)
            self._logger.debug("getKrwDeposit() -> %.0f KRW.", amount)
            return amount
        except Exception as e:
            self._logger.debug("CSPAQ12200 failed: %s; trying CFOBQ10500.", e)

        # 3. CFOBQ10500 (선물옵션계좌 예탁금 및 주문가능금액조회)
        try:
            payload = {
                "CFOBQ10500InBlock1": {
                    "RecCnt": 1
                }
            }
            res = self._request("POST", "/futureoption/accno", tr_cd="CFOBQ10500", json=payload)
            out2 = res.get("CFOBQ10500OutBlock2") or {}
            amount = float(out2.get("MnyOrdAbleAmt") or out2.get("OrdAbleAmt") or out2.get("Dps") or out2.get("DpsamtTotamt") or 0)
            self._logger.debug("getKrwDeposit() -> %.0f KRW (from CFOBQ10500).", amount)
            return amount
        except Exception as e:
            self._logger.error("getKrwDeposit() failed: %s", e)
            raise

    def getUsdDeposit(self):
        """
        Retrieves the available USD cash buying power in the account.

        Returns:
            float: USD amount available for purchase.
        """
        self._logger.debug("getUsdDeposit() called.")
        # COSOQ02701 (해외주식 예수금조회)
        try:
            payload = {
                "COSOQ02701InBlock1": {
                    "RecCnt": 1,
                    "CrcyCode": "USD"
                }
            }
            res = self._request("POST", "/overseas-stock/accno", tr_cd="COSOQ02701", json=payload)
            out3 = res.get("COSOQ02701OutBlock3") or []
            if isinstance(out3, list) and out3:
                amount = float(out3[0].get("FcurrOrdAbleAmt") or out3[0].get("FcurrDps") or 0)
                self._logger.debug("getUsdDeposit() -> %.4f USD.", amount)
                return amount
            elif isinstance(out3, dict):
                amount = float(out3.get("FcurrOrdAbleAmt") or out3.get("FcurrDps") or 0)
                self._logger.debug("getUsdDeposit() -> %.4f USD.", amount)
                return amount
        except Exception as e:
            self._logger.debug("COSOQ02701 failed: %s; checking COSOQ00201.", e)

        # Fallback to COSOQ00201
        try:
            payload = {
                "COSOQ00201InBlock1": {
                    "RecCnt": 1,
                    "BaseDt": "",
                    "CrcyCode": "USD",
                    "AstkBalTpCode": "0"
                }
            }
            res = self._request("POST", "/overseas-stock/accno", tr_cd="COSOQ00201", json=payload)
            out3 = res.get("COSOQ00201OutBlock3") or []
            if isinstance(out3, list) and out3:
                amount = float(out3[0].get("FcurrDps") or 0)
                self._logger.debug("getUsdDeposit() -> %.4f USD.", amount)
                return amount
            elif isinstance(out3, dict):
                amount = float(out3.get("FcurrDps") or 0)
                self._logger.debug("getUsdDeposit() -> %.4f USD.", amount)
                return amount
        except Exception as e:
            self._logger.debug("COSOQ00201 check failed: %s", e)

        return 0.0

    # ------------------------------------------------------------------
    # Chasing orders
    # ------------------------------------------------------------------

    def buyChase(self, ticker, quantity, refresh_period=3., asset_type=None):
        """
        Places a buy order at current bid price and periodically adjusts it if the bid price rises.
        Supports KR Equities, KR Futures/Options, and Overseas (US) Equities.
        """
        self._logger.info(
            "buyChase() %s  qty=%s  refresh=%.1fs  asset_type=%s.", ticker, quantity, refresh_period, asset_type
        )
        book = self.getBook(ticker, asset_type=asset_type)
        if not book["bids_p"]:
            raise ValueError(f"No bid price available for {ticker}")
        price = book["bids_p"][0]  # nearest bid price
        order_id = self.buy(ticker, quantity, price, asset_type=asset_type)
        self._logger.info("buyChase() initial order placed at %s (orderId=%s).", price, order_id)

        filled_price = 0
        while True:
            order_result = self.getOrder(order_id, symbol=ticker, asset_type=asset_type)
            status = order_result.get("status")
            execution = order_result.get("execution") or {}
            filled_qty = float(execution.get("filledQuantity") or 0)
            avg_price = float(execution.get("averageFilledPrice") or 0)

            self._logger.debug("buyChase() checking status=%s, filled_qty=%s", status, filled_qty)

            if status == "FILLED" or filled_qty >= quantity:
                filled_price = avg_price
                self._logger.info("buyChase() order fully executed at price %s.", filled_price)
                break

            if status in ("CANCELLED", "REJECTED"):
                filled_price = avg_price
                self._logger.warning("buyChase() order was %s. Executed price: %s", status, filled_price)
                break

            time.sleep(refresh_period)
            book = self.getBook(ticker, asset_type=asset_type)
            if not book["bids_p"]:
                self._logger.warning("buyChase() empty orderbook for %s; skipping refresh.", ticker)
                continue
            new_price = book["bids_p"][0]
            if new_price > price:
                self._logger.info(
                    "buyChase() bid rose %s -> %s; modifying orderId=%s.",
                    price, new_price, order_id
                )
                order_id = self.modifyOrder(order_id, price=new_price, ticker=ticker, asset_type=asset_type)
                price = new_price
            else:
                self._logger.debug(
                    "buyChase() bid unchanged at %s; waiting.", price
                )
        return filled_price

    def sellChase(self, ticker, quantity, refresh_period=3., asset_type=None):
        """
        Places a sell order at current ask price and periodically adjusts it if the ask price falls.
        Supports KR Equities, KR Futures/Options, and Overseas (US) Equities.
        """
        self._logger.info(
            "sellChase() %s  qty=%s  refresh=%.1fs  asset_type=%s.", ticker, quantity, refresh_period, asset_type
        )
        book = self.getBook(ticker, asset_type=asset_type)
        if not book["asks_p"]:
            raise ValueError(f"No ask price available for {ticker}")
        price = book["asks_p"][0]  # nearest ask price
        order_id = self.sell(ticker, quantity, price, asset_type=asset_type)
        self._logger.info("sellChase() initial order placed at %s (orderId=%s).", price, order_id)

        filled_price = 0
        while True:
            order_result = self.getOrder(order_id, symbol=ticker, asset_type=asset_type)
            status = order_result.get("status")
            execution = order_result.get("execution") or {}
            filled_qty = float(execution.get("filledQuantity") or 0)
            avg_price = float(execution.get("averageFilledPrice") or 0)

            self._logger.debug("sellChase() checking status=%s, filled_qty=%s", status, filled_qty)

            if status == "FILLED" or filled_qty >= quantity:
                filled_price = avg_price
                self._logger.info("sellChase() order fully executed at price %s.", filled_price)
                break

            if status in ("CANCELLED", "REJECTED"):
                filled_price = avg_price
                self._logger.warning("sellChase() order was %s. Executed price: %s", status, filled_price)
                break

            time.sleep(refresh_period)
            book = self.getBook(ticker, asset_type=asset_type)
            if not book["asks_p"]:
                self._logger.warning("sellChase() empty orderbook for %s; skipping refresh.", ticker)
                continue
            new_price = book["asks_p"][0]
            if new_price < price:
                self._logger.info(
                    "sellChase() ask fell %s -> %s; modifying orderId=%s.",
                    price, new_price, order_id
                )
                order_id = self.modifyOrder(order_id, price=new_price, ticker=ticker, asset_type=asset_type)
                price = new_price
            else:
                self._logger.debug(
                    "sellChase() ask unchanged at %s; waiting.", price
                )
        return filled_price

    def chaseOrders(self, ticker_quantity_pairs, refresh_period=3., asset_type=None):
        """
        Places buy/sell orders for the given stock/contract pairs and chases them in sequence.
        Positive quantities represent buy orders (placed at current bid price).
        Negative quantities represent sell orders (placed at current ask price).
        Supports KR Equities, KR Futures/Options, and Overseas (US) Equities.

        Returns a list of average filled prices corresponding to ticker_quantity_pairs.
        """
        self._logger.info("chaseOrders() called with %s.", ticker_quantity_pairs)
        filled_prices = [0.0] * len(ticker_quantity_pairs)
        orders = []

        for idx, (ticker, qty) in enumerate(ticker_quantity_pairs):
            if qty == 0:
                continue
            item_asset = asset_type or self._classify_ticker(ticker)
            book = self.getBook(ticker, asset_type=item_asset)
            if qty > 0:
                if not book["bids_p"]:
                    self._logger.warning("No bid price for %s, skipping.", ticker)
                    continue
                price = book["bids_p"][0]
                order_id = self.buy(ticker, qty, price, asset_type=item_asset)
                side = "BUY"
            else:
                if not book["asks_p"]:
                    self._logger.warning("No ask price for %s, skipping.", ticker)
                    continue
                price = book["asks_p"][0]
                order_id = self.sell(ticker, abs(qty), price, asset_type=item_asset)
                side = "SELL"
            time.sleep(0.5)

            orders.append({
                "idx": idx,
                "ticker": ticker,
                "asset": item_asset,
                "target_qty": abs(qty),
                "side": side,
                "order_id": order_id,
                "price": price,
                "last_bid": book["bids_p"][0] if book["bids_p"] else price,
                "last_ask": book["asks_p"][0] if book["asks_p"] else price,
                "status": "OPEN"
            })
            self._logger.info(
                "chaseOrders() initialized %s order for %s (qty=%s, price=%s, orderId=%s, asset=%s)",
                side, ticker, abs(qty), price, order_id, item_asset
            )

        while True:
            active_orders = [o for o in orders if o["status"] == "OPEN"]
            if not active_orders:
                break

            time.sleep(refresh_period)

            for o in active_orders:
                try:
                    order_result = self.getOrder(o["order_id"], symbol=o["ticker"], asset_type=o["asset"])
                    status = order_result.get("status")
                    execution = order_result.get("execution") or {}
                    filled_qty = float(execution.get("filledQuantity") or 0)
                    avg_price = float(execution.get("averageFilledPrice") or 0)

                    self._logger.debug(
                        "chaseOrders() checking order %s status=%s, filled_qty=%s",
                        o["order_id"], status, filled_qty
                    )

                    if status == "FILLED" or filled_qty >= o["target_qty"]:
                        o["status"] = "FILLED"
                        filled_prices[o["idx"]] = avg_price
                        self._logger.info(
                            "chaseOrders() order for %s fully executed at price %s.",
                            o["ticker"], avg_price
                        )
                        continue

                    if status in ("CANCELLED", "REJECTED"):
                        o["status"] = status
                        filled_prices[o["idx"]] = avg_price
                        self._logger.warning(
                            "chaseOrders() order for %s was %s. Executed price: %s",
                            o["ticker"], status, avg_price
                        )
                        continue

                    # Check for price changes
                    book = self.getBook(o["ticker"], asset_type=o["asset"])
                    if o["side"] == "BUY":
                        if not book["bids_p"] or not book["asks_p"]:
                            continue
                        new_bid = book["bids_p"][0]
                        new_ask = book["asks_p"][0]

                        # Adjust price if the bid or ask rises
                        if new_bid > o["price"] or new_ask > o["last_ask"]:
                            self._logger.info(
                                "chaseOrders() buy for %s: price rising (bid:%s->%s, ask:%s->%s). Modifying orderId=%s to new bid %s",
                                o["ticker"], o["price"], new_bid, o["last_ask"], new_ask, o["order_id"], new_bid
                            )
                            o["order_id"] = self.modifyOrder(o["order_id"], price=new_bid, ticker=o["ticker"], asset_type=o["asset"])
                            time.sleep(0.34)
                            o["price"] = new_bid
                        o["last_bid"] = new_bid
                        o["last_ask"] = new_ask
                    else:  # SELL
                        if not book["bids_p"] or not book["asks_p"]:
                            continue
                        new_bid = book["bids_p"][0]
                        new_ask = book["asks_p"][0]

                        # Adjust price if the ask or bid falls
                        if new_ask < o["price"] or new_bid < o["last_bid"]:
                            self._logger.info(
                                "chaseOrders() sell for %s: price falling (ask:%s->%s, bid:%s->%s). Modifying orderId=%s to new ask %s",
                                o["ticker"], o["price"], new_ask, o["last_bid"], new_bid, o["order_id"], new_ask
                            )
                            o["order_id"] = self.modifyOrder(o["order_id"], price=new_ask, ticker=o["ticker"], asset_type=o["asset"])
                            time.sleep(0.34)
                            o["price"] = new_ask
                        o["last_bid"] = new_bid
                        o["last_ask"] = new_ask
                    time.sleep(0.5)
                except Exception as e:
                    self._logger.error("Error in chaseOrders sweep loop for %s: %s", o["ticker"], e)

        self._logger.info("chaseOrders() finished. Executed prices: %s", filled_prices)
        return filled_prices


# Alias for convenience
LSApi = LSTrade
