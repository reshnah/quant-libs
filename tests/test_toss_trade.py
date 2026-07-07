import unittest
from unittest.mock import patch, MagicMock
import os
import time

from quant_libs.toss_trade import TossTrade, TossAPIError

class TestTossTrade(unittest.TestCase):
    def setUp(self):
        # Set dummy environment variables
        self.env_patch = patch.dict(os.environ, {
            "TOSS_API_KEY": "test_api_key",
            "TOSS_SECRET_KEY": "test_secret_key"
        })
        self.env_patch.start()

        # Common mock responses
        self.token_response = {
            "access_token": "mock_jwt_token",
            "token_type": "Bearer",
            "expires_in": "3600"
        }
        self.accounts_response = {
            "result": [
                {
                    "accountNo": "123-456-789",
                    "accountSeq": 987654321,
                    "accountType": "BROKERAGE"
                }
            ]
        }

    def tearDown(self):
        self.env_patch.stop()

    @patch("requests.Session.request")
    def test_initialization_resolves_account(self, mock_request):
        # Setup mocks for oauth2 token and accounts list
        mock_resp_token = MagicMock()
        mock_resp_token.status_code = 200
        mock_resp_token.json.return_value = self.token_response

        mock_resp_accounts = MagicMock()
        mock_resp_accounts.status_code = 200
        mock_resp_accounts.json.return_value = self.accounts_response

        mock_request.side_effect = [mock_resp_token, mock_resp_accounts]

        # Init TossTrade client
        client = TossTrade()
        
        self.assertEqual(client.account_seq, 987654321)
        self.assertEqual(client._access_token, "mock_jwt_token")

    def test_initialization_missing_keys(self):
        # Remove environment variables
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                TossTrade()

    @patch("requests.Session.request")
    def test_token_auto_refresh(self, mock_request):
        # Mock responses
        mock_resp_token = MagicMock()
        mock_resp_token.status_code = 200
        mock_resp_token.json.return_value = self.token_response

        mock_resp_accounts = MagicMock()
        mock_resp_accounts.status_code = 200
        mock_resp_accounts.json.return_value = self.accounts_response

        mock_request.side_effect = [mock_resp_token, mock_resp_accounts]

        client = TossTrade()
        
        # Manually expire the token
        client._token_expiry = time.time() - 10
        
        # Mock next request for token and then the API call
        mock_resp_new_token = MagicMock()
        mock_resp_new_token.status_code = 200
        mock_resp_new_token.json.return_value = {
            "access_token": "new_mock_jwt_token",
            "token_type": "Bearer",
            "expires_in": "1800"
        }
        
        mock_resp_buy = MagicMock()
        mock_resp_buy.status_code = 200
        mock_resp_buy.json.return_value = {"result": {"orderId": "order_12345"}}

        mock_request.side_effect = [mock_resp_new_token, mock_resp_buy]

        # Trigger a buy which should refresh token
        order_id = client.buy("AAPL", 5, 150.0)
        
        self.assertEqual(order_id, "order_12345")
        self.assertEqual(client._access_token, "new_mock_jwt_token")

    @patch("requests.Session.request")
    def test_buy_limit_and_market(self, mock_request):
        # Setup clients
        mock_resp_token = MagicMock()
        mock_resp_token.status_code = 200
        mock_resp_token.json.return_value = self.token_response
        mock_resp_accounts = MagicMock()
        mock_resp_accounts.status_code = 200
        mock_resp_accounts.json.return_value = self.accounts_response
        mock_request.side_effect = [mock_resp_token, mock_resp_accounts]

        client = TossTrade()

        # 1. Test Limit Buy (price > 0)
        mock_resp_buy_limit = MagicMock()
        mock_resp_buy_limit.status_code = 200
        mock_resp_buy_limit.json.return_value = {"result": {"orderId": "limit_buy_id"}}
        mock_request.side_effect = [mock_resp_buy_limit]

        order_id_limit = client.buy("AAPL", 10, 150.0)
        self.assertEqual(order_id_limit, "limit_buy_id")
        
        # Verify JSON body in request
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs["json"]["orderType"], "LIMIT")
        self.assertEqual(kwargs["json"]["price"], 150.0)
        self.assertEqual(kwargs["json"]["quantity"], 10)
        self.assertEqual(kwargs["headers"]["X-Tossinvest-Account"], "987654321")

        # 2. Test Market Buy (price == 0)
        mock_resp_buy_market = MagicMock()
        mock_resp_buy_market.status_code = 200
        mock_resp_buy_market.json.return_value = {"result": {"orderId": "market_buy_id"}}
        mock_request.side_effect = [mock_resp_buy_market]

        order_id_market = client.buy("AAPL", 10, 0)
        self.assertEqual(order_id_market, "market_buy_id")

        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs["json"]["orderType"], "MARKET")
        self.assertNotIn("price", kwargs["json"])
        self.assertEqual(kwargs["json"]["quantity"], 10)

    @patch("requests.Session.request")
    def test_sell_limit_and_market(self, mock_request):
        # Setup clients
        mock_resp_token = MagicMock()
        mock_resp_token.status_code = 200
        mock_resp_token.json.return_value = self.token_response
        mock_resp_accounts = MagicMock()
        mock_resp_accounts.status_code = 200
        mock_resp_accounts.json.return_value = self.accounts_response
        mock_request.side_effect = [mock_resp_token, mock_resp_accounts]

        client = TossTrade()

        # 1. Limit Sell
        mock_resp_sell_limit = MagicMock()
        mock_resp_sell_limit.status_code = 200
        mock_resp_sell_limit.json.return_value = {"result": {"orderId": "limit_sell_id"}}
        mock_request.side_effect = [mock_resp_sell_limit]

        order_id = client.sell("AAPL", 5, 155.0)
        self.assertEqual(order_id, "limit_sell_id")
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs["json"]["side"], "SELL")
        self.assertEqual(kwargs["json"]["orderType"], "LIMIT")
        self.assertEqual(kwargs["json"]["price"], 155.0)

        # 2. Market Sell
        mock_resp_sell_market = MagicMock()
        mock_resp_sell_market.status_code = 200
        mock_resp_sell_market.json.return_value = {"result": {"orderId": "market_sell_id"}}
        mock_request.side_effect = [mock_resp_sell_market]

        order_id = client.sell("AAPL", 5.5, 0)
        self.assertEqual(order_id, "market_sell_id")
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs["json"]["side"], "SELL")
        self.assertEqual(kwargs["json"]["orderType"], "MARKET")
        self.assertEqual(kwargs["json"]["quantity"], 5.5)
        self.assertNotIn("price", kwargs["json"])

    @patch("requests.Session.request")
    def test_modify_order(self, mock_request):
        mock_resp_token = MagicMock()
        mock_resp_token.status_code = 200
        mock_resp_token.json.return_value = self.token_response
        mock_resp_accounts = MagicMock()
        mock_resp_accounts.status_code = 200
        mock_resp_accounts.json.return_value = self.accounts_response
        mock_request.side_effect = [mock_resp_token, mock_resp_accounts]

        client = TossTrade()

        mock_resp_modify = MagicMock()
        mock_resp_modify.status_code = 200
        mock_resp_modify.json.return_value = {"result": {"orderId": "modified_order_id"}}
        mock_request.side_effect = [mock_resp_modify]

        new_id = client.modifyOrder("orig_order_id", price=160.0)
        self.assertEqual(new_id, "modified_order_id")
        
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs["json"]["orderType"], "LIMIT")
        self.assertEqual(kwargs["json"]["price"], 160.0)
        self.assertNotIn("quantity", kwargs["json"])

    @patch("requests.Session.request")
    def test_cancel_order(self, mock_request):
        mock_resp_token = MagicMock()
        mock_resp_token.status_code = 200
        mock_resp_token.json.return_value = self.token_response
        mock_resp_accounts = MagicMock()
        mock_resp_accounts.status_code = 200
        mock_resp_accounts.json.return_value = self.accounts_response
        mock_request.side_effect = [mock_resp_token, mock_resp_accounts]

        client = TossTrade()

        mock_resp_cancel = MagicMock()
        mock_resp_cancel.status_code = 200
        mock_resp_cancel.json.return_value = {"result": {"orderId": "cancelled_order_id"}}
        mock_request.side_effect = [mock_resp_cancel]

        cancel_id = client.cancelOrder("orig_order_id")
        self.assertEqual(cancel_id, "cancelled_order_id")

    @patch("requests.Session.request")
    def test_api_error_parsing(self, mock_request):
        mock_resp_token = MagicMock()
        mock_resp_token.status_code = 200
        mock_resp_token.json.return_value = self.token_response
        mock_resp_accounts = MagicMock()
        mock_resp_accounts.status_code = 200
        mock_resp_accounts.json.return_value = self.accounts_response
        mock_request.side_effect = [mock_resp_token, mock_resp_accounts]

        client = TossTrade()

        # Mock an error response
        mock_resp_err = MagicMock()
        mock_resp_err.status_code = 400
        mock_resp_err.headers = {"X-Request-Id": "req_123456"}
        mock_resp_err.json.return_value = {
            "error": {
                "requestId": "req_123456",
                "code": "invalid-request",
                "message": "주문 수량이 올바르지 않습니다.",
                "data": {"field": "quantity", "constraint": {"min": 1}}
            }
        }
        mock_request.side_effect = [mock_resp_err]

        with self.assertRaises(TossAPIError) as context:
            client.buy("AAPL", -1, 150.0)

        self.assertEqual(context.exception.code, "invalid-request")
        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(context.exception.request_id, "req_123456")
        self.assertEqual(context.exception.data["field"], "quantity")

if __name__ == "__main__":
    unittest.main()
