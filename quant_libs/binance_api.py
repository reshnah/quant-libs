from quant_libs.utils import *
from quant_libs.logger import *

# Importing required packages -------------------------------#
import sys
import datetime
import requests
from urllib.parse import urlencode
import time
import os
import hmac
import hashlib
from matplotlib import pyplot as plt

from PyQt5 import QtWidgets
from PyQt5.QtWidgets import *
from PyQt5 import QtGui
from PyQt5 import uic
from PyQt5 import QtCore


from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

# For websocket
import websocket
import json
from base64 import b64decode
from base64 import b64encode
#from Crypto.Cipher import AES


#------------------------------- Importing required packages #


def utc2cur(dt):
    offset = datetime.datetime.now()-datetime.datetime.utcnow()
    return dt + offset
def cur2utc(dt):
    offset = datetime.datetime.utcnow()-datetime.datetime.now()
    return dt + offset



# Binance API class
class Binance():
    apikey = ""
    secretkey = ""
    test = False
    baseurl = ""
    tick_sizes = {}
    qty_steps = {}
    min_qtys = {}
    leverages = {}
    last_prices = {}
    recv_window = 15000
    exchange = "SPOT"
    ep_prefix = ""
    ep_prefix_margin = ""
    fake_trading = False
    print_all = False
    timestamp_offset = 0


    def __init__(self, apikey="", secretkey="", test="REAL",exchange="SPOT",key_path=".",leverage=1):
        if test=="FAKE":
            self.fake_trading = True
        if apikey=="":
            fin = open(key_path, "r")
            self.apikey = fin.readline().strip()
            self.secretkey = fin.readline().strip()
            fin.close()
            if self.apikey=="":
                print("Please fill the API Key in %s/key.txt"%key_path)
                sys.exit()
        else:
            self.apikey = apikey
            self.secretkey = secretkey
        if not exchange in ["SPOT", "USDM","COINM","OPTION"]:
            print("Wrong Exchange Information. Set to SPOT")
            exchange = "SPOT"
        if exchange=="SPOT":
            if test=="DEMO":
                self.baseurl = "https://testnet.binance.vision"
            else:
                self.baseurl = "https://api.binance.com"
                #self.baseurl = "https://api1.binance.com"
                #self.baseurl = "https://api2.binance.com"
                #self.baseurl = "https://api3.binance.com"
                #self.baseurl = "https://api4.binance.com"
            self.ep_prefix = "/api/v3"
            self.ep_prefix_margin = "/sapi/v1"
        elif exchange=="USDM":
            if test=="DEMO":
                self.baseurl = "https://testnet.binancefuture.com"
            else:
                self.baseurl = "https://fapi.binance.com"
            self.ep_prefix = "/fapi/v1"
        elif exchange=="COINM":
            if test=="DEMO":
                self.baseurl = "https://testnet.binancefuture.com"
            else:
                self.baseurl = "https://dapi.binance.com"
            self.ep_prefix = "/dapi/v1"
        elif exchange=="OPTION":
            if test=="DEMO":
                self.baseurl = "https://testnet.binanceops.com"
            else:
                self.baseurl = "https://vapi.binance.com"
            self.ep_prefix = "/vapi/v1"
        else:
            print("ERROR!!")
            sys.exit()

        #if exchange=="USDM":
        #    self.USDMChangePositionMode(True)

        self.exchange = exchange
        self.test = test
        self.adjustTimestampOffset()
        self.updateLotInformations()
        self.updateAllPrices()
        if exchange=="USDM":
            self.USDMUpdateLeverages()

    def std_log(self,s):
        print(strNow()+s)
        fout = open("logs\\binance_log_%s.txt"%(strToday(6)), "a")
        fout.writelines(strNow()+s+"\n")
        fout.close()

    #def getLastPrice(self,symbol):



    def getTickRatio(self,symbol):
        return self.tick_sizes[symbol] / self.last_prices[symbol]
    def getLastPrice(self, symbol):
        return self.last_prices[symbol]
    def getUnitCost(self, symbol):
        return self.last_prices[symbol]/self.leverages[symbol]

    def getQuantityFromInvest(self, symbol, invest_usd):
        return self.qtyRoundUp(symbol, invest_usd/(self.last_prices[symbol]/self.leverages[symbol]))


    def priceRound(self,symbol,price):
        return round(self.tick_sizes[symbol]*int(price/self.tick_sizes[symbol]+0.5),9)
    def qtyRound(self,symbol,qty):
        #print(self.qty_steps[symbol])
        return round(self.qty_steps[symbol]*int(qty/self.qty_steps[symbol]+0.5),9)
    def qtyRoundUp(self,symbol,qty):
        #print(self.qty_steps[symbol])
        return round(self.qty_steps[symbol]*int(qty/self.qty_steps[symbol]+0.9999999),9)

    def priceRoundDown(self,symbol,price):
        return round(self.tick_sizes[symbol]*int(price/self.tick_sizes[symbol]),9)
    def qtyRoundDown(self,symbol,qty):
        #print(self.qty_steps[symbol])
        return round(self.qty_steps[symbol]*int(qty/self.qty_steps[symbol]),9)

    def getAllSymbols(self):
        all_symbols = []
        for symbol in self.qty_steps:
            all_symbols.append(symbol)
        return all_symbols

    def dispatch_request_old(self, http_method):
        success = False
        while not success:
            try:
                session = requests.Session()
                success = True
            except:
                success = False
                print("Warning@dispatch_request: Server not responding")
                time.sleep(5)
        session.headers.update({
            'Content-Type': 'application/json;charset=utf-8',
            'X-MBX-APIKEY': self.apikey
        })
        return {
            'GET': session.get,
            'DELETE': session.delete,
            'PUT': session.put,
            'POST': session.post,
        }.get(http_method, 'GET')


    def dispatch_request(self, http_method):
        success = False
        while not success:
            try:
                session = requests.Session()
                session.headers.update({
                    'Content-Type': 'application/json;charset=utf-8',
                    'X-MBX-APIKEY': self.apikey
                })
                result = {
                    'GET': session.get,
                    'DELETE': session.delete,
                    'PUT': session.put,
                    'POST': session.post,
                }.get(http_method, 'GET')
                success = True
            except:
                success = False
                print("Warning@dispatch_request: Request error")
                time.sleep(5)
        return result
    def getServerTimestamp(self):
        while True:
            raw = self.send_public_request(self.ep_prefix + "/time")
            if "serverTime" in raw:
                break
            time.sleep(5)
        return raw["serverTime"]

    def getTimestamp(self):
        return int(time.time()*1000+self.timestamp_offset)
    def adjustTimestampOffset(self):
        sts0 = self.getServerTimestamp()
        ts = self.getTimestamp()
        sts1 = self.getServerTimestamp()
        self.timestamp_offset += (sts0+sts1)/2-ts
        print("new timestamp_offset: %d"%self.timestamp_offset)

    def hashing(self,query_string):
        return hmac.new(self.secretkey.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

    def send_signed_request(self,http_method, url_path, payload={}):
        payload["recvWindow"] = self.recv_window

        while True:
            try:
                query_string = urlencode(payload, True)
                if query_string:
                    query_string = "{}&timestamp={}".format(query_string, self.getTimestamp())
                else:
                    query_string = 'timestamp={}'.format(self.getTimestamp())

                url = self.baseurl+url_path+'?'+query_string+'&signature='+self.hashing(query_string)
                # print("{} {}".format(http_method, url))
                params = {'url': url, 'params': {}}
                response = self.dispatch_request(http_method)(**params)
                result = response.json()
                if "code" in result and result["code"]==-1021:
                    self.adjustTimestampOffset()
                    continue
                elif "code" in result and result["code"]==-1008:
                    self.std_log(result["msg"])
                    continue
                break
            except:
                self.std_log("Warning@send_signed_request: JSON error")
                time.sleep(5)

        return result


    def send_public_request(self, url_path, payload={}):

        while True:
            try:
                query_string = urlencode(payload, True)
                url = self.baseurl+url_path
                if query_string:
                    url = url+'?'+query_string
                #print("{}".format(url))
                response = self.dispatch_request('GET')(url=url)
                #print(response)
                result = response.json()
                if "code" in result and result["code"] == -1008:
                    self.std_log(result["msg"])
                    continue
                break
            except:
                self.std_log("Warning@send_public_request: JSON error")
                time.sleep(5)
        return result

    def updateAllPrices(self):
        while True:
            raw = self.send_public_request(self.ep_prefix+"/ticker/price",payload={})
            if type(raw)!=list:
                print("if type(raw)!=list:")
                print(raw)
                continue
            break
        for info in raw:
            self.last_prices[info["symbol"]] = float(info["price"])
    def updateLotInformations(self):
        raw = self.getExchangeInfo()
        for r in raw["symbols"]:
            # if r["contractType"]!="PERPETUAL": continue
            # if r["contractType"] != "PERPETUAL": continue
            symbol = r["symbol"]
            # print(symbol)
            tick_size = 0
            qty_step = 0
            for f in r["filters"]:
                if f["filterType"] == "PRICE_FILTER":
                    tick_size = float(f["tickSize"])
                elif f["filterType"] == "LOT_SIZE":
                    qty_step = float(f["stepSize"])
                    min_qty = float(f["minQty"])

            self.tick_sizes[symbol] = tick_size
            self.qty_steps[symbol] = qty_step
            self.min_qtys[symbol] = min_qty
            self.last_prices[symbol] = -1
            # if exchange == "USDM":
            #    self.USDMChangeLeverage(symbol, leverage)

    def getChart(self,symbol,interval,start_t=0,end_t=0):
        if not interval in ["1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d","3d","1w","1M"]:
            print("getChart: invalid interval")
            return
        payload = {"symbol":symbol,"interval":interval, "limit":1000}
        # start_t & end_t are assumed to be UTC!!
        if start_t!=0:
            payload["startTime"] = int(utc2cur(start_t).timestamp()*1000)
        if end_t != 0:
            payload["endTime"] = int(utc2cur(end_t).timestamp()*1000)
        #payload = {"symbol":symbol,"interval":interval,"startTime":int(sT.timestamp()*1000),"endTime":int(eT.timestamp()*1000)}
        while True:
            raw = self.send_public_request(self.ep_prefix+"/klines",payload=payload)
            if type(raw)!=list:
                print("if type(raw)!=list:")
                print(raw)
                continue
            if type(raw[0])!=list:
                print("if type(raw[0])!=list:")
                continue
            if len(raw[0])==0:
                print("if len(raw[0])==0:")
                continue
            if type(raw[0][0]) != int:
                print("if type(raw[0][0]) != int:")
                continue
            if type(raw[0][1]) != str:
                print("if type(raw[0][1]) != str:")
                continue
            break
        chart = {"t":[],"o":[],"h":[],"l":[],"c":[],"v":[]}
        for r in raw:
            try:
                chart["t"].append(datetime.datetime.utcfromtimestamp(r[0]/1000))
            except:
                print(symbol,r)
                raise
            #chart["t"].append(datetime.datetime.fromtimestamp(r[0]/1000))
            chart["o"].append(float(r[1]))
            chart["h"].append(float(r[2]))
            chart["l"].append(float(r[3]))
            chart["c"].append(float(r[4]))
            chart["v"].append(float(r[5]))
        if len(chart["t"])==0:
            print("Warning@getChart: Unable to get chart of %s"%symbol)
        return chart

    def getLongChart(self,symbol,interval,start_t,min_length=0):
        if not interval in ["1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d","3d","1w","1M"]:
            print("getChart: invalid interval")
            return
        tdelta_conv = {"1m": datetime.timedelta(minutes=1), "3m": datetime.timedelta(minutes=3),
                       "5m": datetime.timedelta(minutes=5), "15m": datetime.timedelta(minutes=15),
                       "30m": datetime.timedelta(minutes=30), "1h": datetime.timedelta(hours=1),
                       "2h": datetime.timedelta(hours=2), "4h": datetime.timedelta(hours=4),
                       "6h": datetime.timedelta(hours=6), "8h": datetime.timedelta(hours=8),
                       "12h": datetime.timedelta(hours=12), "1d": datetime.timedelta(days=1),
                       "3d": datetime.timedelta(days=3), "1w": datetime.timedelta(days=7)}
        timeframedelta = tdelta_conv[interval]
        last_t = datetime.datetime(2010,1,1)
        chart = {"t":[],"o":[],"h":[],"l":[],"c":[],"v":[]}

        start_t = min(start_t,datetime.datetime.utcnow()-timeframedelta*(min_length+1))
        while last_t<datetime.datetime.utcnow()-timeframedelta*1.5:
            newchart = self.getChart(symbol,interval,start_t=start_t)
            chart["t"] = chart["t"]+newchart["t"]
            chart["o"] = chart["o"]+newchart["o"]
            chart["h"] = chart["h"]+newchart["h"]
            chart["l"] = chart["l"]+newchart["l"]
            chart["c"] = chart["c"]+newchart["c"]
            chart["v"] = chart["v"]+newchart["v"]
            last_t = chart["t"][-1]
            start_t = last_t+timeframedelta
            #time.sleep(1)
            #print(chart["t"][0],last_t,newchart["t"][0],newchart["t"][-1])
        self.last_prices[symbol] = chart["c"][-1]
        return chart

    def getPrice_old(self, symbols):
        if type(symbols) == list:
            print("getPrice(): not supported")
            payload = {"symbols":symbols}
            resp = self.send_public_request(self.ep_prefix + "/ticker/price", payload=payload)
            print(resp, type(resp))
            to_return = {}
            for r in resp:
                to_return[r["symbol"]] = float(r["price"])
            return to_return
        else:
            payload = {"symbol":symbols}
            resp = self.send_public_request(self.ep_prefix + "/ticker/price", payload=payload)
            return float(resp["price"])


    def getExchangeInfo(self):
        raw = self.send_public_request(self.ep_prefix+"/exchangeInfo")
        return raw

    def getBook(self,symbol):
        payload = {"symbol": symbol}
        raw = self.send_public_request(self.ep_prefix+"/depth", payload=payload)
        return raw

    def USDMChangePositionMode(self, dualSide):
        if dualSide:
            payload = {"dualSidePosition": "true"}
        else:
            payload = {"dualSidePosition": "false"}
        a = self.send_signed_request("POST", self.ep_prefix+"/positionSide/dual", payload=payload)
        return a
    def USDMChangeLeverage(self,symbol,leverage):
        payload = {"symbol":symbol, "leverage": int(leverage)}
        a = self.send_signed_request("POST", self.ep_prefix+"/leverage", payload=payload)
        return a

    def USDMUpdateLeverages(self):
        a = self.USDMAccount()
        #print(a["positions"])
        for position in a["positions"]:
            self.leverages[position["symbol"]] = int(position["leverage"])
        return a
    def USDMChangeMarginType(self,symbol,marginType):
        if not marginType in ["ISOLATED", "CROSSED"]:
            return -1
        payload = {"symbol":symbol, "marginType": marginType}
        a = self.send_signed_request("POST", self.ep_prefix+"/marginType", payload=payload)
        return a
    def USDMGetEntryPrice(self,symbol):
        acc = self.USDMAccount()
        acc = acc["positions"]
        price = -1
        for position in acc:
            if position["symbol"]==symbol:
                price = position["entryPrice"]
                break
        return price

    ws_prices = 0

    def ws_prices_message(self,ws, message):
        print("WebSocket thread: %s"%message)

    def ws_prices_open(self):
        print("open")
        subscribe_fmt = {"method": "SUBSCRIBE", "params": ["!miniTicker@arr"], "id": 1}
        subscribe_data = json.dumps(subscribe_fmt)
        self.ws_prices.send(subscribe_data)

    def ws_prices_thread(self,*args):
        ws = websocket.WebSocketApp("wss://fstream.binance.com/ws", on_open=self.ws_prices_open, on_message=self.ws_prices_message)
        ws.run_forever()

    def USDMUnsubscribePrices(self):
        if self.ws_prices!=0:
            self.ws_prices = websocket.create_connection("wss://fstream.binance.com/ws")
            subscribe_fmt = {"method": "UNSUBSCRIBE", "params": ["!miniTicker@arr"], "id": 1}
            subscribe_data = json.dumps(subscribe_fmt)
            self.ws_prices.send(subscribe_data)

    cur_price = {}

    def USDMUpdatePrices(self):
        while True:
            if self.ws_prices==0:   # New connection
                self.ws_prices = websocket.create_connection("wss://fstream.binance.com/ws")
                subscribe_fmt = {"method": "SUBSCRIBE", "params": ["!miniTicker@arr"], "id": 1}
                subscribe_data = json.dumps(subscribe_fmt)
                self.ws_prices.send(subscribe_data)
            try:
                result = self.ws_prices.recv()
            except websocket._exceptions.WebSocketConnectionClosedException or ConnectionResetError:
                self.ws_prices = websocket.create_connection("wss://fstream.binance.com/ws")
                subscribe_fmt = {"method": "SUBSCRIBE", "params": ["!miniTicker@arr"], "id": 1}
                subscribe_data = json.dumps(subscribe_fmt)
                #print(subscribe_data)
                self.ws_prices.send(subscribe_data)
                result = self.ws_prices.recv()
            if "null" in result: continue
            for p in eval(result):
                self.cur_price[p["s"]]=float(p["c"])
            not_loaded = False
            for symbol in self.tick_sizes:
                if not symbol in self.cur_price:
                    not_loaded = True
                    #print("not_loaded %s"%symbol)
                    print("Price loading.. %s"%symbol)
                    break
            if not_loaded: continue
            break

    def GetContractPrice2(self,symbol,orderId):
        payload = {"symbol": symbol,"orderId":orderId}
        price = self.cur_price[symbol]
        if not self.fake_trading:
            for trial in range(100):
                if self.exchange == "SPOT":
                    a = self.send_signed_request("GET", self.ep_prefix+"/myTrades", payload=payload)
                elif self.exchange == "USDM":
                    a = self.send_signed_request("GET", self.ep_prefix+"/order", payload=payload)
                #if "code" in a:
                if not "avgPrice" in a:
                    print(a)
                    print("Warning@GetContractPrice2: GetContractPrice2(%s,%d), error"%(symbol, int(orderId)))
                    time.sleep(1)
                    continue
                price = float(a["avgPrice"])
                if price > 0: break
                print("Warning@GetContractPrice2: Server did not accept order yet")
                time.sleep(1)
            if self.print_all:
                print(a)
        return price

    def GetContractPrice(self,symbol,orderId):
        #payload = {"symbol": symbol,"startTime":int(utc2cur(datetime.datetime.utcnow()-datetime.timedelta(minutes=10)).timestamp()*1000)}
        payload = {"symbol": symbol}
        if self.fake_trading:
            price = -1
        else:
            for trial in range(100):
                if self.exchange=="SPOT":
                    a = self.send_signed_request("GET", self.ep_prefix+"/myTrades", payload=payload)
                elif self.exchange=="USDM":
                    a = self.send_signed_request("GET", self.ep_prefix+"/userTrades", payload=payload)
                price = -1
                #print(a)
                if "code" in a:
                    print("Warning@GetContractPrice: GetContractPrice(%s,%d), error"%(symbol,int(orderId)))
                    time.sleep(1)
                    continue
                for order in a:
                    if order["orderId"]==int(orderId):
                        price = float(order["price"])
                        break
                if price!=-1: break
                print("Warning@GetContractPrice: Server did not accept order yet")
                time.sleep(1)
        if self.print_all:
            print(a)
        return price






    def CheckOrder(self,symbol,orderId):

        if self.fake_trading:
            # TODO
            price = -1
        else:
            payload = {"symbol": symbol, "orderId": orderId}
            a = self.send_signed_request("GET", self.ep_prefix+"/order", payload=payload)
            # "status": "FILLED" / "NEW" / "CANCELED" / "EXPIRED"
        return a

    def ShortStoploss(self,symbol,quantity,price):
        payload = {"symbol": symbol, "side": "BUY", "quantity": self.qtyRound(symbol, quantity)}
        #payload["reduceOnly"] = "true"
        payload["reduceOnly"] = "false"
        payload["type"] = "STOP_MARKET"
        payload["timeInForce"] = "GTC"
        payload["stopPrice"] = self.priceRound(symbol, price)
        # print(payload)
        a = self.send_signed_request("POST", self.ep_prefix+"/order", payload=payload)

        # print(a)
        if not "orderId" in a:
            if a["code"]==-2021:
                self.std_log("Warning@ShortStoploss(): Price is already above stoploss")
            else:
                self.std_log(str(a))
                self.std_log("Order error")
                raise ValueError
        else:
            self.std_log("Set stoploss %s (quantity:%f, orderID:%d)"%(symbol, quantity, a["orderId"]))

        return a

    def LongStoploss(self,symbol,quantity,price):
        payload = {"symbol": symbol, "side": "SELL", "quantity": self.qtyRound(symbol, quantity)}
        #payload["reduceOnly"] = "true"
        payload["reduceOnly"] = "false"
        payload["type"] = "STOP_MARKET"
        payload["timeInForce"] = "GTC"
        payload["stopPrice"] = self.priceRound(symbol, price)
        # print(payload)
        a = self.send_signed_request("POST", self.ep_prefix+"/order", payload=payload)

        # print(a)
        if not "orderId" in a:
            if a["code"]==-2021:    # ORDER_WOULD_IMMEDIATELY_TRIGGER
                self.std_log("Warning@LongStoploss(): Price is already below stoploss")
            else:
                self.std_log(str(a))
                self.std_log("Order error")
                raise ValueError
        else:
            self.std_log("Set stoploss %s (quantity:%f, orderID:%d)"%(symbol, quantity, a["orderId"]))

        return a
    def Buy(self,symbol,quantity,price,leverage=0,reduce_only=False,position="",priceMatch="NONE"):
        return self.NewOrder("BUY",symbol,quantity,price,leverage=leverage,reduce_only=reduce_only,position=position,priceMatch=priceMatch)

    def Sell(self,symbol,quantity,price,leverage=0,reduce_only=False,position="",priceMatch="NONE"):
        return self.NewOrder("SELL",symbol,quantity,price,leverage=leverage,reduce_only=reduce_only,position=position,priceMatch=priceMatch)

    def NewOrder(self,side,symbol,quantity,price,leverage=0,reduce_only=False,position="",priceMatch="NONE"):
        if self.fake_trading:
            # TODO
            a = {"orderId":0}
        else:
            if self.exchange=="USDM" and leverage!=0:
                self.USDMChangeLeverage(symbol,leverage)
            payload = {"symbol":symbol,"side":side,"quantity":self.qtyRound(symbol,quantity)}
            if position!="":
                payload["positionSide"] = position
            payload["priceMatch"] = priceMatch
            if reduce_only: # Only in future
                payload["reduceOnly"]="true"
            if priceMatch[0]=="Q":
                payload["type"] = "LIMIT"
                payload["timeInForce"] = "GTC"
            elif priceMatch[0]=="O":
                pass
            else:
                if price==0:
                    payload["type"] = "MARKET"
                else:
                    payload["type"] = "LIMIT"
                    payload["timeInForce"] = "GTC"
                    payload["price"] = self.priceRound(symbol,price)
            a = self.send_signed_request("POST",self.ep_prefix+"/order",payload=payload)
            #print(a)
            if not "orderId" in a:

                if a["code"] == -2022:  # REDUCE_ONLY_REJECT
                    self.std_log("Warning@NewOrder():Order(or stoploss) may already have been executed")
                elif a["code"] == -2019:
                    self.std_log(str(a))
                    return None
                else:
                    self.std_log(str(a))
                    self.std_log("Order error with NewOrder(%s,%s,%s,%s)"%(side,symbol,quantity,price))
                    raise ValueError
            else:
                self.std_log("NewOrder %s (quantity:%f, orderID:%d)"%(symbol, quantity, a["orderId"]))
        return a
    def BuyModify(self, symbol, orderId, quantity, price, priceMatch="NONE"):
        return self.OrderModify("BUY", symbol, orderId, quantity, price, priceMatch=priceMatch)
    def SellModify(self, symbol, orderId, quantity, price, priceMatch="NONE"):
        return self.OrderModify("SELL", symbol, orderId, quantity, price, priceMatch=priceMatch)
    def OrderModify(self, side, symbol, orderId, quantity, price, priceMatch="NONE"):
        if self.fake_trading:
            # TODO
            a = {"orderId": 0}
        else:
            payload = {"orderId":orderId, "symbol": symbol, "side": side, "quantity": self.qtyRound(symbol, quantity)}
            if priceMatch[0] == "Q":
                #payload["type"] = "LIMIT"
                #payload["timeInForce"] = "GTC"
                payload["priceMatch"] = priceMatch
            elif priceMatch[0] == "O":
                payload["priceMatch"] = priceMatch
            else:
                payload["price"] = self.priceRound(symbol, price)
            a = self.send_signed_request("PUT", self.ep_prefix + "/order", payload=payload)
            if "code" in a:
                if a["code"]==-5027 or a["code"]==-2013:
                    print(payload, a)
                    return a
            # print(a)
            if not "orderId" in a:

                if a["code"] == -2022:  # REDUCE_ONLY_REJECT
                    self.std_log("Warning@OrderModify():Order(or stoploss) may already have been executed")
                else:
                    self.std_log(str(a))
                    self.std_log("Order error with OrderModify(%s,%s,%s)" % (symbol, quantity, price))
                    raise ValueError
            else:
                self.std_log("OrderModify %s (quantity:%f, orderID:%d)" % (symbol, quantity, a["orderId"]))
        return a

    def OrderCancel(self,symbol,orderId):

        if self.fake_trading:
            # TODO
            a = {}
        else:
            payload = {"symbol":symbol,"orderId":orderId}
            a = self.send_signed_request("DELETE",self.ep_prefix+"/order",payload=payload)
        return a


    def OrderWait(self,symbol, orderId):
        order = {}
        if orderId==-1 or self.fake_trading:   # Server issue: OrderWait does not work properly
            order_filled = True

            order = {"executedQty":10}
            time.sleep(1)
        else:
            order_filled = False
            try:
                while True:
                    order = self.CheckOrder(symbol, orderId)
                    # {'code': -2013, 'msg': 'Order does not exist.'}
                    if not "status" in order:
                        print(order)
                        print("Warning@OrderWait(): Server did not accept order yet.")
                    elif order["origQty"] == order["executedQty"]:
                        order_filled = True
                        break
                    time.sleep(1.5)
            except KeyboardInterrupt:
                self.std_log("%s"%str(order))
                self.std_log("Order %s canceled"%orderId)
                self.OrderCancel(symbol, orderId)
        if self.print_all:
            print("print_all")
            print(order)
        order["executedPrice"] = self.priceRound(symbol,float(order["cummulativeQuoteQty"])/float(order["executedQty"]))
        return order_filled,order


    def BuyMargin(self,symbol,quantity,price,leverage=0,position=""):
        if self.fake_trading:
            # TODO
            a = {"orderId":0}
        else:
            if self.exchange == "USDM" and leverage != 0:
                self.USDMChangeLeverage(symbol,leverage)
            payload = {"symbol":symbol,"side":"BUY","quantity":self.qtyRound(symbol,quantity)}
            if position!="":
                payload["positionSide"] = position
            if price==0:
                payload["type"] = "MARKET"
            else:
                payload["type"] = "LIMIT"
                payload["timeInForce"] = "GTC"
                payload["price"] = self.priceRound(symbol,price)
            payload["sideEffectType"] = "MARGIN_BUY"    # Option in Margin
            a = self.send_signed_request("POST",self.ep_prefix_margin+"/margin/order",payload=payload)

            if not "orderId" in a:
                if a["code"] == -2022:  # REDUCE_ONLY_REJECT
                    self.std_log("Warning@BuyMargin():Order(or stoploss) may already have been executed")
                else:
                    self.std_log(str(a))
                    self.std_log("Order error with Buy(%s,%s,%s)"%(symbol,quantity,price))
                    raise ValueError
            else:
                self.std_log("BuyMargin %s (quantity:%f, orderID:%d)"%(symbol, quantity, a["orderId"]))
        return a

    def SellMargin(self,symbol,quantity,price,leverage=0,position=""):
        # TODO: repay
        if self.fake_trading:
            # TODO
            a = {"orderId":0}
        else:
            if self.exchange=="USDM" and leverage!=0:
                self.USDMChangeLeverage(symbol,leverage)
            payload = {"symbol":symbol,"side":"SELL","quantity":self.qtyRound(symbol,quantity)}
            if position!="":
                payload["positionSide"] = position
            if price==0:
                payload["type"] = "MARKET"
            else:
                payload["type"] = "LIMIT"
                payload["timeInForce"] = "GTC"
                payload["price"] = self.priceRound(symbol,price)
            payload["sideEffectType"] = "AUTO_REPAY"
            a = self.send_signed_request("POST",self.ep_prefix_margin+"/margin/order",payload=payload)
            #print(a)
            if not "orderId" in a:

                if a["code"] == -2022:  # REDUCE_ONLY_REJECT
                    self.std_log("Warning@SellMargin():Order(or stoploss) may already have been executed")
                else:
                    self.std_log(str(a))
                    self.std_log("Order error with SellMargin(%s,%s,%s)"%(symbol,quantity,price))
                    raise ValueError
            else:
                self.std_log("SellMargin %s (quantity:%f, orderID:%d)"%(symbol, quantity, a["orderId"]))
        return a

    def OrderCancelMargin(self,symbol,orderId):

        if self.fake_trading:
            # TODO
            a = {}
        else:
            payload = {"symbol":symbol,"orderId":orderId}
            a = self.send_signed_request("DELETE",self.ep_prefix_margin+"/margin/order",payload=payload)
        return a


    def CheckOrderMargin(self,symbol,orderId):

        if self.fake_trading:
            # TODO
            price = -1
        else:
            payload = {"symbol": symbol, "orderId": orderId}
            a = self.send_signed_request("GET", self.ep_prefix_margin+"/margin/order", payload=payload)
            # "status": "FILLED" / "NEW" / "CANCELED" / "EXPIRED"
        return a


    def OrderWaitMargin(self,symbol, orderId):
        order = {}
        if orderId==-1 or self.fake_trading:   # Server issue: OrderWait does not work properly
            order_filled = True

            order = {"executedQty":10}
            time.sleep(1)
        else:
            order_filled = False
            try:
                while True:
                    order = self.CheckOrderMargin(symbol, orderId)
                    # {'code': -2013, 'msg': 'Order does not exist.'}
                    if not "status" in order:
                        print(order)
                        print("Warning@OrderWaitMargin(): Server did not accept order yet.")
                    elif order["origQty"] == order["executedQty"]:
                        order_filled = True
                        break
                    time.sleep(1.5)
            except KeyboardInterrupt:
                self.std_log("%s"%str(order))
                self.std_log("Order %s canceled"%orderId)
                self.OrderCancelMargin(symbol, orderId)
        if self.print_all:
            print("print_all")
            print(order)
        order["executedPrice"] = self.priceRound(symbol,float(order["cummulativeQuoteQty"])/float(order["executedQty"]))
        return order_filled,order


    def SpotAccount(self):
        return self.send_signed_request("GET","/api/v3/account")

    def getSpotBalanceQuantity(self,symbol):
        if self.fake_trading:
            quantity = -1
        else:
            while True:
                acc = self.SpotAccount()
                if "balances" in acc:
                    break
                print(acc)
                time.sleep(0.5)
            acc = acc["balances"]
            quantity = -1
            for asset in acc:
                if asset["asset"]==symbol:
                    quantity = float(asset["free"])
                    break
        return quantity
    def getSpotBalanceTotalQuantity(self,symbol):
        if self.fake_trading:
            quantity = -1
        else:
            while True:
                acc = self.SpotAccount()
                if "balances" in acc:
                    break
                print(acc)
                time.sleep(0.5)
            acc = acc["balances"]
            quantity = -1
            for asset in acc:
                if asset["asset"]==symbol:
                    quantity = float(asset["free"])+float(asset["locked"])
                    break
        return quantity


    def MarginAccount(self):
        return self.send_signed_request("GET","/sapi/v1/margin/account")
    def IsolatedMarginAccount(self):
        return self.send_signed_request("GET","/sapi/v1/margin/isolated/account")

    def getMarginBalanceQuantity(self,symbol):
        if self.fake_trading:
            quantity = -1
        else:
            while True:
                acc = self.MarginAccount()
                if "userAssets" in acc:
                    break
                print(acc)
                time.sleep(0.5)
            acc = acc["userAssets"]
            quantity = -1
            for asset in acc:
                if asset["asset"]==symbol:
                    quantity = float(asset["netAsset"])-float(asset["locked"])
                    break
        return quantity
    def getMarginBalanceTotalQuantity(self,symbol):
        if self.fake_trading:
            quantity = -1
        else:
            while True:
                acc = self.MarginAccount()
                if "userAssets" in acc:
                    break
                print(acc)
                time.sleep(0.5)
            acc = acc["userAssets"]
            quantity = -1
            for asset in acc:
                if asset["asset"]==symbol:
                    print(asset)
                    quantity = float(asset["netAsset"])
                    break
        return quantity


    def USDMAccount(self):
        while True:
            result = self.send_signed_request("GET","/fapi/v2/account")
            if "totalMarginBalance" in result:
                break
            self.std_log("Warning@USDMAccount(): Account not fetched well %s"%(str(result)))
            time.sleep(1)
        return result
    def getUsdmBalance(self):
        while True:
            result = self.send_signed_request("GET","/fapi/v2/balance")
            if type(result)==list:
                break
            self.std_log("Warning@getUsdmBalance(): not fetched well %s"%(str(result)))
            time.sleep(1)
        return result
    def getUSDMBalanceQuantity(self,symbol):
        if self.fake_trading:
            quantity = -1
        else:
            acc = self.USDMAccount()
            acc = acc["positions"]
            quantity = -1
            for position in acc:
                if position["symbol"]==symbol:
                    quantity = position["positionAmt"]
                    break
        return float(quantity)

    def getUSDMMarginBalance(self): # Balance with unrealized profits
        acc = self.USDMAccount()
        if self.print_all:
            print(acc)
        balance = float(acc["totalMarginBalance"]) # totalMarginBalance / totalWalletBalance / availableBalance
        return balance

    def getUSDMWalletBalance(self): # Balance before position entry
        acc = self.USDMAccount()
        if self.print_all:
            print(acc)
        balance = float(acc["totalWalletBalance"]) # totalMarginBalance / totalWalletBalance / availableBalance
        return balance

    def getUsdmAvailableBalance(self): # Available for new order
        acc = self.USDMAccount()
        if self.print_all:
            print(acc)
        balance = float(acc["availableBalance"]) # totalMarginBalance / totalWalletBalance / availableBalance
        return balance
    def getUSDMSafeBalance(self, ratio):    # User custom safe balance
        acc = self.USDMAccount()
        if self.print_all:
            print(acc)
        margin = float(acc["totalMarginBalance"])
        position = float(acc["totalPositionInitialMargin"])

        return margin*ratio-position

    def boundaryRemaining(self, tf):
        # "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"
        #t = datetime.datetime.now()
        t = datetime.datetime.utcnow()
        if tf == "1m":
            next_t = (t+datetime.timedelta(minutes=1)).replace(second=0,microsecond=0)
        elif tf == "3m":
            next_t = (t+datetime.timedelta(minutes=3-t.minute%3)).replace(second=0, microsecond=0)
        elif tf == "5m":
            next_t = (t+datetime.timedelta(minutes=5-t.minute%5)).replace(second=0, microsecond=0)
        elif tf == "15m":
            next_t = (t+datetime.timedelta(minutes=15-t.minute%15)).replace(second=0, microsecond=0)
        elif tf == "30m":
            next_t = (t+datetime.timedelta(minutes=30-t.minute%30)).replace(second=0, microsecond=0)
        elif tf == "1h":
            next_t = (t+datetime.timedelta(hours=1)).replace(minute=0,second=0,microsecond=0)
        elif tf == "2h":
            next_t = (t+datetime.timedelta(hours=2-t.hour%2)).replace(minute=0, second=0, microsecond=0)
        elif tf == "4h":
            next_t = (t+datetime.timedelta(hours=4-t.hour%4)).replace(minute=0, second=0, microsecond=0)
        elif tf == "6h":
            next_t = (t+datetime.timedelta(hours=6-t.hour%6)).replace(minute=0, second=0, microsecond=0)
        elif tf == "8h":
            next_t = (t+datetime.timedelta(hours=8-t.hour%8)).replace(minute=0, second=0, microsecond=0)
        elif tf == "12h":
            next_t = (t+datetime.timedelta(hours=12-t.hour%12)).replace(minute=0, second=0, microsecond=0)
        elif tf == "1d":
            next_t = (t+datetime.timedelta(hours=24)).replace(hour=0,minute=0, second=0, microsecond=0)
        elif tf == "3d":
            day_pivot = datetime.datetime(2017, 8, 17, 0, 0)
            next_t = (t+datetime.timedelta(days=3-(t-day_pivot).days%3)).replace(hour=0,minute=0, second=0, microsecond=0)
        elif tf == "1w":  # Monday 0am
            next_t = (t+datetime.timedelta(days=7-t.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
        elif tf == "1M":  # 0am
            if t.month==12:
                next_t = datetime.datetime(t.year+1,1,1,0,0,0)
            else:
                next_t = datetime.datetime(t.year, t.month+1, 1, 0, 0, 0)
        remaining = next_t-t
        return remaining

