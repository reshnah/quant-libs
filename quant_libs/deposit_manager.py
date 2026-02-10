
from dataclasses import dataclass, asdict, fields
import datetime
from typing import Optional
import os
import csv

class TradeRecords:
    auto_backup: bool
    records: list
    closed_records: list

    record_name: str

    def __init__(self, fname = None):
        self.record_name = fname
        self.auto_backup = True
        self.closed_records = []
        self.records = []
        if not fname is None and os.path.isfile(self.record_name):
            self.load()

    def setRecordName(self, fname):
        self.record_name = fname
        return
    
    def newRecord(self, ticker, quantity, direction, entry_price=0, executed=False, entry_date=None, order_id="", close_date=None):
        if entry_date is None:
            entry_date = datetime.datetime.now()
        if close_date is None:
            close_date = datetime.datetime(1970, 1, 1)
        record = TradeRecord(ticker=ticker,
                             quantity=quantity,
                             entry_price=entry_price,
                             order_id=str(order_id),
                             executed=executed,
                             direction=direction,
                             entry_date=entry_date,
                             close_date=close_date)
        self.records.append(record)
        if self.auto_backup:
            self.backup()

    def getExpired(self):
        to_return = []
        for record in self.records:
            if record.needToClose():
                to_return.append(record)
        return to_return[:]
    
    def close(self, order_id, close_price: float, close_date=None):
        order_id = str(order_id)
        for record in self.records:
            if record.order_id==order_id:
                record.close(close_price, close_date)
                break
        if self.auto_backup:
            self.backup()
    
    def markExecuted(self, order_id: str, entry_price: float, entry_date=None):
        order_id = str(order_id)
        if entry_date is None:
            entry_date = datetime.datetime.now()
        for record in self.records:
            if record.order_id==order_id:
                record.entry_price = entry_price
                record.entry_date=entry_date
                break
        if self.auto_backup:
            self.backup()


    def getWaiting(self):
        to_return = []
        for record in self.records:
            if not record.executed:
                to_return.append(record)
        return to_return[:]
    def getHolding(self):
        to_return = []
        for record in self.records:
            if record.executed:
                to_return.append(record)
        return to_return[:]
    def getClosed(self):
        return self.closed_records[:]
    

    def backup(self):
        if self.record_name is None:
            print("Record name is not set")
            return
        headers = [f.name for f in fields(TradeRecord)]

        with open(self.record_name, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            # asdict() turns the object into a dict that DictWriter understands
            for record in self.closed_records+self.records:
                # Create a copy of the data to avoid modifying the live object
                row = asdict(record)
                # Convert datetime to string: "2026-02-10T22:38:50"
                row['entry_date'] = datetime.datetime.strftime(row['entry_date'],"%Y-%m-%d %H:%M:%S")
                row['close_date'] = datetime.datetime.strftime(row['close_date'],"%Y-%m-%d %H:%M:%S")
                writer.writerow(row)
        

    def load(self):
        if self.record_name is None:
            print("Record name is not set")
            return
        print("load()")

        with open(self.record_name, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Note: CSV stores everything as strings. 
                # We must convert numbers back to float/int manually.
                record = TradeRecord(
                    ticker=row['ticker'],
                    direction=int(row['direction']),
                    entry_price=float(row['entry_price']),
                    entry_date=datetime.datetime.strptime(row['entry_date'],"%Y-%m-%d %H:%M:%S"),
                    close_price=float(row["close_price"]),
                    stoploss_price=float(row["stoploss_price"]),
                    close_date=datetime.datetime.strptime(row['close_date'],"%Y-%m-%d %H:%M:%S"),
                    executed=row["executed"]=="True",
                    closed=row["closed"]=="True",
                    #deposit_used=float(row['deposit_used']),
                    #exit_price=float(row['exit_price']),
                    quantity=float(row["quantity"]),
                    order_id=row["order_id"]
                )
                if record.closed:
                    self.closed_records.append(record)
                else:
                    self.records.append(record)


@dataclass
class TradeRecord:
    ticker: str = None
    direction: int = 0
    entry_price: float = 0
    entry_date: datetime.datetime = datetime.datetime(1970, 1, 1)
    close_price: float = 0
    stoploss_price: float = 0
    close_date: datetime.datetime = datetime.datetime(1970, 1, 1)
    executed: bool = False
    closed: bool = False
    #deposit_used: float
    #leverage: float = 1.
    quantity: float = 0
    order_id: str = ""

    def getPnl(self, current_price: float = 0):
        if self.closed:
            return (self.close_price - self.entry_price) / self.entry_price
        else:
            return (current_price - self.entry_price) / self.entry_price

    def needToClose(self, cur_price=0):
        if self.closed:
            return False
        if (self.close_date is None) and (self.close_price is None) and (self.stoploss_price is None):
            return False
        print(self.close_date)
        if self.close_date < datetime.datetime.now():
            return True
        if not self.close_price is None:
            if self.close_price*self.direction > cur_price*self.direction:
                return True
        if not self.stoploss_price is None:
            if self.stoploss_price*self.direction < cur_price*self.direction:
                return True
        return False
            
    def close(self, close_price, close_date=None):
        if close_date is None:
            close_date = datetime.datetime.now()
        self.close_price = close_price
        self.close_date = close_date
        self.closed = True