from quant_libs.utils import *

import sys
import os
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import datetime
import time
import MetaTrader5 as mt5




class MT5():
    timezone = "UTC"
    time_offset = datetime.timedelta(hours=-12)
    server = ""
    company = ""
    margin_free = 0

    def __init__(self,login=None,server=None,password=None):
        if login is None:
            init = mt5.initialize()
        else:
            init = mt5.initialize(login=login, server=server, password=password)
        if not init:
            print("initialize() failed")
            mt5.shutdown()
            raise Exception("Initialize failed")
        acc_info = mt5.account_info()
        self.server = acc_info.server
        self.company = acc_info.company
        self.margin_free = acc_info.margin_free
    def getDst(self):
        return False

    def setTimezone(self,tz):
        self.timezone = tz
        if getDst("US", datetime.datetime.now()):
            if tz=="UTC":
                self.time_offset = datetime.timedelta(hours=-12)
            elif tz=="KR":
                self.time_offset = datetime.timedelta(hours=-3)
        else:
            if tz=="UTC":
                self.time_offset = datetime.timedelta(hours=-11)
            elif tz=="KR":
                self.time_offset = datetime.timedelta(hours=-2)

    def buy(self,symbol,qty,price,take_profit=None,stop_loss=None,expiration=None,close_by=None,comment=None):
        if qty<0:
            return self.sendOrder("SELL", symbol, -qty, price, take_profit=take_profit, stop_loss=stop_loss, expiration=expiration, close_by=close_by, comment=comment)
        else:
            return self.sendOrder("BUY",symbol,qty, price,take_profit=take_profit,stop_loss=stop_loss,expiration=expiration,close_by=close_by, comment=comment)
    def sell(self,symbol,qty,price,take_profit=None,stop_loss=None,expiration=None,close_by=None,comment=None):
        if qty<0:
            return self.sendOrder("BUY", symbol, -qty, price, take_profit=take_profit, stop_loss=stop_loss,
                                  expiration=expiration, close_by=close_by, comment=comment)
        else:
            return self.sendOrder("SELL",symbol, qty, price,  take_profit=take_profit, stop_loss=stop_loss, expiration=expiration,close_by=close_by, comment=comment)


    def getPrice(self, pair):
        info = mt5.symbol_info(pair)
        return (info.bid + info.ask) / 2
    def getPriceOverUsd(self, currency):
        if currency=="USD":
            return 1.
        elif currency in ["EUR","GBP","AUD","NZD"]:
            info = mt5.symbol_info(currency+"USD")
            return (info.bid+info.ask)/2
        else:
            info = mt5.symbol_info("USD"+currency)
            if currency=="JPY":
                return 2 / (info.bid + info.ask) * 100
            else:
                return 2 / (info.bid + info.ask)
    def getCommissionRatio(self,symbol):
        info = mt5.symbol_info(symbol)
        price = (info.bid + info.ask)/2
        spread = (info.ask - info.bid)
        commission = self.getPureCommission(symbol)
        #print(spread, commission, price)
        return (spread+commission)/price
    def getPureCommission(self, symbol):
        commission = 0.00004 / self.getPriceOverUsd(symbol[3:])
        return commission
    def getUnit(self, symbol):
        info = mt5.symbol_info(symbol)
        return info.point


    def getDealProfit(self, order_id):

        result = mt5.history_deals_get(position=order_id)
        if result is None:
            result = mt5.history_deals_get(ticket=order_id)
        try:
            return result[-1].profit
        except:
            return 0
    def getOrderPrice(self,order_id):
        result = mt5.positions_get(ticket=order_id)
        print(result)
        return result.price_open

    def sendOrder(self,direction,symbol,qty,price,take_profit=None,stop_loss=None,expiration=None,close_by=None,comment=None,wait_order=True):
        point = mt5.symbol_info(symbol).point
        digits = mt5.symbol_info(symbol).digits
        req = {}
        req["symbol"] = symbol
        req["volume"] = qty
        if price==0:
            req["action"] = mt5.TRADE_ACTION_DEAL
            if direction[0] == "B":
                req["type"] = mt5.ORDER_TYPE_BUY
            elif direction[0] == "S":
                req["type"] = mt5.ORDER_TYPE_SELL
            else:
                raise ValueError
            #req["price"] = round(price,digits)
        else:
            req["action"] = mt5.TRADE_ACTION_PENDING
            req["price"] = round(price,digits)
            if expiration is None:
                req["type_time"] = mt5.ORDER_TIME_GTC
            else:
                req["type_time"] = mt5.ORDER_TIME_SPECIFIED
                req["expiration"] = int(expiration.timestamp())

            if direction[0] == "B":
                req["type"] = mt5.ORDER_TYPE_BUY_LIMIT
            elif direction[0] == "S":
                req["type"] = mt5.ORDER_TYPE_SELL_LIMIT
            else:
                raise ValueError
        if not take_profit is None:
            req["tp"] = round(take_profit,digits)
        if not stop_loss is None:
            req["sl"] = round(stop_loss,digits)
        if not close_by is None:
            req["position"] = close_by
        if not comment is None:
            req["comment"] = str(comment)
        req["type_filling"] = mt5.ORDER_FILLING_FOK
        while True:
            result = mt5.order_send(req)
            time.sleep(0.1)
            if result.retcode==10021:
                print(req)
                print(result)
                print(result.comment)
                time.sleep(3)
                continue
            elif result.comment != "Request executed":
                print(req)
                print(result)
                print(result.comment)
                if wait_order: continue
                raise Exception("Order rejected")
            return result.order, result.price
    def orderCancel(self,symbol,orderId):
        req = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": orderId
        }
        result = mt5.order_send(req)
        print(result.comment)
    #def orderModify(self,symbol,orderId,):

    def getPositions(self,symbol=None,order_id=None):
        if not symbol is None:
            result = mt5.positions_get(symbol=symbol)
        elif not order_id is None:
            result = mt5.positions_get(ticket=order_id)
        else:
            result = mt5.positions_get()
        #print(result)
        positions = []
        for position in result:
            #print(position)
            #print(position.symbol)
            #print(position.identifier)
            v = position.volume
            if position.type==1:
                v *= -1
            #print(position.volume)
            positions.append({
                "symbol":position.symbol,
                "ticket":position.identifier,
                "volume":v
            })
        return positions
    def getLongInterest(self,symbol):
        result = mt5.symbol_info(symbol)
        return result.swap_long
    def getShortInterest(self,symbol):
        result = mt5.symbol_info(symbol)
        return result.swap_short
    def tradeAvailable(self, symbol):
        result = mt5.symbol_info(symbol)
        #print(result)
        return result.trade_mode==mt5.SYMBOL_TRADE_MODE_FULL

    def isMarketOpen(self,timeafter=datetime.timedelta(seconds=0)):
        checktick = datetime.datetime.utcnow()+timeafter
        if 20*60+30<checktick.hour*60+checktick.minute<21*60+30:
            return False
        elif checktick.weekday()==6 and checktick.hour*60+checktick.minute<21*60+30:
            return False
        elif checktick.weekday()==5:
            return False
        elif checktick.weekday() == 4 and checktick.hour * 60 + checktick.minute > 20 * 60 + 30:
            return False
        else:
            return True


    def getChart(self,symbol,interval,start_t=None,end_t=None,dst_adjust=None,length=99999):
        if interval=="1m":
            interval = mt5.TIMEFRAME_M1
            delta = datetime.timedelta(minutes=1)
        elif interval=="5m":
            interval = mt5.TIMEFRAME_M5
            delta = datetime.timedelta(minutes=5)
        elif interval=="15m":
            interval = mt5.TIMEFRAME_M15
            delta = datetime.timedelta(minutes=15)
        elif interval=="30m":
            interval = mt5.TIMEFRAME_M30
            delta = datetime.timedelta(minutes=30)
        elif interval=="1h" or interval=="60m":
            interval = mt5.TIMEFRAME_H1
            delta = datetime.timedelta(minutes=60)
        elif interval=="2h" or interval=="120m":
            interval = mt5.TIMEFRAME_H2
            delta = datetime.timedelta(minutes=120)
        elif interval=="3h" or interval=="180m":
            interval = mt5.TIMEFRAME_H3
            delta = datetime.timedelta(minutes=180)
        elif interval=="4h" or interval=="240m":
            interval = mt5.TIMEFRAME_H4
            delta = datetime.timedelta(minutes=240)
        elif interval=="6h" or interval=="360m":
            interval = mt5.TIMEFRAME_H6
            delta = datetime.timedelta(minutes=360)
        elif interval=="1d" or interval=="24h":
            interval = mt5.TIMEFRAME_D1
            delta = datetime.timedelta(days=1)
        elif interval=="1w" or interval=="7d" or interval=="168h":
            interval = mt5.TIMEFRAME_W1
            delta = datetime.timedelta(days=7)
        else:
            raise NotImplementedError
        while True:
            if not start_t is None:
                if not end_t is None:
                    result = mt5.copy_rates_from(symbol, interval, end_t, int((end_t - start_t)/delta+0.999))
                else:
                    # TODO
                    result = mt5.copy_rates_from_pos(symbol, interval, 0, int((datetime.datetime.utcnow()+datetime.timedelta(hours=12)+self.time_offset - start_t)/delta+0.999))
            else:
                if not end_t is None:
                    result = mt5.copy_rates_from(symbol, interval, end_t, length)
                else:
                    result = mt5.copy_rates_from_pos(symbol, interval, 0, length)
            if not result is None:
                break
            time.sleep(5)
        chart = {"t":[],"o":[],"h":[],"l":[],"c":[],"sp":[]}
        tick_size = mt5.symbol_info(symbol).trade_tick_size
        for r in result:
            chart["sp"].append(float(r[6])*tick_size)
            # Align with UTC first
            if getDst("US",datetime.datetime.fromtimestamp(r[0])):
                chart["t"].append(datetime.datetime.fromtimestamp(r[0])-datetime.timedelta(hours=12))
            else:
                chart["t"].append(datetime.datetime.fromtimestamp(r[0])-datetime.timedelta(hours=11))
            chart["o"].append(float(r[1])+tick_size/2)
            chart["h"].append(float(r[2])+tick_size/2)
            chart["l"].append(float(r[3])+tick_size/2)
            chart["c"].append(float(r[4])+tick_size/2)

        if self.timezone=="KR":
            for ti in range(len(chart["t"])):
                chart["t"][ti] = chart["t"][ti] + datetime.timedelta(hours=9)

        if chart["t"][0] > chart["t"][len(chart["t"]) - 1]:
            chart["t"].reverse()
            chart["o"].reverse()
            chart["h"].reverse()
            chart["l"].reverse()
            chart["c"].reverse()
            chart["sp"].reverse()



        if not dst_adjust is None:
            # Current DST
            if getDst(dst_adjust,datetime.datetime.now()):
                for ti in range(len(chart["t"])):
                    if not getDst(dst_adjust,chart["t"][ti]):
                        chart["t"][ti] = chart["t"][ti]-datetime.timedelta(hours=1)
            # Current not DST
            else:
                for ti in range(len(chart["t"])):
                    if getDst(dst_adjust,chart["t"][ti]):
                        chart["t"][ti] = chart["t"][ti]+datetime.timedelta(hours=1)
        return chart
