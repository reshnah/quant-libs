import os
import sys
import re
import io
import time
import json
import hashlib
import tempfile
import logging
import calendar
import datetime
import warnings
import zipfile
import urllib.request
import requests


class KISAPIError(Exception):
    """
    Custom exception raised for errors returned by the Korea Investment & Securities
    (한국투자증권, KIS) Open API.
    """
    def __init__(self, code, message, request_id=None, data=None, status_code=None):
        self.code = code
        self.message = message
        self.request_id = request_id
        self.data = data
        self.status_code = status_code
        super().__init__(f"KISAPIError (Status {status_code}, Code: {code}): {message} (Request ID: {request_id})")

    @classmethod
    def from_response(cls, response):
        """
        Creates a KISAPIError from an HTTP response or API error message.
        """
        status_code = response.status_code
        request_id = response.headers.get("gt_uid") or response.headers.get("tr_cont") or response.headers.get("X-Request-Id")
        code = response.headers.get("msg_cd") or response.headers.get("rt_cd")
        message = response.headers.get("msg1")

        try:
            err_data = response.json()
            if isinstance(err_data, dict):
                # Format 1: {"error_code": "...", "error_description": "..."} (OAuth errors)
                if "error_code" in err_data or "error_description" in err_data:
                    return cls(
                        code=err_data.get("error_code", code or "unknown_error"),
                        message=err_data.get("error_description", message or ""),
                        request_id=request_id,
                        data=err_data,
                        status_code=status_code
                    )
                # Format 2: {"rt_cd": "...", "msg_cd": "...", "msg1": "..."}
                if "rt_cd" in err_data or "msg_cd" in err_data or "msg1" in err_data:
                    return cls(
                        code=err_data.get("msg_cd") or err_data.get("rt_cd") or code or "unknown_error",
                        message=err_data.get("msg1", message or ""),
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


KISTradeError = KISAPIError


class KISTrade:
    """
    Trading system client for Korea Investment & Securities (한국투자증권) Open API.
    Provides identical interface and capabilities to LSTrade and TossTrade, with seamless
    multi-asset support across Korean Equities (국내주식), Korean Futures/Options (국내선물옵션),
    and Overseas Equities (해외주식).
    """
    def __init__(self, account_no=None, appkey=None, appsecretkey=None, is_virtual=False, market=None, api_latency=0.06):
        # --- Logger setup (default: INFO) ---
        self._logger = logging.getLogger(__name__)
        if not self._logger.handlers:
            _handler = logging.StreamHandler(sys.stdout)
            _handler.setFormatter(logging.Formatter(
                "[%(asctime)s] %(levelname)s [KISTrade] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
            self._logger.addHandler(_handler)
        self._logger.setLevel(logging.INFO)

        # Market classification: "KRX" (한국주식), "FO" (선물옵션), or None
        self.market = str(market).strip().upper() if market else None

        # Resolve API keys based on market and environment variables
        # 한국주식: KISAPI_KRX_KEY / KIS_KRX_SECRET
        # 선물옵션: KISAPI_FO_KEY / KISAPI_FO_SECRET
        if self.market in ("KRX", "KR", "STOCK", "EQUITY", "DOMESTIC"):
            self.appkey = (
                appkey
                or os.environ.get("KISAPI_KRX_KEY")
                or os.environ.get("KIS_KRX_KEY")
                or os.environ.get("KIS_APP_KEY")
                or os.environ.get("KIS_API_KEY")
            )
            self.appsecretkey = (
                appsecretkey
                or os.environ.get("KIS_KRX_SECRET")
                or os.environ.get("KISAPI_KRX_SECRET")
                or os.environ.get("KIS_APP_SECRET")
                or os.environ.get("KIS_SECRET_KEY")
            )
            account_no = (
                account_no
                or os.environ.get("KISAPI_KRX_ACCOUNT_NO")
                or os.environ.get("KIS_KRX_ACCOUNT_NO")
                or os.environ.get("KIS_KRX_CANO")
                or os.environ.get("KIS_ACCOUNT_NO")
                or os.environ.get("KIS_CANO")
            )
            default_acnt_type = "BROKERAGE"
        elif self.market in ("FO", "FUTURES", "OPTIONS", "FUTURE", "OPTION", "DERIVATIVES", "KR_FO"):
            self.appkey = (
                appkey
                or os.environ.get("KISAPI_FO_KEY")
                or os.environ.get("KIS_FO_KEY")
                or os.environ.get("KIS_APP_KEY")
                or os.environ.get("KIS_API_KEY")
            )
            self.appsecretkey = (
                appsecretkey
                or os.environ.get("KISAPI_FO_SECRET")
                or os.environ.get("KIS_FO_SECRET")
                or os.environ.get("KIS_APP_SECRET")
                or os.environ.get("KIS_SECRET_KEY")
            )
            account_no = (
                account_no
                or os.environ.get("KISAPI_FO_ACCOUNT_NO")
                or os.environ.get("KIS_FO_ACCOUNT_NO")
                or os.environ.get("KIS_FO_CANO")
                or os.environ.get("KIS_ACCOUNT_NO")
                or os.environ.get("KIS_CANO")
            )
            default_acnt_type = "FUTURES_OPTIONS"
        else:
            self.appkey = (
                appkey
                or os.environ.get("KIS_APP_KEY")
                or os.environ.get("KIS_API_KEY")
                or os.environ.get("KISAPI_KRX_KEY")
                or os.environ.get("KISAPI_FO_KEY")
            )
            self.appsecretkey = (
                appsecretkey
                or os.environ.get("KIS_APP_SECRET")
                or os.environ.get("KIS_SECRET_KEY")
                or os.environ.get("KIS_KRX_SECRET")
                or os.environ.get("KISAPI_KRX_SECRET")
                or os.environ.get("KISAPI_FO_SECRET")
            )
            account_no = (
                account_no
                or os.environ.get("KIS_ACCOUNT_NO")
                or os.environ.get("KIS_CANO")
                or os.environ.get("KISAPI_KRX_ACCOUNT_NO")
                or os.environ.get("KISAPI_FO_ACCOUNT_NO")
            )
            default_acnt_type = "BROKERAGE"

        if not self.appkey or not self.appsecretkey:
            if self.market in ("FO", "FUTURES", "OPTIONS", "FUTURE", "OPTION", "DERIVATIVES", "KR_FO"):
                err_msg = (
                    "Authorization keys for futures/options market must be defined in environment variables "
                    "(KISAPI_FO_KEY and KISAPI_FO_SECRET) or passed to constructor."
                )
            elif self.market in ("KRX", "KR", "STOCK", "EQUITY", "DOMESTIC"):
                err_msg = (
                    "Authorization keys for KRX stock market must be defined in environment variables "
                    "(KISAPI_KRX_KEY and KIS_KRX_SECRET) or passed to constructor."
                )
            else:
                err_msg = (
                    "Authorization keys must be defined in environment variables "
                    "(for KRX: KISAPI_KRX_KEY and KIS_KRX_SECRET; for FO: KISAPI_FO_KEY and KISAPI_FO_SECRET; "
                    "or default KIS_APP_KEY and KIS_APP_SECRET) or passed to the constructor."
                )
            raise ValueError(err_msg)

        # Check virtual simulation trading flag
        env_virtual = os.environ.get("KIS_VIRTUAL", "").strip().lower() in ("true", "1", "y", "yes")
        self.is_virtual = is_virtual or env_virtual

        if self.is_virtual:
            self.base_url = "https://openapivts.koreainvestment.com:29443"
        else:
            self.base_url = "https://openapi.koreainvestment.com:9443"

        self.session = requests.Session()

        # Token caching state (in-memory + local filesystem cache)
        self._access_token = None
        self._token_expiry = 0
        self._token_cache_dir = os.environ.get("KIS_TOKEN_CACHE_DIR") or os.path.join(tempfile.gettempdir(), "kis_tokens")

        # Master code caching state (for option underlyings and expirations)
        self._master_cache = {}
        self._master_cache_date = None

        # Day/Night session configuration for domestic futures and options:
        # None: auto-detect based on current time (18:00 ~ 06:00 KST is night)
        # True: force night session
        # False: force day session
        self.is_night = None

        # API request rate limiting latency (default: 0.06 seconds for <= 18 req/sec)
        self.api_latency = max(0.0, float(api_latency if api_latency is not None else 0.06))

        self.account_no = account_no
        self.account_type = default_acnt_type

        # If account_no is not provided, attempt to resolve default account
        if self.account_no is None:
            self._logger.debug("account_no not provided; resolving default account.")
            try:
                self.resolve_default_account()
            except Exception as e:
                self._logger.warning("Could not automatically resolve default account: %s", e)

        self._logger.info(
            "KISTrade initialised (account_no=%s, market=%s, account_type=%s, is_virtual=%s, is_night=%s).",
            self.account_no, self.market, self.account_type, self.is_virtual, self.is_night
        )

    # ------------------------------------------------------------------
    # Logging & session control
    # ------------------------------------------------------------------

    def setLogLevel(self, level):
        """
        Sets the logging verbosity for this KISTrade instance.

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

    def setNight(self, is_night=None):
        """
        Sets or resets the day/night session mode for domestic futures & options trading and market data.

        Args:
            is_night (bool or None): If True, forces night session mode.
                                     If False, forces day session mode.
                                     If None (default), dynamically determines session mode
                                     based on current local time (18:00 ~ 06:00 KST).
        """
        if is_night is not None:
            self.is_night = bool(is_night)
        else:
            self.is_night = None
        self._logger.info("Night session mode set to %s (auto=%s).", self.is_night, self.is_night is None)

    def getMarket(self):
        """
        Returns the configured market classification for this KISTrade instance ('KRX', 'FO', etc.).
        """
        return self.market

    def setApiLatency(self, latency=0.06):
        """
        Sets the delay latency (in seconds) between API requests to respect the rate limit (e.g. 18 req/sec).
        Default is 0.06 seconds.

        Args:
            latency (float): Delay in seconds (e.g. 0.06).
        """
        self.api_latency = max(0.0, float(latency if latency is not None else 0.06))
        self._logger.info("API latency set to %.4fs.", self.api_latency)

    def getApiLatency(self):
        """
        Returns the current API request delay latency in seconds.
        """
        return getattr(self, "api_latency", 0.06)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_night(self):
        """
        Determines whether the current session should be treated as night session for domestic futures/options.
        If self.is_night is explicitly set (True/False), returns that value.
        Otherwise, checks current local time: returns True if between 18:00 and 06:00 KST, False otherwise.
        """
        if self.is_night is not None:
            return bool(self.is_night)
        now = datetime.datetime.now().time()
        # Domestic derivatives night session: 18:00:00 to 06:00:00 KST
        return now >= datetime.time(18, 0) or now < datetime.time(6, 0)

    def _is_option_ticker(self, ticker):
        """
        Determines whether a domestic derivatives contract ticker represents an option.
        Options in KRX:
        - Call: begins with '2' or 'B' (Weekly)
        - Put: begins with '3' or 'C' (Weekly)
        - Stock/Mini Options: 'D', 'E', 'J', 'K', etc., or 8-10 chars containing 'C' or 'P' marker
        """
        t = str(ticker or "").strip().upper()
        if len(t) in (8, 9, 10):
            if t[0] in ("2", "3", "B", "C", "D", "E", "J", "K"):
                return True
            if any(ch in t for ch in ("C", "P")) and not t.startswith("1"):
                return True
        return False

    def _is_stock_option(self, ticker):
        """
        Determines whether a domestic derivatives contract ticker represents an individual stock option (개별주식옵션).
        e.g. Samsung Electronics option 'B11611094', 'C11611094', '211...', '311...', 'B12...', etc.
        Index options have underlying codes 01 (KOSPI200), 05 (KSQ150), 06 (KRX300), 09 (VKOSPI), or AF/AJ/AK (Mini).
        """
        if not self._is_option_ticker(ticker):
            return False

        t = str(ticker or "").strip().upper()

        # Check master data cache if available
        if getattr(self, "_master_cache", None) and "contracts_by_underlying" in self._master_cache:
            for u_code, contracts in self._master_cache["contracts_by_underlying"].items():
                if any(c.get("code") == t or c.get("std_code") == t for c in contracts):
                    is_idx = u_code in ("KOSPI200", "KSQ150", "KRX300", "VKOSPI", "2001", "2002")
                    return not is_idx

        # Pattern check:
        # Index option 2nd & 3rd characters in KRX are: '01', '05', '06', '09', 'AF', 'AJ', 'AK'
        if len(t) >= 3:
            sub = t[1:3]
            if sub in ("01", "05", "06", "09", "AF", "AJ", "AK"):
                return False
            return True

        return False

    def _is_stock_future(self, ticker):
        """
        Determines whether a domestic derivatives contract ticker represents an individual stock future (개별주식선물).
        e.g. 'A11612' (Samsung Electronics futures) vs 'A01612' (KOSPI200 futures).
        """
        if self._is_option_ticker(ticker):
            return False

        t = str(ticker or "").strip().upper()
        if len(t) >= 3:
            sub = t[1:3]
            if sub not in ("01", "04", "05", "06", "07", "09", "AF", "AJ", "AK"):
                return True
        return False

    def _resolve_fo_market_div(self, ticker):
        """
        Resolves FID_COND_MRKT_DIV_CODE for domestic futures/options market data:
          - Stock Option (개별주식옵션, e.g. B11611094): 'JO' (Day only, no night session)
          - Stock Futures (개별주식선물, e.g. A11612): 'JF' (Day only, no night session)
          - Index Option (지수옵션, e.g. B01611750, 201TC350): 'O' (Day) / 'EU' (Night)
          - Index Futures (지수선물, e.g. 101TC000, A01612): 'F' (Day) / 'CM' (Night)
        """
        if self._is_stock_option(ticker):
            return "JO"
        if self._is_stock_future(ticker):
            return "JF"

        is_night = self._is_night()
        is_opt = self._is_option_ticker(ticker)
        if is_night:
            return "EU" if is_opt else "CM"
        else:
            return "O" if is_opt else "F"

    def _split_account(self, account_no=None):
        """
        Splits an account string into CANO (8 digits) and ACNT_PRDT_CD (2 digits).
        Supports formats: '12345678-01', '1234567801', or '12345678'.
        """
        acc = str(account_no or self.account_no or "").replace("-", "").strip()
        if len(acc) >= 10:
            return acc[:8], acc[8:10]
        elif len(acc) == 8:
            prdt = "03" if (getattr(self, "account_type", "") == "FUTURES_OPTIONS" or getattr(self, "market", "") in ("FO", "FUTURES", "OPTIONS", "FUTURE", "OPTION", "DERIVATIVES", "KR_FO")) else "01"
            return acc, prdt
        elif len(acc) == 0:
            return "00000000", "01"
        return acc.ljust(8, "0")[:8], "01"

    def _get_token_cache_filepath(self):
        """
        Generates a deterministic file path for caching the OAuth2 token
        based on the base URL (real/virtual), app key, and market.
        """
        try:
            os.makedirs(self._token_cache_dir, exist_ok=True)
            mode = "vts" if self.is_virtual else "real"
            key_val = str(self.appkey or "none")
            key_hash = hashlib.sha256(f"{self.base_url}:{key_val}".encode("utf-8")).hexdigest()[:16]
            key_prefix = key_val[:4] if len(key_val) >= 4 else "key"
            filename = f"kis_token_{mode}_{key_prefix}_{key_hash}.json"
            return os.path.join(self._token_cache_dir, filename)
        except Exception as e:
            self._logger.debug("Failed to determine token cache filepath: %s", e)
            return None

    def _load_token_from_file(self):
        """
        Attempts to load an unexpired OAuth2 token from the local filesystem cache.
        Returns the token string if valid, or None if expired or not found.
        """
        cache_path = self._get_token_cache_filepath()
        if not cache_path or not os.path.isfile(cache_path):
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            now = time.time()
            expires_at = data.get("expires_at", 0)
            token = data.get("access_token")

            # Check if token is still valid with 60s buffer
            if token and now < expires_at - 60:
                self._access_token = token
                self._token_expiry = expires_at
                issued_str = data.get("issued_datetime", "unknown")
                expires_str = data.get("expires_datetime", "unknown")
                remaining_sec = int(expires_at - now)
                self._logger.info(
                    "Reusing cached OAuth2 token from file (issued: %s, expires: %s, remaining: %ds): %s",
                    issued_str, expires_str, remaining_sec, cache_path
                )
                return token
            else:
                self._logger.debug("Cached token in %s has expired.", cache_path)
                return None
        except Exception as e:
            self._logger.debug("Failed to read token from cache file %s: %s", cache_path, e)
            return None

    def _save_token_to_file(self, token, expires_in, issued_at=None):
        """
        Saves the OAuth2 token and timestamp metadata to the local filesystem cache.
        """
        cache_path = self._get_token_cache_filepath()
        if not cache_path:
            return

        now = issued_at or time.time()
        expires_at = now + int(expires_in)
        issued_dt = datetime.datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
        expires_dt = datetime.datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M:%S")

        payload = {
            "access_token": token,
            "token_type": "Bearer",
            "issued_at": now,
            "issued_datetime": issued_dt,
            "expires_in": int(expires_in),
            "expires_at": expires_at,
            "expires_datetime": expires_dt,
            "base_url": self.base_url,
            "appkey_prefix": self.appkey[:4] if self.appkey else "",
            "market": getattr(self, "market", "")
        }

        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            self._logger.info("Saved OAuth2 token to local cache file: %s (expires: %s)", cache_path, expires_dt)
        except Exception as e:
            self._logger.warning("Failed to save token to cache file %s: %s", cache_path, e)

    def _get_token(self):
        """
        Retrieves a valid OAuth2 access token, executing client credentials flow
        if necessary or if the token is close to expiring (within 60 seconds).
        First checks in-memory cache, then checks local filesystem cache before
        requesting a new token from KIS Open API.
        """
        now = time.time()
        if self._access_token and now < self._token_expiry - 60:
            self._logger.debug("Reusing in-memory cached OAuth2 token (expires in %.0fs).", self._token_expiry - now)
            return self._access_token

        # Check local filesystem cache
        cached_file_token = self._load_token_from_file()
        if cached_file_token:
            return cached_file_token

        self._logger.info("Fetching new OAuth2 access token from KIS Open API (%s).", self.base_url)
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {
            "Content-Type": "application/json; charset=utf-8"
        }
        data = {
            "grant_type": "client_credentials",
            "appkey": self.appkey,
            "appsecret": self.appsecretkey
        }

        response = self.session.post(url, headers=headers, json=data)
        if response.status_code != 200:
            self._logger.error("OAuth2 token request failed (HTTP %s).", response.status_code)
            raise KISAPIError.from_response(response)

        res_json = response.json()
        if "access_token" not in res_json:
            raise KISAPIError.from_response(response)

        token = res_json["access_token"]
        expires_in = int(res_json.get("expires_in", 86400))
        self._access_token = token
        self._token_expiry = now + expires_in

        # Persist to local filesystem cache
        self._save_token_to_file(token, expires_in, issued_at=now)

        self._logger.debug("OAuth2 token obtained; expires in %ss.", expires_in)
        return self._access_token

    def _get_headers(self, tr_id, tr_cont="N", custtype="P", hashkey=None):
        """
        Builds the request headers required by KIS Open API for a given transaction ID.
        """
        token = self._get_token()
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.appkey,
            "appsecret": self.appsecretkey,
            "tr_id": str(tr_id),
            "tr_cont": tr_cont,
            "custtype": custtype
        }
        if hashkey:
            headers["hashkey"] = hashkey
        return headers

    def _request(self, method, path, tr_id=None, tr_cont="N", headers=None, params=None, json=None, suppress_error_log=False):
        """
        Helper method to make HTTP requests with automatic header injection and error handling.
        """
        url = f"{self.base_url}{path}"
        req_headers = {}
        if tr_id:
            req_headers = self._get_headers(tr_id=tr_id, tr_cont=tr_cont)
        else:
            token = self._get_token()
            req_headers = {
                "Content-Type": "application/json; charset=utf-8",
                "authorization": f"Bearer {token}",
                "appkey": self.appkey,
                "appsecret": self.appsecretkey
            }

        if headers:
            req_headers.update(headers)

        if getattr(self, "api_latency", 0) > 0:
            time.sleep(self.api_latency)

        self._logger.debug("%s %s  tr_id=%s  params=%s  body=%s", method, path, tr_id, params, json)
        response = self.session.request(method, url, headers=req_headers, params=params, json=json)
        self._logger.debug("Response HTTP %s from %s (tr_id=%s).", response.status_code, path, tr_id)

        if not (200 <= response.status_code < 300):
            if not suppress_error_log:
                self._logger.error(
                    "API error on %s %s - HTTP %s: %s",
                    method, path, response.status_code, response.text[:200]
                )
            else:
                self._logger.debug(
                    "API error on %s %s - HTTP %s: %s",
                    method, path, response.status_code, response.text[:200]
                )
            raise KISAPIError.from_response(response)

        res_json = response.json()

        # Check for business-level errors returned with HTTP 200
        rt_cd = res_json.get("rt_cd") if isinstance(res_json, dict) else None
        if rt_cd and rt_cd != "0":
            msg = res_json.get("msg1", "")
            if not ("완료" in msg or "정상" in msg or "성공" in msg):
                if not suppress_error_log:
                    self._logger.error("API response business error: rt_cd=%s, msg=%s", rt_cd, msg)
                else:
                    self._logger.debug("API response business error: rt_cd=%s, msg=%s", rt_cd, msg)
                raise KISAPIError.from_response(response)

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

        # KR stock: 6 digits (e.g. 005930) or 'A' + 6 digits (e.g. A005930)
        if (len(t) == 6 and t.isdigit()) or (len(t) == 7 and t.startswith("A") and t[1:].isdigit()):
            return "KR"

        # Korean index/stock futures & options: 8, 9, or 10 characters
        # e.g. 101TC350, 201TC350, B01611947, C01611947, A016C000
        if len(t) in (8, 9, 10) and (t[0] in ("1", "2", "3", "4", "A", "B", "C", "D", "E", "J", "K") or not t.isdigit()):
            return "FO"

        # US stock: 1 to 5 alphabetical characters (or containing '.' like BRK.B)
        clean_t = t.replace(".", "").replace("-", "")
        if clean_t.isalpha() and 1 <= len(clean_t) <= 6:
            return "US"

        if len(t) in (8, 9, 10):
            return "FO"

        return "KR"

    def _resolve_us_exchange(self, ticker, for_order=False):
        """
        Resolves US exchange code for quotation or trading order.
        For order: 'NASD', 'NYSE', 'AMEX'
        For quotation: 'NAS', 'NYS', 'AMS'
        """
        # Default to NASDAQ, as it covers most tech and common US symbols
        if for_order:
            return "NASD"
        return "NAS"

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
            raise ValueError("No KIS brokerage accounts found for this user context.")
        self.account_no = accounts[0]["accountNo"]
        self.account_type = accounts[0].get("accountType", "BROKERAGE")
        self._logger.info("Default account resolved: account_no=%s (%s).", self.account_no, self.account_type)

    def getAccounts(self):
        """
        Retrieves the list of accounts associated with the user credentials by querying:
          1. /uapi/domestic-stock/v1/trading/inquire-balance
          2. /uapi/domestic-futureoption/v1/trading/inquire-balance
          3. /uapi/domestic-futureoption/v1/trading/inquire-ngt-balance

        Returns:
            list: List of accounts containing accountNo, accountNm, accountType.
        """
        self._logger.debug("getAccounts() called.")
        accounts = []

        # Collect candidate CANO (8-digit account number) from account_no or environment variables
        canos = []
        if self.account_no and not str(self.account_no).startswith("DEFAULT"):
            c, _ = self._split_account(self.account_no)
            if c and c.isdigit() and c not in canos:
                canos.append(c)

        env_candidates = [
            "KISAPI_KRX_ACCOUNT_NO",
            "KISAPI_FO_ACCOUNT_NO",
            "KIS_KRX_ACCOUNT_NO",
            "KIS_FO_ACCOUNT_NO",
            "KIS_ACCOUNT_NO",
            "KIS_CANO",
            "KIS_KRX_CANO",
            "KIS_FO_CANO"
        ]
        for env_var in env_candidates:
            val = os.environ.get(env_var)
            if val and val.strip() and not val.strip().startswith("DEFAULT"):
                c, _ = self._split_account(val)
                if c and c.isdigit() and c not in canos:
                    canos.append(c)

        if not canos:
            self._logger.info(
                "getAccounts(): CANO (8-digit account number) is not provided or set in environment variables. "
                "KIS balance endpoints require CANO. Falling back to default configuration."
            )

        for cano in canos:
            # 1. Domestic stock balance: /uapi/domestic-stock/v1/trading/inquire-balance
            try:
                tr_id = "VTTC8434R" if self.is_virtual else "TTTC8434R"
                prdt_stock = "01"
                params = {
                    "CANO": cano,
                    "ACNT_PRDT_CD": prdt_stock,
                    "AFHR_FLPR_YN": "N",
                    "OFL_YN": "",
                    "INQR_DVSN": "02",
                    "UNPR_DVSN": "01",
                    "FUND_STTL_ICLD_YN": "N",
                    "FNCG_AMT_AUTO_RDPT_YN": "N",
                    "PRCS_DVSN": "00",
                    "CTX_AREA_FK100": "",
                    "CTX_AREA_NK100": ""
                }
                res = self._request("GET", "/uapi/domestic-stock/v1/trading/inquire-balance", tr_id=tr_id, params=params, suppress_error_log=True)
                out_cano = res.get("cano") or cano
                if out_cano:
                    acnt_no = f"{out_cano}-{prdt_stock}"
                    if not any(a["accountNo"] == acnt_no for a in accounts):
                        accounts.append({
                            "accountNo": acnt_no,
                            "accountNm": "한국투자증권 위탁계좌",
                            "accountType": "BROKERAGE"
                        })
            except Exception as e:
                self._logger.debug("getAccounts() stock inquire-balance failed for cano=%s: %s", cano, e)

            # 2. Domestic Futures/Options day balance: /uapi/domestic-futureoption/v1/trading/inquire-balance
            try:
                tr_id = "VTFO6118R" if self.is_virtual else "CTFO6118R"
                prdt_fo = "03"
                params = {
                    "CANO": cano,
                    "ACNT_PRDT_CD": prdt_fo,
                    "MGNA_DVSN": "01",
                    "EXCC_STAT_CD": "0",
                    "CTX_AREA_FK200": "",
                    "CTX_AREA_NK200": ""
                }
                res = self._request("GET", "/uapi/domestic-futureoption/v1/trading/inquire-balance", tr_id=tr_id, params=params, suppress_error_log=True)
                out_cano = res.get("cano") or cano
                if out_cano:
                    acnt_no = f"{out_cano}-{prdt_fo}"
                    if not any(a["accountNo"] == acnt_no for a in accounts):
                        accounts.append({
                            "accountNo": acnt_no,
                            "accountNm": "한국투자증권 선물옵션계좌",
                            "accountType": "FUTURES_OPTIONS"
                        })
            except Exception as e:
                self._logger.debug("getAccounts() FO inquire-balance failed for cano=%s: %s", cano, e)

            # 3. Domestic Futures/Options night balance: /uapi/domestic-futureoption/v1/trading/inquire-ngt-balance
            try:
                tr_id = "VTFO6118R" if self.is_virtual else "CTFN6118R"
                prdt_fo = "03"
                params = {
                    "CANO": cano,
                    "ACNT_PRDT_CD": prdt_fo,
                    "MGNA_DVSN": "01",
                    "EXCC_STAT_CD": "0",
                    "CTX_AREA_FK200": "",
                    "CTX_AREA_NK200": ""
                }
                res = self._request("GET", "/uapi/domestic-futureoption/v1/trading/inquire-ngt-balance", tr_id=tr_id, params=params, suppress_error_log=True)
                out_cano = res.get("cano") or cano
                if out_cano:
                    acnt_no = f"{out_cano}-{prdt_fo}"
                    if not any(a["accountNo"] == acnt_no for a in accounts):
                        accounts.append({
                            "accountNo": acnt_no,
                            "accountNm": "한국투자증권 (야간)선물옵션계좌",
                            "accountType": "FUTURES_OPTIONS"
                        })
            except Exception as e:
                self._logger.debug("getAccounts() FO inquire-ngt-balance failed for cano=%s: %s", cano, e)

        # Fallback if API calls returned no accounts (e.g. offline, mock, or credentials without network)
        if not accounts:
            if self.account_no and self.account_no != "DEFAULT":
                cano, prdt = self._split_account(self.account_no)
                acnt_type = "FUTURES_OPTIONS" if (prdt in ("03", "02") or getattr(self, "account_type", "") == "FUTURES_OPTIONS") else "BROKERAGE"
                accounts.append({
                    "accountNo": f"{cano}-{prdt}",
                    "accountNm": "한국투자증권 계좌",
                    "accountType": acnt_type
                })
            else:
                cano = os.environ.get("KIS_CANO") or (canos[0] if canos and canos[0] else "DEFAULT")
                prdt = os.environ.get("KIS_ACNT_PRDT_CD") or ("03" if self.market in ("FO", "FUTURES", "OPTIONS") else "01")
                acnt_type = "FUTURES_OPTIONS" if (prdt in ("03", "02") or self.market in ("FO", "FUTURES", "OPTIONS")) else "BROKERAGE"
                accounts.append({
                    "accountNo": f"{cano}-{prdt}",
                    "accountNm": "한국투자증권 선물옵션계좌" if acnt_type == "FUTURES_OPTIONS" else "한국투자증권 위탁계좌",
                    "accountType": acnt_type
                })

        # Sort accounts to prioritize based on market
        if self.market in ("FO", "FUTURES", "OPTIONS", "FUTURE", "OPTION", "DERIVATIVES", "KR_FO"):
            accounts.sort(key=lambda x: (0 if x.get("accountType") == "FUTURES_OPTIONS" else 1))
        elif self.market in ("KRX", "KR", "STOCK", "EQUITY", "DOMESTIC"):
            accounts.sort(key=lambda x: (0 if x.get("accountType") == "BROKERAGE" else 1))

        self._logger.info("getAccounts() resolved %d account(s): %s", len(accounts), [a["accountNo"] for a in accounts])
        return accounts

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def buy(self, ticker, quantity, price, asset_type=None):
        """
        Submits a buy order.
        If price is 0, a market order is submitted. Otherwise, a limit order is submitted.
        Supports KR Equities, KR Futures/Options, and Overseas (US) Equities.

        Args:
            ticker (str): The symbol of the stock/contract (e.g., "005930", "101TC350", "AAPL").
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

        cano, prdt = self._split_account()

        if asset == "FO":
            # KR Futures/Options buy order via /uapi/domestic-futureoption/v1/trading/order
            # Day: Real TTTO1101U / Virtual VTTO1101U
            # Night: Real STTN1101U (KRX futures/options) or JTCE1001U (Eurex options)
            is_night = self._is_night()
            is_opt = self._is_option_ticker(ticker)
            if is_night:
                tr_id = "VTTO1101U" if self.is_virtual else ("JTCE1001U" if is_opt else "STTN1101U")
            else:
                tr_id = "VTTO1101U" if self.is_virtual else "TTTO1101U"

            # SLL_BUY_DVSN_CD: '02' (매수), ORD_DVSN_CD: '01' 지정가, '02' 시장가
            ord_dvsn = "02" if price == 0 else "01"
            payload = {
                "ORD_PRCS_DVSN_CD": "02",
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "SLL_BUY_DVSN_CD": "02",
                "SHTN_PDNO": ticker,
                "ORD_QTY": str(int(quantity)),
                "UNIT_PRICE": str(round(price, 2)) if price > 0 else "0",
                "ORD_DVSN_CD": ord_dvsn
            }
            res = self._request("POST", "/uapi/domestic-futureoption/v1/trading/order", tr_id=tr_id, json=payload)
            out = res.get("output") or {}
            order_id = str(out.get("ODNO") or out.get("odno") or "")
            self._logger.info("buy() FO order placed (night=%s, tr_id=%s): orderId=%s.", is_night, tr_id, order_id)
            return order_id

        elif asset == "US":
            # Overseas (US) stock order via /uapi/overseas-stock/v1/trading/order
            # TR ID: Real TTTT1002U (US buy) / Virtual VTTT1002U
            # ORD_DVSN: '00' 지정가, '01' 시장가
            tr_id = "VTTT1002U" if self.is_virtual else "TTTT1002U"
            excg_cd = self._resolve_us_exchange(ticker, for_order=True)
            ord_dvsn = "01" if price == 0 else "00"
            payload = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "OVRS_EXCG_CD": excg_cd,
                "PDNO": ticker,
                "ORD_QTY": str(int(quantity)),
                "OVRS_ORD_UNPR": str(round(price, 4)) if price > 0 else "0",
                "ORD_SVR_DVSN_CD": "0",
                "ORD_DVSN": ord_dvsn
            }
            res = self._request("POST", "/uapi/overseas-stock/v1/trading/order", tr_id=tr_id, json=payload)
            out = res.get("output") or {}
            order_id = str(out.get("ODNO") or out.get("odno") or "")
            self._logger.info("buy() overseas order placed: orderId=%s.", order_id)
            return order_id

        else:
            # KR domestic stock order via /uapi/domestic-stock/v1/trading/order-cash
            # TR ID: Real TTTC0012U (Buy) / Virtual VTTC0012U
            # ORD_DVSN: '00' 지정가, '01' 시장가
            clean_ticker = ticker[1:] if (len(ticker) == 7 and ticker.startswith("A")) else ticker
            tr_id = "VTTC0012U" if self.is_virtual else "TTTC0012U"
            ord_dvsn = "01" if price == 0 else "00"
            payload = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "PDNO": clean_ticker,
                "ORD_DVSN": ord_dvsn,
                "ORD_QTY": str(int(quantity)),
                "ORD_UNPR": str(int(price)) if price > 0 else "0"
            }
            res = self._request("POST", "/uapi/domestic-stock/v1/trading/order-cash", tr_id=tr_id, json=payload)
            out = res.get("output") or {}
            order_id = str(out.get("ODNO") or out.get("odno") or "")
            self._logger.info("buy() stock order placed: orderId=%s.", order_id)
            return order_id

    def sell(self, ticker, quantity, price, asset_type=None):
        """
        Submits a sell order.
        If price is 0, a market order is submitted. Otherwise, a limit order is submitted.
        Supports KR Equities, KR Futures/Options, and Overseas (US) Equities.

        Args:
            ticker (str): The symbol of the stock/contract (e.g., "005930", "101TC350", "AAPL").
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

        cano, prdt = self._split_account()

        if asset == "FO":
            # KR Futures/Options sell order via /uapi/domestic-futureoption/v1/trading/order
            # Day: Real TTTO1101U / Virtual VTTO1101U
            # Night: Real STTN1101U (KRX futures/options) or JTCE1001U (Eurex options)
            is_night = self._is_night()
            is_opt = self._is_option_ticker(ticker)
            if is_night:
                tr_id = "VTTO1101U" if self.is_virtual else ("JTCE1001U" if is_opt else "STTN1101U")
            else:
                tr_id = "VTTO1101U" if self.is_virtual else "TTTO1101U"

            # SLL_BUY_DVSN_CD: '01' (매도), ORD_DVSN_CD: '01' 지정가, '02' 시장가
            ord_dvsn = "02" if price == 0 else "01"
            payload = {
                "ORD_PRCS_DVSN_CD": "02",
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "SLL_BUY_DVSN_CD": "01",
                "SHTN_PDNO": ticker,
                "ORD_QTY": str(int(quantity)),
                "UNIT_PRICE": str(round(price, 2)) if price > 0 else "0",
                "ORD_DVSN_CD": ord_dvsn
            }
            res = self._request("POST", "/uapi/domestic-futureoption/v1/trading/order", tr_id=tr_id, json=payload)
            out = res.get("output") or {}
            order_id = str(out.get("ODNO") or out.get("odno") or "")
            self._logger.info("sell() FO order placed (night=%s, tr_id=%s): orderId=%s.", is_night, tr_id, order_id)
            return order_id

        elif asset == "US":
            # Overseas (US) stock sell order via /uapi/overseas-stock/v1/trading/order
            # TR ID: Real TTTT1006U (US sell) / Virtual VTTT1001U
            tr_id = "VTTT1001U" if self.is_virtual else "TTTT1006U"
            excg_cd = self._resolve_us_exchange(ticker, for_order=True)
            ord_dvsn = "01" if price == 0 else "00"
            payload = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "OVRS_EXCG_CD": excg_cd,
                "PDNO": ticker,
                "ORD_QTY": str(int(quantity)),
                "OVRS_ORD_UNPR": str(round(price, 4)) if price > 0 else "0",
                "ORD_SVR_DVSN_CD": "0",
                "ORD_DVSN": ord_dvsn
            }
            res = self._request("POST", "/uapi/overseas-stock/v1/trading/order", tr_id=tr_id, json=payload)
            out = res.get("output") or {}
            order_id = str(out.get("ODNO") or out.get("odno") or "")
            self._logger.info("sell() overseas order placed: orderId=%s.", order_id)
            return order_id

        else:
            # KR domestic stock sell order via /uapi/domestic-stock/v1/trading/order-cash
            # TR ID: Real TTTC0011U (Sell) / Virtual VTTC0011U
            clean_ticker = ticker[1:] if (len(ticker) == 7 and ticker.startswith("A")) else ticker
            tr_id = "VTTC0011U" if self.is_virtual else "TTTC0011U"
            ord_dvsn = "01" if price == 0 else "00"
            payload = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "PDNO": clean_ticker,
                "ORD_DVSN": ord_dvsn,
                "ORD_QTY": str(int(quantity)),
                "ORD_UNPR": str(int(price)) if price > 0 else "0"
            }
            res = self._request("POST", "/uapi/domestic-stock/v1/trading/order-cash", tr_id=tr_id, json=payload)
            out = res.get("output") or {}
            order_id = str(out.get("ODNO") or out.get("odno") or "")
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
        cano, prdt = self._split_account()

        is_market = (order_type == "MARKET") or (price is not None and price == 0)

        if asset == "FO":
            # KR Futures/Options modify via /uapi/domestic-futureoption/v1/trading/order-rvsecncl
            # Day: Real TTTO1103U / Virtual VTTO1103U
            # Night: Real STTN1103U (KRX futures/options) or JTCE1002U (Eurex options)
            is_night = self._is_night()
            is_opt = self._is_option_ticker(ticker)
            if is_night:
                tr_id = "VTTO1103U" if self.is_virtual else ("JTCE1002U" if is_opt else "STTN1103U")
            else:
                tr_id = "VTTO1103U" if self.is_virtual else "TTTO1103U"

            ord_dvsn = "02" if is_market else "01"
            payload = {
                "ORD_PRCS_DVSN_CD": "02",
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "RVSE_CNCL_DVSN_CD": "01",  # 01: 정정
                "ORGN_ODNO": str(order_id),
                "ORD_QTY": str(int(quantity or 0)),
                "UNIT_PRICE": str(round(price, 2)) if (price is not None and price > 0) else "0",
                "ORD_DVSN_CD": ord_dvsn
            }
            res = self._request("POST", "/uapi/domestic-futureoption/v1/trading/order-rvsecncl", tr_id=tr_id, json=payload)
            out = res.get("output") or {}
            new_order_id = str(out.get("ODNO") or out.get("odno") or order_id)
            self._logger.info("modifyOrder() FO new orderId=%s (night=%s, tr_id=%s).", new_order_id, is_night, tr_id)
            return new_order_id

        elif asset == "US":
            # Overseas stock modify via /uapi/overseas-stock/v1/trading/order-rvsecncl
            # TR ID: Real TTTT1004U / Virtual VTTT1004U
            tr_id = "VTTT1004U" if self.is_virtual else "TTTT1004U"
            excg_cd = self._resolve_us_exchange(ticker, for_order=True)
            payload = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "OVRS_EXCG_CD": excg_cd,
                "PDNO": ticker,
                "ORGN_ODNO": str(order_id),
                "RVSE_CNCL_DVSN_CD": "01",  # 01: 정정
                "ORD_QTY": str(int(quantity or 0)),
                "OVRS_ORD_UNPR": str(round(price, 4)) if (price is not None and price > 0) else "0",
                "ORD_SVR_DVSN_CD": "0"
            }
            res = self._request("POST", "/uapi/overseas-stock/v1/trading/order-rvsecncl", tr_id=tr_id, json=payload)
            out = res.get("output") or {}
            new_order_id = str(out.get("ODNO") or out.get("odno") or order_id)
            self._logger.info("modifyOrder() overseas new orderId=%s.", new_order_id)
            return new_order_id

        else:
            # KR domestic stock modify via /uapi/domestic-stock/v1/trading/order-rvsecncl
            # TR ID: Real TTTC0013U / Virtual VTTC0013U
            tr_id = "VTTC0013U" if self.is_virtual else "TTTC0013U"
            ord_dvsn = "01" if is_market else "00"
            payload = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "KRX_FWDG_ORD_ORGNO": "",
                "ORGN_ODNO": str(order_id),
                "ORD_DVSN": ord_dvsn,
                "RVSE_CNCL_DVSN_CD": "01",  # 01: 정정
                "ORD_QTY": str(int(quantity or 0)),
                "ORD_UNPR": str(int(price)) if (price is not None and price > 0) else "0",
                "QTY_ALL_ORD_YN": "N"
            }
            res = self._request("POST", "/uapi/domestic-stock/v1/trading/order-rvsecncl", tr_id=tr_id, json=payload)
            out = res.get("output") or {}
            new_order_id = str(out.get("ODNO") or out.get("odno") or order_id)
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
        cano, prdt = self._split_account()

        if asset == "FO":
            # KR Futures/Options cancel via /uapi/domestic-futureoption/v1/trading/order-rvsecncl
            # Day: Real TTTO1103U / Virtual VTTO1103U
            # Night: Real STTN1103U (KRX futures/options) or JTCE1002U (Eurex options)
            is_night = self._is_night()
            is_opt = self._is_option_ticker(ticker)
            if is_night:
                tr_id = "VTTO1103U" if self.is_virtual else ("JTCE1002U" if is_opt else "STTN1103U")
            else:
                tr_id = "VTTO1103U" if self.is_virtual else "TTTO1103U"

            payload = {
                "ORD_PRCS_DVSN_CD": "02",
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "RVSE_CNCL_DVSN_CD": "02",  # 02: 취소
                "ORGN_ODNO": str(order_id),
                "ORD_QTY": str(int(quantity or 0)),
                "UNIT_PRICE": "0",
                "ORD_DVSN_CD": "01"
            }
            res = self._request("POST", "/uapi/domestic-futureoption/v1/trading/order-rvsecncl", tr_id=tr_id, json=payload)
            out = res.get("output") or {}
            cancelled_id = str(out.get("ODNO") or out.get("odno") or order_id)
            self._logger.info("cancelOrder() FO cancelled orderId=%s (night=%s, tr_id=%s).", cancelled_id, is_night, tr_id)
            return cancelled_id

        elif asset == "US":
            # Overseas stock cancel via /uapi/overseas-stock/v1/trading/order-rvsecncl
            # TR ID: Real TTTT1004U / Virtual VTTT1004U
            tr_id = "VTTT1004U" if self.is_virtual else "TTTT1004U"
            excg_cd = self._resolve_us_exchange(ticker, for_order=True)
            payload = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "OVRS_EXCG_CD": excg_cd,
                "PDNO": ticker,
                "ORGN_ODNO": str(order_id),
                "RVSE_CNCL_DVSN_CD": "02",  # 02: 취소
                "ORD_QTY": str(int(quantity or 0)),
                "OVRS_ORD_UNPR": "0",
                "ORD_SVR_DVSN_CD": "0"
            }
            res = self._request("POST", "/uapi/overseas-stock/v1/trading/order-rvsecncl", tr_id=tr_id, json=payload)
            out = res.get("output") or {}
            cancelled_id = str(out.get("ODNO") or out.get("odno") or order_id)
            self._logger.info("cancelOrder() overseas cancelled orderId=%s.", cancelled_id)
            return cancelled_id

        else:
            # KR domestic stock cancel via /uapi/domestic-stock/v1/trading/order-rvsecncl
            # TR ID: Real TTTC0013U / Virtual VTTC0013U
            tr_id = "VTTC0013U" if self.is_virtual else "TTTC0013U"
            payload = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "KRX_FWDG_ORD_ORGNO": "",
                "ORGN_ODNO": str(order_id),
                "ORD_DVSN": "00",
                "RVSE_CNCL_DVSN_CD": "02",  # 02: 취소
                "ORD_QTY": str(int(quantity or 0)),
                "ORD_UNPR": "0",
                "QTY_ALL_ORD_YN": "Y" if not quantity else "N"
            }
            res = self._request("POST", "/uapi/domestic-stock/v1/trading/order-rvsecncl", tr_id=tr_id, json=payload)
            out = res.get("output") or {}
            cancelled_id = str(out.get("ODNO") or out.get("odno") or order_id)
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
            dict: The detailed order information formatted identically to LSTrade / TossTrade.
        """
        self._logger.debug("getOrder() orderId=%s.", order_id)
        # 1. Search in cached recent orders
        orders_res = self.getOrders(limit=100, symbol=symbol, asset_type=asset_type)
        orders = orders_res.get("orders", [])
        for o in orders:
            if str(o.get("orderId")).strip() == str(order_id).strip():
                self._logger.debug("getOrder() found order: status=%s", o.get("status"))
                return o

        # Fallback minimal structure if not found
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
        Normalizes a domestic stock order item from inquire-daily-ccld into standardized dict.
        """
        odno = str(item.get("odno") or item.get("ODNO") or "").strip()
        pdno = str(item.get("pdno") or item.get("PDNO") or "").strip()
        sll_buy = str(item.get("sll_buy_dvsn_cd") or item.get("sll_buy_dvsn_cd_name") or "").strip()
        side = "SELL" if sll_buy in ("01", "1", "매도") else "BUY"

        qty = float(item.get("ord_qty") or 0)
        price = float(item.get("ord_unpr") or 0)
        ccld_qty = float(item.get("tot_ccld_qty") or item.get("ccld_qty") or 0)
        avg_price = float(item.get("avg_prvs") or item.get("pchs_avg_pric") or 0)
        rmn_qty = float(item.get("rmn_qty") or 0)
        cncl_qty = float(item.get("cncl_qty") or item.get("cncl_cfrm_qty") or 0)
        status_raw = str(item.get("rvse_cncl_dvsn_name") or item.get("cncl_yn") or "").strip()

        if ccld_qty >= qty and qty > 0:
            status = "FILLED"
        elif "취소" in status_raw or cncl_qty >= qty or (rmn_qty == 0 and ccld_qty < qty and cncl_qty > 0):
            status = "CANCELLED"
        elif "거부" in status_raw or float(item.get("rjct_qty") or 0) > 0:
            status = "REJECTED"
        elif ccld_qty > 0 and rmn_qty > 0:
            status = "PARTIALLY_FILLED"
        else:
            status = "OPEN"

        return {
            "orderId": odno,
            "symbol": pdno,
            "side": side,
            "status": status,
            "quantity": qty,
            "price": price,
            "execution": {
                "filledQuantity": ccld_qty,
                "averageFilledPrice": avg_price
            },
            "raw": item
        }

    def _parse_fo_order_item(self, item):
        """
        Normalizes a futures/options order item from inquire-ccnl into standardized dict.
        """
        odno = str(item.get("odno") or item.get("ODNO") or "").strip()
        pdno = str(item.get("pdno") or item.get("PDNO") or "").strip()
        sll_buy = str(item.get("sll_buy_dvsn_cd") or "").strip()
        side = "SELL" if sll_buy in ("01", "1", "매도") else "BUY"

        qty = float(item.get("ord_qty") or 0)
        price = float(item.get("ord_idx") or 0)
        ccld_qty = float(item.get("tot_ccld_qty") or 0)
        avg_price = float(item.get("avg_idx") or 0)
        rmn_qty = float(item.get("qty") or 0)
        status_raw = str(item.get("trad_dvsn_name") or "").strip()

        if ccld_qty >= qty and qty > 0:
            status = "FILLED"
        elif "취소" in status_raw:
            status = "CANCELLED"
        elif float(item.get("rjct_qty") or 0) > 0:
            status = "REJECTED"
        elif ccld_qty > 0 and rmn_qty > 0:
            status = "PARTIALLY_FILLED"
        else:
            status = "OPEN"

        return {
            "orderId": odno,
            "symbol": pdno,
            "side": side,
            "status": status,
            "quantity": qty,
            "price": price,
            "execution": {
                "filledQuantity": ccld_qty,
                "averageFilledPrice": avg_price
            },
            "raw": item
        }

    def _parse_us_order_item(self, item):
        """
        Normalizes an overseas stock order item from inquire-ccnl into standardized dict.
        """
        odno = str(item.get("odno") or item.get("ODNO") or "").strip()
        pdno = str(item.get("pdno") or item.get("PDNO") or "").strip()
        sll_buy = str(item.get("sll_buy_dvsn_cd") or item.get("sll_buy_dvsn_cd_name") or "").strip()
        side = "SELL" if sll_buy in ("01", "1", "매도") else "BUY"

        qty = float(item.get("ft_ord_qty") or item.get("ord_qty") or 0)
        price = float(item.get("ft_ord_unpr3") or item.get("ord_unpr") or 0)
        ccld_qty = float(item.get("ft_ccld_qty") or 0)
        avg_price = float(item.get("ft_ccld_unpr3") or 0)
        nccs_qty = float(item.get("nccs_qty") or 0)
        status_raw = str(item.get("prcs_stat_name") or item.get("rvse_cncl_dvsn_name") or "").strip()

        if ccld_qty >= qty and qty > 0:
            status = "FILLED"
        elif "취소" in status_raw or (nccs_qty == 0 and ccld_qty < qty and "취소" in status_raw):
            status = "CANCELLED"
        elif "거부" in status_raw or item.get("rjct_rson"):
            status = "REJECTED"
        elif ccld_qty > 0 and nccs_qty > 0:
            status = "PARTIALLY_FILLED"
        else:
            status = "OPEN"

        return {
            "orderId": odno,
            "symbol": pdno,
            "side": side,
            "status": status,
            "quantity": qty,
            "price": price,
            "execution": {
                "filledQuantity": ccld_qty,
                "averageFilledPrice": avg_price
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
            cursor (str, optional): Pagination cursor.
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
        cano, prdt = self._split_account()

        today_str = datetime.date.today().strftime("%Y%m%d")
        start_dt = str(from_date).replace("-", "") if from_date else today_str
        end_dt = str(to_date).replace("-", "") if to_date else today_str

        # CCLD_DVSN: '00' 전체, '01' 체결, '02' 미체결
        ccld_dvsn = "00"
        if status:
            s_upper = status.upper()
            if s_upper == "OPEN":
                ccld_dvsn = "02"
            elif s_upper in ("CLOSED", "FILLED"):
                ccld_dvsn = "01"

        parsed_orders = []
        next_cursor = None
        has_next = False

        if asset == "FO":
            # KR Futures/Options order inquiry
            # Day: /uapi/domestic-futureoption/v1/trading/inquire-ccnl (Real TTTO5201R / Virtual VTTO5201R)
            # Night: /uapi/domestic-futureoption/v1/trading/inquire-ngt-ccnl (Real STTN5201R / Virtual VTTO5201R)
            is_night = self._is_night()
            if is_night:
                path = "/uapi/domestic-futureoption/v1/trading/inquire-ngt-ccnl"
                tr_id = "VTTO5201R" if self.is_virtual else "STTN5201R"
            else:
                path = "/uapi/domestic-futureoption/v1/trading/inquire-ccnl"
                tr_id = "VTTO5201R" if self.is_virtual else "TTTO5201R"

            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "STRT_ORD_DT": start_dt,
                "END_ORD_DT": end_dt,
                "SLL_BUY_DVSN_CD": "00",
                "CCLD_NCCS_DVSN": ccld_dvsn,
                "SORT_SQN": "DS",
                "STRT_ODNO": cursor or "",
                "PDNO": symbol or "",
                "MKET_ID_CD": "",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": ""
            }
            try:
                res = self._request("GET", path, tr_id=tr_id, params=params)
            except Exception as e:
                if is_night and not self.is_virtual:
                    self._logger.debug("Night FO order inquiry (%s) failed: %s; falling back to day endpoint.", tr_id, e)
                    path = "/uapi/domestic-futureoption/v1/trading/inquire-ccnl"
                    tr_id = "TTTO5201R"
                    res = self._request("GET", path, tr_id=tr_id, params=params)
                else:
                    raise
            items = res.get("output1") or []
            next_cursor = res.get("ctx_area_nk200", "").strip()

            for it in items:
                o = self._parse_fo_order_item(it)
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
            # Overseas stock order inquiry via /uapi/overseas-stock/v1/trading/inquire-ccnl
            # TR ID: Real TTTS3035R / Virtual VTTS3035R
            tr_id = "VTTS3035R" if self.is_virtual else "TTTS3035R"
            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "PDNO": symbol or "%",
                "ORD_STRT_DT": start_dt,
                "ORD_END_DT": end_dt,
                "SLL_BUY_DVSN": "00",
                "CCLD_NCCS_DVSN": ccld_dvsn,
                "OVRS_EXCG_CD": "%",
                "SORT_SQN": "DS",
                "ORD_DT": "",
                "ORD_GNO_BRNO": "",
                "ODNO": cursor or "",
                "CTX_AREA_NK200": "",
                "CTX_AREA_FK200": ""
            }
            res = self._request("GET", "/uapi/overseas-stock/v1/trading/inquire-ccnl", tr_id=tr_id, params=params)
            items = res.get("output") or []
            next_cursor = res.get("ctx_area_nk200", "").strip()

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

            has_next = bool(next_cursor and len(items) >= 20)

        else:
            # KR domestic stock order inquiry via /uapi/domestic-stock/v1/trading/inquire-daily-ccld
            # TR ID: Real TTTC0081R / Virtual VTTC0081R
            tr_id = "VTTC0081R" if self.is_virtual else "TTTC0081R"
            clean_ticker = (symbol[1:] if len(symbol) == 7 and symbol.startswith("A") else symbol) if symbol else ""
            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "INQR_STRT_DT": start_dt,
                "INQR_END_DT": end_dt,
                "SLL_BUY_DVSN_CD": "00",
                "INQR_DVSN": "00",
                "PDNO": clean_ticker,
                "CCLD_DVSN": ccld_dvsn,
                "ORD_GNO_BRNO": "",
                "ODNO": cursor or "",
                "INQR_DVSN_1": "",
                "INQR_DVSN_3": "00",
                "EXCG_ID_DVSN_CD": "KRX",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": ""
            }
            res = self._request("GET", "/uapi/domestic-stock/v1/trading/inquire-daily-ccld", tr_id=tr_id, params=params)
            items = res.get("output1") or []
            next_cursor = res.get("ctx_area_nk100", "").strip()

            for it in items:
                o = self._parse_order_item(it)
                if clean_ticker and o["symbol"] != clean_ticker:
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
            cano, prdt = self._split_account()
            tr_id = "VTTS3007R" if self.is_virtual else "TTTS3007R"
            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "OVRS_EXCG_CD": "NASD",
                "OVRS_ORD_UNPR": "0",
                "ITEM_CD": "AAPL"
            }
            res = self._request("GET", "/uapi/overseas-stock/v1/trading/inquire-psamount", tr_id=tr_id, params=params)
            out = res.get("output") or {}
            rate = float(out.get("exrt") or 0)
            if rate > 0:
                return rate
        except Exception as e:
            self._logger.debug("Could not fetch exchange rate from inquire-psamount: %s", e)

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
            ticker (str): Symbol (e.g. "005930", "101TC350", "AAPL").
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
            # KR Futures/Options current price via /uapi/domestic-futureoption/v1/quotations/inquire-price
            # TR ID: FHMIF10000000
            # FID_COND_MRKT_DIV_CODE:
            #   - Stock Options (개별주식옵션, e.g. B11611094): 'JO' (Day only, no night session)
            #   - Stock Futures (개별주식선물): 'JF' (Day only, no night session)
            #   - Index Options: Day 'O' / Night 'EU'
            #   - Index Futures: Day 'F' / Night 'CM'
            is_night = self._is_night()
            is_opt = self._is_option_ticker(ticker)
            is_stock_opt = self._is_stock_option(ticker)
            is_stock_fut = self._is_stock_future(ticker)
            mrkt_div = self._resolve_fo_market_div(ticker)
            params = {
                "FID_COND_MRKT_DIV_CODE": mrkt_div,
                "FID_INPUT_ISCD": ticker
            }
            try:
                res = self._request("GET", "/uapi/domestic-futureoption/v1/quotations/inquire-price", tr_id="FHMIF10000000", params=params)
            except Exception as e:
                if is_night and not (is_stock_opt or is_stock_fut):
                    fallback_div = "O" if is_opt else "F"
                    self._logger.debug("Night price query failed for %s (mrkt=%s): %s; trying day division %s.", ticker, mrkt_div, e, fallback_div)
                    params["FID_COND_MRKT_DIV_CODE"] = fallback_div
                    res = self._request("GET", "/uapi/domestic-futureoption/v1/quotations/inquire-price", tr_id="FHMIF10000000", params=params)
                else:
                    raise
            out = res.get("output1") or {}
            price = float(out.get("futs_prpr") or out.get("optn_prpr") or out.get("stck_prpr") or out.get("last") or 0)
            self._logger.debug("getPrice() %s -> %.6g (from FHMIF10000000, mrkt=%s, night=%s).", ticker, price, mrkt_div, is_night)
            return price

        elif asset == "US":
            # Overseas stock current price via /uapi/overseas-price/v1/quotations/price
            # TR ID: HHDFS00000300
            for excd in ("NAS", "NYS", "AMS"):
                try:
                    params = {
                        "AUTH": "",
                        "EXCD": excd,
                        "SYMB": ticker
                    }
                    res = self._request("GET", "/uapi/overseas-price/v1/quotations/price", tr_id="HHDFS00000300", params=params)
                    out = res.get("output") or {}
                    price = float(out.get("last") or 0)
                    if price > 0:
                        self._logger.debug("getPrice() %s -> %.6g (from HHDFS00000300, excd=%s).", ticker, price, excd)
                        return price
                except Exception as e:
                    self._logger.debug("HHDFS00000300 failed for %s (excd=%s): %s", ticker, excd, e)
            return 0.0

        else:
            # KR domestic stock current price via /uapi/domestic-stock/v1/quotations/inquire-price
            # TR ID: FHKST01010100
            clean_ticker = ticker[1:] if (len(ticker) == 7 and ticker.startswith("A")) else ticker
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": clean_ticker
            }
            res = self._request("GET", "/uapi/domestic-stock/v1/quotations/inquire-price", tr_id="FHKST01010100", params=params)
            out = res.get("output") or {}
            price = float(out.get("stck_prpr") or 0)
            self._logger.debug("getPrice() %s -> %.6g (from FHKST01010100).", ticker, price)
            return price

    def getBook(self, ticker, asset_type=None):
        """
        Retrieves the orderbook for a stock or derivatives contract.
        Supports KR Equities (10-step), KR Futures/Options (5-step), and Overseas US Equities (10-step).

        Args:
            ticker (str): Ticker symbol (e.g., "005930", "101TC350", "B11611094", "AAPL").
            asset_type (str, optional): Explicit asset class ("KR", "FO", "US").

        Returns:
            dict: Dict of bids/asks prices and quantities, sorted by nearest to farthest:
                  - bids_p: descending (highest bid nearest)
                  - asks_p: ascending (lowest ask nearest)
        """
        self._logger.debug("getBook() %s.", ticker)
        asset = self._classify_ticker(ticker, asset_type)
        if asset == "FO":
            # KR Futures/Options orderbook via /uapi/domestic-futureoption/v1/quotations/inquire-asking-price
            # TR ID: FHMIF10010000 (5-step bid/ask)
            # FID_COND_MRKT_DIV_CODE:
            #   - Stock Options (개별주식옵션, e.g. B11611094): 'JO' (Day only, no night session)
            #   - Stock Futures (개별주식선물): 'JF' (Day only, no night session)
            #   - Index Options: Day 'O' / Night 'EU'
            #   - Index Futures: Day 'F' / Night 'CM'
            is_night = self._is_night()
            is_opt = self._is_option_ticker(ticker)
            is_stock_opt = self._is_stock_option(ticker)
            is_stock_fut = self._is_stock_future(ticker)
            mrkt_div = self._resolve_fo_market_div(ticker)
            params = {
                "FID_COND_MRKT_DIV_CODE": mrkt_div,
                "FID_INPUT_ISCD": ticker
            }
            try:
                res = self._request("GET", "/uapi/domestic-futureoption/v1/quotations/inquire-asking-price", tr_id="FHMIF10010000", params=params)
            except Exception as e:
                if is_night and not (is_stock_opt or is_stock_fut):
                    fallback_div = "O" if is_opt else "F"
                    self._logger.debug("Night orderbook query failed for %s (mrkt=%s): %s; trying day division %s.", ticker, mrkt_div, e, fallback_div)
                    params["FID_COND_MRKT_DIV_CODE"] = fallback_div
                    res = self._request("GET", "/uapi/domestic-futureoption/v1/quotations/inquire-asking-price", tr_id="FHMIF10010000", params=params)
                else:
                    raise

            out = res.get("output2") or {}

            bids_p = []
            bids_n = []
            asks_p = []
            asks_n = []

            for i in range(1, 6):
                ap = float(out.get(f"futs_askp{i}") or out.get(f"optn_askp{i}") or out.get(f"askp{i}") or 0)
                av = float(out.get(f"askp_rsqn{i}") or out.get(f"optn_askp_rsqn{i}") or out.get(f"askp_csgn{i}") or 0)
                if ap > 0:
                    asks_p.append(ap)
                    asks_n.append(av)

                bp = float(out.get(f"futs_bidp{i}") or out.get(f"optn_bidp{i}") or out.get(f"bidp{i}") or 0)
                bv = float(out.get(f"bidp_rsqn{i}") or out.get(f"optn_bidp_rsqn{i}") or out.get(f"bidp_csgn{i}") or 0)
                if bp > 0:
                    bids_p.append(bp)
                    bids_n.append(bv)

            self._logger.debug("getBook() FO %s (mrkt=%s, night=%s) bids=%d  asks=%d.", ticker, mrkt_div, is_night, len(bids_p), len(asks_p))
            return {
                "bids_p": bids_p,
                "bids_n": bids_n,
                "asks_p": asks_p,
                "asks_n": asks_n
            }

        elif asset == "US":
            # Overseas US stock orderbook via /uapi/overseas-price/v1/quotations/inquire-asking-price
            # TR ID: HHDFS76200100 (10-step bid/ask)
            out = {}
            for excd in ("NAS", "NYS", "AMS"):
                try:
                    params = {
                        "AUTH": "",
                        "EXCD": excd,
                        "SYMB": ticker
                    }
                    res = self._request("GET", "/uapi/overseas-price/v1/quotations/inquire-asking-price", tr_id="HHDFS76200100", params=params)
                    temp_out = res.get("output2") or {}
                    if temp_out.get("pask1") or temp_out.get("pbid1"):
                        out = temp_out
                        break
                except Exception as e:
                    self._logger.debug("HHDFS76200100 getBook failed for %s (excd=%s): %s", ticker, excd, e)

            bids_p = []
            bids_n = []
            asks_p = []
            asks_n = []

            for i in range(1, 11):
                ap = float(out.get(f"pask{i}") or 0)
                av = float(out.get(f"vask{i}") or 0)
                if ap > 0:
                    asks_p.append(ap)
                    asks_n.append(av)

                bp = float(out.get(f"pbid{i}") or 0)
                bv = float(out.get(f"vbid{i}") or 0)
                if bp > 0:
                    bids_p.append(bp)
                    bids_n.append(bv)

            # Fallback to single last price if orderbook levels are empty
            if not bids_p and not asks_p:
                last_p = self.getPrice(ticker, asset_type="US")
                if last_p > 0:
                    bids_p = [last_p]
                    bids_n = [1.0]
                    asks_p = [last_p]
                    asks_n = [1.0]

            self._logger.debug("getBook() US %s  bids=%d  asks=%d.", ticker, len(bids_p), len(asks_p))
            return {
                "bids_p": bids_p,
                "bids_n": bids_n,
                "asks_p": asks_p,
                "asks_n": asks_n
            }

        else:
            # KR domestic stock orderbook via /uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn
            # TR ID: FHKST01010200 (10-step bid/ask)
            clean_ticker = ticker[1:] if (len(ticker) == 7 and ticker.startswith("A")) else ticker
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": clean_ticker
            }
            res = self._request("GET", "/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn", tr_id="FHKST01010200", params=params)
            out = res.get("output1") or {}

            bids_p = []
            bids_n = []
            asks_p = []
            asks_n = []

            for i in range(1, 11):
                ap = float(out.get(f"askp{i}") or 0)
                av = float(out.get(f"askp_rsqn{i}") or 0)
                if ap > 0:
                    asks_p.append(ap)
                    asks_n.append(av)

                bp = float(out.get(f"bidp{i}") or 0)
                bv = float(out.get(f"bidp_rsqn{i}") or 0)
                if bp > 0:
                    bids_p.append(bp)
                    bids_n.append(bv)

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
            ticker (str): Stock or contract ticker (e.g. "005930", "101TC350", "AAPL").
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
            is_night = self._is_night()
            is_opt = self._is_option_ticker(ticker)
            is_stock_opt = self._is_stock_option(ticker)
            is_stock_fut = self._is_stock_future(ticker)
            mrkt_div = self._resolve_fo_market_div(ticker)

            if timeframe == "1m":
                # Minute chart via /uapi/domestic-futureoption/v1/quotations/inquire-time-fuopchartprice
                # TR ID: FHKIF03020200
                hour_str = to_dt.strftime("%H%M%S") if isinstance(to_dt, datetime.datetime) else "154500"
                date_str = to_dt.strftime("%Y%m%d")
                params = {
                    "FID_COND_MRKT_DIV_CODE": mrkt_div,
                    "FID_INPUT_ISCD": ticker,
                    "FID_HOUR_CLS_CODE": "1",
                    "FID_PW_DATA_INCU_YN": "Y",
                    "FID_FAKE_TICK_INCU_YN": "N",
                    "FID_INPUT_DATE_1": date_str,
                    "FID_INPUT_HOUR_1": hour_str
                }
                try:
                    res = self._request("GET", "/uapi/domestic-futureoption/v1/quotations/inquire-time-fuopchartprice", tr_id="FHKIF03020200", params=params)
                except Exception as e:
                    if is_night and not (is_stock_opt or is_stock_fut):
                        fallback_div = "O" if is_opt else "F"
                        self._logger.debug("Night 1m chart failed for %s (mrkt=%s): %s; trying day division %s.", ticker, mrkt_div, e, fallback_div)
                        params["FID_COND_MRKT_DIV_CODE"] = fallback_div
                        res = self._request("GET", "/uapi/domestic-futureoption/v1/quotations/inquire-time-fuopchartprice", tr_id="FHKIF03020200", params=params)
                    else:
                        raise

                candles = res.get("Output2") or res.get("output2") or []
                for c in candles:
                    d_str = str(c.get("stck_bsop_date") or "").strip()
                    t_str = str(c.get("stck_cntg_hour") or "").strip().zfill(6)
                    if not d_str:
                        continue
                    try:
                        dt = datetime.datetime.strptime(f"{d_str}{t_str}", "%Y%m%d%H%M%S")
                    except ValueError:
                        dt = datetime.datetime.strptime(d_str, "%Y%m%d")

                    parsed_candles.append({
                        "t": dt,
                        "o": float(c.get("futs_oprc") or c.get("optn_oprc") or 0),
                        "h": float(c.get("futs_hgpr") or c.get("optn_hgpr") or 0),
                        "l": float(c.get("futs_lwpr") or c.get("optn_lwpr") or 0),
                        "c": float(c.get("futs_prpr") or c.get("optn_prpr") or 0),
                        "v": float(c.get("cntg_vol") or c.get("acml_vol") or 0)
                    })
            else:
                # Daily chart via /uapi/domestic-futureoption/v1/quotations/inquire-daily-fuopchartprice
                # TR ID: FHKIF03020100
                edate = to_dt.strftime("%Y%m%d")
                sdate = (to_dt - datetime.timedelta(days=730)).strftime("%Y%m%d")
                params = {
                    "FID_COND_MRKT_DIV_CODE": mrkt_div,
                    "FID_INPUT_ISCD": ticker,
                    "FID_INPUT_DATE_1": sdate,
                    "FID_INPUT_DATE_2": edate,
                    "FID_PERIOD_DIV_CODE": "D"
                }
                try:
                    res = self._request("GET", "/uapi/domestic-futureoption/v1/quotations/inquire-daily-fuopchartprice", tr_id="FHKIF03020100", params=params)
                except Exception as e:
                    if is_night and not (is_stock_opt or is_stock_fut):
                        fallback_div = "O" if is_opt else "F"
                        self._logger.debug("Night daily chart failed for %s (mrkt=%s): %s; trying day division %s.", ticker, mrkt_div, e, fallback_div)
                        params["FID_COND_MRKT_DIV_CODE"] = fallback_div
                        res = self._request("GET", "/uapi/domestic-futureoption/v1/quotations/inquire-daily-fuopchartprice", tr_id="FHKIF03020100", params=params)
                    else:
                        raise

                candles = res.get("output2") or []
                for c in candles:
                    d_str = str(c.get("stck_bsop_date") or c.get("-stck_bsop_date") or "").strip()
                    if not d_str:
                        continue
                    dt = datetime.datetime.strptime(d_str, "%Y%m%d")
                    parsed_candles.append({
                        "t": dt,
                        "o": float(c.get("futs_oprc") or c.get("optn_oprc") or c.get("-futs_oprc") or 0),
                        "h": float(c.get("futs_hgpr") or c.get("optn_hgpr") or c.get("-futs_hgpr") or 0),
                        "l": float(c.get("futs_lwpr") or c.get("optn_lwpr") or c.get("-futs_lwpr") or 0),
                        "c": float(c.get("futs_prpr") or c.get("optn_prpr") or c.get("-futs_prpr") or 0),
                        "v": float(c.get("acml_vol") or c.get("-acml_vol") or 0)
                    })

        elif asset == "US":
            # Overseas US stock chart
            if timeframe == "1m":
                # Minute chart via /uapi/overseas-price/v1/quotations/inquire-time-itemchartprice
                # TR ID: HHDFS76950200
                candles = []
                for excd in ("NAS", "NYS", "AMS"):
                    try:
                        params = {
                            "AUTH": "",
                            "EXCD": excd,
                            "SYMB": ticker,
                            "NMIN": "1",
                            "PINC": "1",
                            "NEXT": "",
                            "NREC": "120",
                            "FILL": "",
                            "KEYB": ""
                        }
                        res = self._request("GET", "/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice", tr_id="HHDFS76950200", params=params)
                        temp_candles = res.get("output2") or []
                        if temp_candles:
                            candles = temp_candles
                            break
                    except Exception as e:
                        self._logger.debug("HHDFS76950200 failed for %s (excd=%s): %s", ticker, excd, e)

                for c in candles:
                    d_str = str(c.get("kymd") or c.get("tymd") or c.get("xymd") or "").strip()
                    t_str = str(c.get("khms") or c.get("xhms") or "").strip().zfill(6)
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
                        "c": float(c.get("last") or c.get("clos") or 0),
                        "v": float(c.get("evol") or c.get("tvol") or 0)
                    })
            else:
                # Daily chart via /uapi/overseas-price/v1/quotations/dailyprice
                # TR ID: HHDFS76240000
                candles = []
                bymd = to_dt.strftime("%Y%m%d")
                modp = "1" if adjusted else "0"
                for excd in ("NAS", "NYS", "AMS"):
                    try:
                        params = {
                            "AUTH": "",
                            "EXCD": excd,
                            "SYMB": ticker,
                            "GUBN": "0",  # 0: 일, 1: 주, 2: 월
                            "BYMD": bymd,
                            "MODP": modp,
                            "KEYB": ""
                        }
                        res = self._request("GET", "/uapi/overseas-price/v1/quotations/dailyprice", tr_id="HHDFS76240000", params=params)
                        temp_candles = res.get("output2") or []
                        if temp_candles:
                            candles = temp_candles
                            break
                    except Exception as e:
                        self._logger.debug("HHDFS76240000 failed for %s (excd=%s): %s", ticker, excd, e)

                for c in candles:
                    d_str = str(c.get("xymd") or "").strip()
                    if not d_str:
                        continue
                    dt = datetime.datetime.strptime(d_str, "%Y%m%d")
                    parsed_candles.append({
                        "t": dt,
                        "o": float(c.get("open") or 0),
                        "h": float(c.get("high") or 0),
                        "l": float(c.get("low") or 0),
                        "c": float(c.get("clos") or 0),
                        "v": float(c.get("tvol") or 0)
                    })

        else:
            # KR domestic stock chart
            clean_ticker = ticker[1:] if (len(ticker) == 7 and ticker.startswith("A")) else ticker
            if timeframe == "1m":
                # Minute chart via /uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice
                # TR ID: FHKST03010200
                hour_str = to_dt.strftime("%H%M%S") if isinstance(to_dt, datetime.datetime) else "153000"
                params = {
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": clean_ticker,
                    "FID_INPUT_HOUR_1": hour_str,
                    "FID_PW_DATA_INCU_YN": "Y",
                    "FID_ETC_CLS_CODE": ""
                }
                res = self._request("GET", "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice", tr_id="FHKST03010200", params=params)
                candles = res.get("output2") or []
                for c in candles:
                    d_str = str(c.get("stck_bsop_date") or "").strip()
                    t_str = str(c.get("stck_cntg_hour") or "").strip().zfill(6)
                    if not d_str:
                        continue
                    try:
                        dt = datetime.datetime.strptime(f"{d_str}{t_str}", "%Y%m%d%H%M%S")
                    except ValueError:
                        dt = datetime.datetime.strptime(d_str, "%Y%m%d")

                    parsed_candles.append({
                        "t": dt,
                        "o": float(c.get("stck_oprc") or 0),
                        "h": float(c.get("stck_hgpr") or 0),
                        "l": float(c.get("stck_lwpr") or 0),
                        "c": float(c.get("stck_prpr") or 0),
                        "v": float(c.get("cntg_vol") or 0)
                    })
            else:
                # Daily chart via /uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice
                # TR ID: FHKST03010100
                edate = to_dt.strftime("%Y%m%d")
                sdate = (to_dt - datetime.timedelta(days=730)).strftime("%Y%m%d")
                org_adj = "0" if adjusted else "1"  # 0: 수정주가, 1: 원주가
                params = {
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": clean_ticker,
                    "FID_INPUT_DATE_1": sdate,
                    "FID_INPUT_DATE_2": edate,
                    "FID_PERIOD_DIV_CODE": "D",
                    "FID_ORG_ADJ_PRC": org_adj
                }
                res = self._request("GET", "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", tr_id="FHKST03010100", params=params)
                candles = res.get("output2") or []
                for c in candles:
                    d_str = str(c.get("stck_bsop_date") or "").strip()
                    if not d_str:
                        continue
                    dt = datetime.datetime.strptime(d_str, "%Y%m%d")
                    parsed_candles.append({
                        "t": dt,
                        "o": float(c.get("stck_oprc") or 0),
                        "h": float(c.get("stck_hgpr") or 0),
                        "l": float(c.get("stck_lwpr") or 0),
                        "c": float(c.get("stck_clpr") or 0),
                        "v": float(c.get("acml_vol") or 0)
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
                        "101TC350": {"exchange": "KR_FO", "quantity": 1, "price": 944.8},
                        "AAPL": {"exchange": "US", "quantity": 5, "price": 220.5}}
        """
        self._logger.debug("getHoldings() called.")
        result = {}
        cano, prdt = self._split_account()

        # 1. Domestic stock holdings via /uapi/domestic-stock/v1/trading/inquire-balance
        # TR ID: Real TTTC8434R / Virtual VTTC8434R
        try:
            tr_id = "VTTC8434R" if self.is_virtual else "TTTC8434R"
            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": ""
            }
            res = self._request("GET", "/uapi/domestic-stock/v1/trading/inquire-balance", tr_id=tr_id, params=params)
            items = res.get("output1") or []
            for item in items:
                symbol = str(item.get("pdno") or "").strip()
                if not symbol:
                    continue
                qty = float(item.get("hldg_qty") or 0)
                price = float(item.get("pchs_avg_pric") or item.get("prpr") or 0)
                if qty > 0:
                    result[symbol] = {
                        "exchange": "KR",
                        "quantity": qty,
                        "price": price
                    }
        except Exception as e:
            self._logger.debug("getHoldings() error fetching domestic positions: %s", e)

        # 2. Futures & Options holdings
        # Day: /uapi/domestic-futureoption/v1/trading/inquire-balance (Real CTFO6118R / Virtual VTFO6118R)
        # Night: /uapi/domestic-futureoption/v1/trading/inquire-ngt-balance (Real CTFN6118R / Virtual VTFO6118R)
        try:
            is_night = self._is_night()
            if is_night:
                path = "/uapi/domestic-futureoption/v1/trading/inquire-ngt-balance"
                tr_id = "VTFO6118R" if self.is_virtual else "CTFN6118R"
            else:
                path = "/uapi/domestic-futureoption/v1/trading/inquire-balance"
                tr_id = "VTFO6118R" if self.is_virtual else "CTFO6118R"

            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "MGNA_DVSN": "01",
                "EXCC_STAT_CD": "0",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": ""
            }
            try:
                res = self._request("GET", path, tr_id=tr_id, params=params)
            except Exception as e:
                if is_night and not self.is_virtual:
                    self._logger.debug("Night FO balance query (%s) failed: %s; falling back to day endpoint.", tr_id, e)
                    path = "/uapi/domestic-futureoption/v1/trading/inquire-balance"
                    tr_id = "CTFO6118R"
                    res = self._request("GET", path, tr_id=tr_id, params=params)
                else:
                    raise

            items = res.get("output1") or []
            for item in items:
                symbol = str(item.get("pdno") or item.get("shtn_pdno") or "").strip()
                if not symbol:
                    continue
                qty = float(item.get("cblc_qty") or 0)
                price = float(item.get("ccld_avg_unpr1") or item.get("excc_unpr") or 0)
                if qty > 0:
                    result[symbol] = {
                        "exchange": "KR_FO",
                        "quantity": qty,
                        "price": price
                    }
        except Exception as e:
            self._logger.debug("getHoldings() error fetching futures/options positions: %s", e)

        # 3. Overseas holdings via /uapi/overseas-stock/v1/trading/inquire-balance
        # TR ID: Real TTTS3012R / Virtual VTTS3012R
        try:
            tr_id = "VTTS3012R" if self.is_virtual else "TTTS3012R"
            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "OVRS_EXCG_CD": "%",
                "TR_CRCY_CD": "USD",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": ""
            }
            res = self._request("GET", "/uapi/overseas-stock/v1/trading/inquire-balance", tr_id=tr_id, params=params)
            items = res.get("output1") or []
            for item in items:
                symbol = str(item.get("ovrs_pdno") or "").strip()
                if not symbol:
                    continue
                qty = float(item.get("ovrs_cblc_qty") or 0)
                price = float(item.get("pchs_avg_pric") or item.get("now_pric2") or 0)
                if qty > 0:
                    result[symbol] = {
                        "exchange": "US",
                        "quantity": qty,
                        "price": price
                    }
        except Exception as e:
            self._logger.debug("getHoldings() error fetching overseas positions: %s", e)

        self._logger.debug("getHoldings() returned %d position(s).", len(result))
        return result

    def getKrwDeposit(self):
        """
        Retrieves the available KRW cash buying power in the account.

        Returns:
            float: KRW amount available for purchase.
        """
        self._logger.debug("getKrwDeposit() called.")
        cano, prdt = self._split_account()

        # 1. /uapi/domestic-stock/v1/trading/inquire-psbl-order (TR: TTTC8908R / VTTC8908R)
        try:
            tr_id = "VTTC8908R" if self.is_virtual else "TTTC8908R"
            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "PDNO": "005930",
                "ORD_UNPR": "0",
                "ORD_DVSN": "01",
                "CMA_EVLU_AMT_ICLD_YN": "N",
                "OVRS_ICLD_YN": "N"
            }
            res = self._request("GET", "/uapi/domestic-stock/v1/trading/inquire-psbl-order", tr_id=tr_id, params=params)
            out = res.get("output") or {}
            amount = float(out.get("ord_psbl_cash") or 0)
            if amount >= 0:
                self._logger.debug("getKrwDeposit() -> %.0f KRW (from inquire-psbl-order).", amount)
                return amount
        except Exception as e:
            self._logger.debug("inquire-psbl-order failed: %s; trying inquire-balance.", e)

        # 2. Fallback to /uapi/domestic-stock/v1/trading/inquire-balance (output2.dnca_tot_amt)
        try:
            tr_id = "VTTC8434R" if self.is_virtual else "TTTC8434R"
            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": ""
            }
            res = self._request("GET", "/uapi/domestic-stock/v1/trading/inquire-balance", tr_id=tr_id, params=params)
            out2 = res.get("output2")
            if isinstance(out2, list) and out2:
                out2 = out2[0]
            elif not isinstance(out2, dict):
                out2 = {}
            amount = float(out2.get("dnca_tot_amt") or out2.get("prvs_rcdl_excc_amt") or 0)
            self._logger.debug("getKrwDeposit() -> %.0f KRW (from inquire-balance).", amount)
            return amount
        except Exception as e:
            self._logger.debug("inquire-balance deposit query failed: %s; checking futureoption deposit.", e)

        # 3. Fallback to Futures/Options /uapi/domestic-futureoption/v1/trading/inquire-deposit (TR: CTRP6550R)
        try:
            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt
            }
            res = self._request("GET", "/uapi/domestic-futureoption/v1/trading/inquire-deposit", tr_id="CTRP6550R", params=params)
            out = res.get("output") or {}
            amount = float(out.get("ord_psbl_cash") or out.get("ord_psbl_tota") or out.get("dnca_tota") or 0)
            self._logger.debug("getKrwDeposit() -> %.0f KRW (from CTRP6550R).", amount)
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
        cano, prdt = self._split_account()

        # 1. /uapi/overseas-stock/v1/trading/inquire-psamount (TR: TTTS3007R / VTTS3007R)
        try:
            tr_id = "VTTS3007R" if self.is_virtual else "TTTS3007R"
            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "OVRS_EXCG_CD": "NASD",
                "OVRS_ORD_UNPR": "0",
                "ITEM_CD": "AAPL"
            }
            res = self._request("GET", "/uapi/overseas-stock/v1/trading/inquire-psamount", tr_id=tr_id, params=params)
            out = res.get("output") or {}
            amount = float(out.get("ord_psbl_frcr_amt") or out.get("ovrs_ord_psbl_amt") or 0)
            self._logger.debug("getUsdDeposit() -> %.4f USD (from inquire-psamount).", amount)
            return amount
        except Exception as e:
            self._logger.debug("inquire-psamount failed: %s; trying overseas inquire-balance.", e)

        # 2. Fallback to /uapi/overseas-stock/v1/trading/inquire-balance (output2.frcr_dncl_amt_2)
        try:
            tr_id = "VTTS3012R" if self.is_virtual else "TTTS3012R"
            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": prdt,
                "OVRS_EXCG_CD": "%",
                "TR_CRCY_CD": "USD",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": ""
            }
            res = self._request("GET", "/uapi/overseas-stock/v1/trading/inquire-balance", tr_id=tr_id, params=params)
            out2 = res.get("output2")
            if isinstance(out2, list) and out2:
                out2 = out2[0]
            elif not isinstance(out2, dict):
                out2 = {}
            amount = float(out2.get("frcr_dncl_amt_2") or 0)
            self._logger.debug("getUsdDeposit() -> %.4f USD (from inquire-balance).", amount)
            return amount
        except Exception as e:
            self._logger.debug("overseas inquire-balance deposit check failed: %s", e)

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

    # ------------------------------------------------------------------
    # Option master / underlyings and expirations
    # ------------------------------------------------------------------

    def _load_master_data(self):
        """
        Loads and parses option master files (fo_idx_code_mts, fo_stk_code_mts) from
        Korea Investment & Securities CDN. Caches the parsed data for the current date.
        """
        today = datetime.date.today().strftime("%Y%m%d")
        if self._master_cache and self._master_cache_date == today:
            return self._master_cache

        self._logger.debug("Downloading and caching option master files from KIS CDN.")
        data = {
            "underlyings": [],
            "underlying_map": {},
            "contracts_by_underlying": {}
        }

        # 1. Index options (fo_idx_code_mts.mst.zip)
        idx_url = "https://new.real.download.dws.co.kr/common/master/fo_idx_code_mts.mst.zip"
        try:
            req = urllib.request.Request(idx_url, headers={"User-Agent": "Mozilla/5.0"})
            content = urllib.request.urlopen(req, timeout=10).read()
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                raw = z.read(z.namelist()[0]).decode("cp949", errors="ignore")
                for line in raw.splitlines():
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 9:
                        ptype, code, std_code, name, atm, strike, month, u_code, u_name = parts[:9]
                        if ptype in ("5", "6", "D", "E", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S"):
                            canonical_code = u_name if u_name in ("KOSPI200", "KSQ150") else u_code
                            if canonical_code not in data["contracts_by_underlying"]:
                                data["contracts_by_underlying"][canonical_code] = []
                                data["underlyings"].append({
                                    "code": canonical_code,
                                    "name": u_name,
                                    "type": "INDEX"
                                })
                                data["underlying_map"][canonical_code.upper()] = canonical_code
                                data["underlying_map"][u_code.upper()] = canonical_code
                                data["underlying_map"][u_name.upper()] = canonical_code
                                if canonical_code == "KOSPI200":
                                    data["underlying_map"]["코스피200"] = canonical_code
                                elif canonical_code == "KSQ150":
                                    data["underlying_map"]["코스닥150"] = canonical_code

                            data["contracts_by_underlying"][canonical_code].append({
                                "ptype": ptype,
                                "code": code,
                                "std_code": std_code,
                                "name": name,
                                "strike": strike
                            })
        except Exception as e:
            self._logger.warning("Failed to load index options master file: %s", e)

        # 2. Stock options (fo_stk_code_mts.mst.zip)
        stk_url = "https://new.real.download.dws.co.kr/common/master/fo_stk_code_mts.mst.zip"
        try:
            req = urllib.request.Request(stk_url, headers={"User-Agent": "Mozilla/5.0"})
            content = urllib.request.urlopen(req, timeout=10).read()
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                raw = z.read(z.namelist()[0]).decode("cp949", errors="ignore")
                for line in raw.splitlines():
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 9:
                        ptype, code, std_code, name, atm, strike, month, u_code, u_name = parts[:9]
                        if ptype in ("5", "6"):
                            clean_u_code = u_code[1:] if (len(u_code) == 7 and u_code.startswith("A")) else u_code
                            if clean_u_code not in data["contracts_by_underlying"]:
                                data["contracts_by_underlying"][clean_u_code] = []
                                data["underlyings"].append({
                                    "code": clean_u_code,
                                    "name": u_name,
                                    "type": "STOCK"
                                })
                                data["underlying_map"][clean_u_code] = clean_u_code
                                data["underlying_map"][f"A{clean_u_code}"] = clean_u_code
                                data["underlying_map"][u_name] = clean_u_code

                            data["contracts_by_underlying"][clean_u_code].append({
                                "ptype": ptype,
                                "code": code,
                                "std_code": std_code,
                                "name": name,
                                "strike": strike
                            })
        except Exception as e:
            self._logger.warning("Failed to load stock options master file: %s", e)

        self._master_cache = data
        self._master_cache_date = today
        return data

    def getOptionUnderlyings(self, include_name=False):
        """
        Retrieves the list of tradeable option underlying assets (지수옵션 및 개별주식옵션 기초자산 목록).

        Args:
            include_name (bool, optional): If True, returns a list of dicts with 'code' and 'name'.
                                          If False (default), returns a list of string symbols.
                                          e.g. ["KOSPI200", "KSQ150", "005930", "000660", ...]

        Returns:
            list: List of underlying asset symbols or dicts.
        """
        self._logger.debug("getOptionUnderlyings() called (include_name=%s).", include_name)
        data = self._load_master_data()
        underlyings = data["underlyings"]

        # Sort so index options appear first, then stock options in alphabetical/numerical order
        sorted_items = sorted(underlyings, key=lambda x: (0 if x["type"] == "INDEX" else 1, x["code"]))

        if include_name:
            return [{"code": item["code"], "name": item["name"]} for item in sorted_items]
        return [item["code"] for item in sorted_items]

    def getExpirations(self, ticker):
        """
        Retrieves available expiration dates for options on the specified underlying asset.
        Supports index options (e.g. "KOSPI200", "KSQ150") including weekly options,
        as well as individual stock options (e.g. "005930", "삼성전자").

        Args:
            ticker (str): Underlying asset symbol, code, or name (e.g. "KOSPI200", "005930", "삼성전자").

        Returns:
            list: Sorted list of expiration date strings in "YYYY-MM-DD" format.
                  e.g. ["2026-10-19", "2026-10-22", "2026-11-12", "2026-12-10", ...]
        """
        self._logger.debug("getExpirations() called for ticker=%s.", ticker)
        data = self._load_master_data()
        clean_input = str(ticker).strip()
        canonical_key = data["underlying_map"].get(clean_input) or data["underlying_map"].get(clean_input.upper())

        if not canonical_key:
            if len(clean_input) == 7 and clean_input.startswith("A"):
                canonical_key = data["underlying_map"].get(clean_input[1:])

        if not canonical_key or canonical_key not in data["contracts_by_underlying"]:
            self._logger.warning("No options found for underlying ticker: %s", ticker)
            return []

        contracts = data["contracts_by_underlying"][canonical_key]
        expirations = set()

        for c in contracts:
            exp_date = self._get_contract_expiration(c["name"])
            if exp_date:
                expirations.add(exp_date)

        sorted_expirations = sorted(list(expirations))
        self._logger.debug("getExpirations(%s) -> %d expiration(s): %s", ticker, len(sorted_expirations), sorted_expirations)
        return sorted_expirations

    def _get_contract_expiration(self, name):
        """
        Extracts the expiration date string ('YYYY-MM-DD') from an option contract name.
        Supports both weekly and monthly index and stock options.
        """
        # 1. Weekly pattern: e.g. "위클리C 2610W3", "위클리M C 2610W3", "코스닥위클리C 2610W3"
        m_week = re.search(r'위클리(M)?\s*[CP]\s*(\d{2})(\d{2})W(\d)', name)
        if m_week:
            is_mon = bool(m_week.group(1))
            yy = 2000 + int(m_week.group(2))
            mm = int(m_week.group(3))
            w = int(m_week.group(4))

            mondays = [
                d for d in range(1, calendar.monthrange(yy, mm)[1] + 1)
                if datetime.date(yy, mm, d).weekday() == 0
            ]
            if w <= len(mondays):
                mon_dt = datetime.date(yy, mm, mondays[w - 1])
            else:
                mon_dt = datetime.date(yy, mm, mondays[-1]) + datetime.timedelta(weeks=w - len(mondays))

            if is_mon:
                return mon_dt.strftime("%Y-%m-%d")
            else:
                thu_dt = mon_dt + datetime.timedelta(days=3)
                return thu_dt.strftime("%Y-%m-%d")

        # 2. Monthly pattern: e.g. "C 202611", "미니C 202611", "삼성전자 C 202611"
        m_month = re.search(r'[CP]\s*(\d{4})(\d{2})', name)
        if m_month:
            yy = int(m_month.group(1))
            mm = int(m_month.group(2))
            thursdays = [
                d for d in range(1, calendar.monthrange(yy, mm)[1] + 1)
                if datetime.date(yy, mm, d).weekday() == 3
            ]
            if len(thursdays) >= 2:
                thu2_dt = datetime.date(yy, mm, thursdays[1])
            else:
                thu2_dt = datetime.date(yy, mm, thursdays[0])
            return thu2_dt.strftime("%Y-%m-%d")

        return None

    def getOptionChain(self, underlying, expiration, fetch_quotes=False):
        """
        Retrieves the option chain (전광판) for a given underlying asset and expiration date.

        Args:
            underlying (str): Underlying asset code or symbol (e.g. "KOSPI200", "005930", "KSQ150").
            expiration (str or date): Expiration date string in "YYYY-MM-DD" or "YYYYMMDD" format,
                                      as returned by getExpirations().
            fetch_quotes (bool, optional): If True and display-board API is unavailable,
                                          fetches individual orderbook quotes for each strike.
                                          Defaults to False (returns master strikes with 0 quotes).

        Returns:
            dict: Dictionary with 'calls' and 'puts' lists, sorted by strike price ascending:
                  {
                      "calls": [
                          {"code": "BAFC2W822", "strike": 822.5, "bid": 0, "ask": 0, "bid_n": 0, "ask_n": 0},
                          ...
                      ],
                      "puts": [
                          {"code": "CAFC2W822", "strike": 822.5, "bid": 0, "ask": 0, "bid_n": 0, "ask_n": 0},
                          ...
                      ]
                  }
        """
        self._logger.debug("getOptionChain() called: underlying=%s, expiration=%s.", underlying, expiration)
        data = self._load_master_data()
        clean_input = str(underlying).strip()
        canonical_key = data["underlying_map"].get(clean_input) or data["underlying_map"].get(clean_input.upper())
        if not canonical_key and len(clean_input) == 7 and clean_input.startswith("A"):
            canonical_key = data["underlying_map"].get(clean_input[1:])

        if not canonical_key or canonical_key not in data["contracts_by_underlying"]:
            self._logger.warning("getOptionChain(): No options found for underlying: %s", underlying)
            return {"calls": [], "puts": []}

        # Normalize expiration date to YYYY-MM-DD
        if isinstance(expiration, (datetime.date, datetime.datetime)):
            exp_str = expiration.strftime("%Y-%m-%d")
        else:
            exp_str = str(expiration).strip().replace("/", "-")
            if len(exp_str) == 8 and exp_str.isdigit():
                exp_str = f"{exp_str[:4]}-{exp_str[4:6]}-{exp_str[6:8]}"

        contracts = data["contracts_by_underlying"][canonical_key]
        matching_contracts = [c for c in contracts if self._get_contract_expiration(c["name"]) == exp_str]

        if not matching_contracts:
            self._logger.warning(
                "getOptionChain(): No contracts found for underlying %s on expiration %s.",
                underlying, exp_str
            )
            return {"calls": [], "puts": []}

        # If standard monthly options (ptype '5'/'6') exist for this date, prioritize over mini ('D'/'E')
        has_standard = any(c["ptype"] in ("5", "6") for c in matching_contracts)
        if has_standard:
            matching_contracts = [c for c in matching_contracts if c["ptype"] in ("5", "6")]

        calls = []
        puts = []
        call_map = {}
        put_map = {}

        for c in matching_contracts:
            strike_num = float(c["strike"])
            strike_val = int(strike_num) if strike_num.is_integer() else strike_num
            code = c["code"]
            is_call = c["ptype"] in ("5", "D", "L", "N") or (" C " in c["name"] or c["name"].startswith("C "))

            item = {
                "code": code,
                "strike": strike_val,
                "bid": 0,
                "ask": 0,
                "bid_n": 0,
                "ask_n": 0
            }

            if is_call:
                calls.append(item)
                call_map[code] = item
                call_map[strike_val] = item
            else:
                puts.append(item)
                put_map[code] = item
                put_map[strike_val] = item

        # Sort by strike ascending
        calls.sort(key=lambda x: x["strike"])
        puts.sort(key=lambda x: x["strike"])

        # Attempt to populate quotes from KIS display-board API
        try:
            mrkt_div = "U" if canonical_key in ("KOSPI200", "KSQ150") else "J"
            input_iscd = "0001" if canonical_key == "KOSPI200" else ("1001" if canonical_key == "KSQ150" else canonical_key)
            params = {
                "FID_COND_MRKT_DIV_CODE": mrkt_div,
                "FID_INPUT_ISCD": input_iscd,
                "FID_INPUT_DATE_1": exp_str.replace("-", "")
            }
            res = self._request("GET", "/uapi/domestic-futureoption/v1/quotations/display-board-callput", tr_id="FHPIF05030100", params=params)
            rows = res.get("output") or res.get("output1") or res.get("output2") or []
            if isinstance(rows, list):
                for r in rows:
                    c_code = str(r.get("call_shrn_iscd") or r.get("call_iscd") or r.get("call_code") or "").strip()
                    p_code = str(r.get("put_shrn_iscd") or r.get("put_iscd") or r.get("put_code") or "").strip()
                    strike_r = float(r.get("actp") or r.get("strike_price") or 0)
                    strike_k = int(strike_r) if strike_r.is_integer() else strike_r

                    c_target = call_map.get(c_code) or call_map.get(strike_k)
                    if c_target:
                        c_target["bid"] = float(r.get("call_bidp") or r.get("call_bid") or 0)
                        c_target["ask"] = float(r.get("call_askp") or r.get("call_ask") or 0)
                        c_target["bid_n"] = int(float(r.get("call_bidp_rsqn") or r.get("call_bid_qty") or 0))
                        c_target["ask_n"] = int(float(r.get("call_askp_rsqn") or r.get("call_ask_qty") or 0))

                    p_target = put_map.get(p_code) or put_map.get(strike_k)
                    if p_target:
                        p_target["bid"] = float(r.get("put_bidp") or r.get("put_bid") or 0)
                        p_target["ask"] = float(r.get("put_askp") or r.get("put_ask") or 0)
                        p_target["bid_n"] = int(float(r.get("put_bidp_rsqn") or r.get("put_bid_qty") or 0))
                        p_target["ask_n"] = int(float(r.get("put_askp_rsqn") or r.get("put_ask_qty") or 0))
        except Exception as e:
            self._logger.debug("display-board-callput query failed or not supported: %s", e)
            if fetch_quotes:
                for item in calls:
                    try:
                        bk = self.getBook(item["code"])
                        if bk["bids_p"]:
                            item["bid"] = bk["bids_p"][0]
                            item["bid_n"] = int(bk["bids_n"][0])
                        if bk["asks_p"]:
                            item["ask"] = bk["asks_p"][0]
                            item["ask_n"] = int(bk["asks_n"][0])
                    except Exception:
                        pass
                for item in puts:
                    try:
                        bk = self.getBook(item["code"])
                        if bk["bids_p"]:
                            item["bid"] = bk["bids_p"][0]
                            item["bid_n"] = int(bk["bids_n"][0])
                        if bk["asks_p"]:
                            item["ask"] = bk["asks_p"][0]
                            item["ask_n"] = int(bk["asks_n"][0])
                    except Exception:
                        pass

        self._logger.info(
            "getOptionChain(%s, %s) -> %d calls, %d puts.",
            underlying, exp_str, len(calls), len(puts)
        )
        return {
            "calls": calls,
            "puts": puts
        }


# Aliases for convenience
KISApi = KISTrade
KISAPI = KISTrade
