import requests
import pandas as pd
import datetime
import FinanceDataReader as fdr
import pykrx
import os
import time
from bisect import bisect_right
import yfinance as yf


def getUsTickers(listed_idx=None):
    if listed_idx is None:
        listed_idx = ["DJ", "NQ100", "SP500"]
    tickers = []
    if "DJ" in listed_idx:
        url = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
        tickers = list(set(tickers + getWikiTickers(url, 2, "Symbol")))
    if "NQ100" in listed_idx:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        tickers = list(set(tickers + getWikiTickers(url, 4, "Ticker")))
    if "SP500" in listed_idx:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tickers = list(set(tickers + getWikiTickers(url, 0, "Symbol")))

    return tickers[:]

def getKospi200Tickers():
    return getWikiTickers("https://en.wikipedia.org/wiki/KOSPI_200", 2, "Symbol")

def getWikiTickers(url, table_idx, table_column):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    response = requests.get(url, headers=headers)
    t = list(pd.read_html(response.text,
                          converters={table_column: str}
                          )[table_idx][table_column])
    tickers = list(set(t))
    return [t.replace(".", "-") for t in tickers]

def getChart(ticker,from_date,to_date=None):
    if isinstance(from_date, datetime.datetime):
        from_date = from_date.strftime("%Y-%m-%d")
    if isinstance(to_date, datetime.datetime):
        to_date = to_date.strftime("%Y-%m-%d")
    elif to_date is None:
        to_date = datetime.datetime.now().strftime("%Y-%m-%d")
    if "_" in ticker:
        if len(ticker)==7:
            ticker = ticker.replace("_","/")
        elif len(ticker)==4:
            ticker = ticker.replace("_","=")
    if "." in ticker and ticker[0].isalpha():
        ticker = ticker.replace(".", "-")
    for trial in range(5):
        try:
            df = fdr.DataReader(ticker, from_date, to_date)
            chart = {}
            chart["t"] = list(df.index)
            chart["o"] = list(df["Open"])
            chart["h"] = list(df["High"])
            chart["l"] = list(df["Low"])
            chart["c"] = list(df["Close"])
            chart["v"] = list(df["Volume"])
            if "Adj Close" in df:
                chart["ac"] = list(df["Adj Close"])
            return chart
        except (requests.exceptions.HTTPError,
                ConnectionError,
                ConnectionAbortedError,
                ConnectionRefusedError,
                ConnectionAbortedError) as err:
            print("Server Error: %s"%err)
            if "Not Found for url" in err: break
            time.sleep(3)
            continue
    return None


def exportCharts(dst_dir, tickers, from_date,to_date=None,mute=False,prefix="",refresh_tick=None):
    for i, ticker in enumerate(tickers):
        if not mute:
            print("Exporting %s (%d/%d)     "%(ticker, i+1, len(tickers)), end="\r")
        fname = dst_dir + prefix + ticker + ".csv"
        if not refresh_tick is None:
            if os.path.isfile(fname):
                creation_time = datetime.datetime.fromtimestamp(os.path.getmtime(fname))
                needs_update = creation_time <= refresh_tick
                if not needs_update:
                    print("exportRefCharts(): created at %s, last_market %s -> needs_update=%s"%(creation_time, refresh_tick, needs_update))
                    continue
                os.system("del /Q %s"%fname)
            #else:
                
                #print("file not exist")

        c = getChart(ticker, from_date, to_date)
        if c is None: continue
        fout = open(dst_dir + prefix + ticker + ".csv", "w")
        fout.writelines("Date,Price,Open,High,Low,Volume")
        if "ac" in c:
            ac = c["ac"]
            fout.writelines(",AdjClose")
        fout.writelines("\n")
        p = c["c"]
        o = c["o"]
        h = c["h"]
        l = c["l"]
        v = c["v"]
        t = c["t"]
        
        if "ac" in c:
            for ti in range(len(p)):
                fout.writelines("\"%04d-%02d-%02d\",\"%f\",\"%f\",\"%f\",\"%f\",\"%f\",\"%f\"\n" % (
                    t[ti].year, t[ti].month, t[ti].day,
                    p[ti], o[ti], h[ti], l[ti], v[ti], ac[ti]))
        else:
            for ti in range(len(p)):
                fout.writelines("\"%04d-%02d-%02d\",\"%f\",\"%f\",\"%f\",\"%f\",\"%f\"\n" % (
                    t[ti].year, t[ti].month, t[ti].day,
                    p[ti], o[ti], h[ti], l[ti], v[ti]))
        fout.close()
    if not mute:
        print("")
    return

    if isinstance(from_date, datetime.datetime):
        from_date = from_date.strftime("%Y-%m-%d")
    if isinstance(to_date, datetime.datetime):
        to_date = to_date.strftime("%Y-%m-%d")
    elif to_date is None:
        to_date = datetime.datetime.now().strftime("%Y-%m-%d")
    for ti in range(len(tickers)):
        if "_" in tickers[ti]:
            if len(tickers[ti])==7:
                tickers[ti] = tickers[ti].replace("_","/")
            elif len(tickers[ti])==4:
                tickers[ti] = tickers[ti].replace("_","=")
    result = yf.download(tickers, start=from_date, end=to_date)
    for ticker in tickers:
        fout = open(dst_dir + ticker + ".csv", "w")
        fout.writelines("Date,Price,Open,High,Low,Volume\n")
        p = result["Close"][ticker]
        o = result["Open"][ticker]
        h = result["High"][ticker]
        l = result["Low"][ticker]
        v = result["Volume"][ticker]
        # print(p.index)
        # input()
        for ti in range(len(p)):
            fout.writelines("\"%04d-%02d-%02d\",\"%f\",\"%f\",\"%f\",\"%f\",\"%f\"\n" % (
                p.index[ti].year, p.index[ti].month, p.index[ti].day,
                p.iloc[ti], o.iloc[ti], h.iloc[ti], l.iloc[ti], v.iloc[ti]))
        fout.close()

def getEtfList():
    date = datetime.datetime.now()
    if date.weekday()>=5:
        date -= datetime.timedelta(days=date.weekday()-4)
    date = date.strftime("%Y%m%d")
    etfs = list(pykrx.stock.get_etf_ticker_list(date))
    return etfs

def getKrxEtfName(code):
    return pykrx.stock.get_etf_ticker_name(code)

def getKrxTopCapList(num, date=None):
    if date is None:
        date = datetime.datetime.now()
        if date.weekday()>=5:
            date -= datetime.timedelta(days=date.weekday()-4)
        date = date.strftime("%Y%m%d")
    for trial in range(7):
        try:
            df = pykrx.stock.get_market_cap(date)
        except:
            date -= datetime.timedelta(days=1)
            continue
        break
    else:
        raise ValueError
    return list(df.index)[:num]

def getKrxTopForeignRatioList(num, date=None):
    if date is None:
        date = datetime.datetime.now()
        if date.weekday()>=5:
            date -= datetime.timedelta(days=date.weekday()-4)
        date = date.strftime("%Y%m%d")
    for trial in range(7):
        try:
            df = pykrx.stock.get_exhaustion_rates_of_foreign_investment(date, "KOSPI")
        except:
            date -= datetime.timedelta(days=1)
            continue
        break
    else:
        raise ValueError
    df1 = pykrx.stock.get_exhaustion_rates_of_foreign_investment(date, "KOSDAQ")
    df = pd.concat([df, df1])
    df = df.sort_values(by=['지분율'], ascending=False)
    return list(df.index)[:num]


def getKrxTopVolumeList(num, date=None):
    if date is None:
        date = datetime.datetime.now()
        if date.weekday()>=5:
            date -= datetime.timedelta(days=date.weekday()-4)
        date = date.strftime("%Y%m%d")
    
    for trial in range(7):
        try:
            df = pykrx.stock.get_market_cap(date)
        except:
            date -= datetime.timedelta(days=1)
            continue
        break
    else:
        raise ValueError
    df = df.sort_values(by=['거래대금'], ascending=False)
    return list(df.index)[:num]




_SNP500_HISTORY_URL = (
    "https://raw.githubusercontent.com/chinobing/"
    "historical_sp500_constituents/main/sp_500_historical_components.csv"
)


def _load_snp500_history():
    df = pd.read_csv(_SNP500_HISTORY_URL)

    # Normalize column names.
    df.columns = [
        str(column).strip().lower()
        for column in df.columns
    ]

    # Locate date column.
    date_column = next(
        (c for c in df.columns if c in ("date", "datetime", "timestamp")),
        None,
    )

    if date_column is None:
        raise ValueError(
            f"Could not find date column. Columns: {list(df.columns)}"
        )

    df[date_column] = pd.to_datetime(df[date_column])

    # Locate ticker column.
    ticker_column = next(
        (
            c
            for c in df.columns
            if c in ("ticker", "symbol", "constituent", "tickers")
        ),
        None,
    )

    if ticker_column is None:
        raise ValueError(
            f"Could not find ticker column. Columns: {list(df.columns)}"
        )

    date_list = []
    member_list = []
    for dt, group in df.groupby(date_column):
        tickers_set = set()
        for raw_entry in group[ticker_column]:
            if pd.notna(raw_entry):
                for t in str(raw_entry).split(","):
                    t_clean = t.strip().replace(".", "-")
                    if t_clean:
                        tickers_set.add(t_clean)
        date_list.append(pd.Timestamp(dt))
        member_list.append(sorted(tickers_set))

    sorted_pairs = sorted(zip(date_list, member_list), key=lambda x: x[0])
    dates = [p[0] for p in sorted_pairs]
    members = [p[1] for p in sorted_pairs]
    return dates, members


_SNP500_DATES, _SNP500_MEMBERS = _load_snp500_history()


def getSnp500Tickers(tick: datetime.datetime) -> list[str]:
    tick = pd.Timestamp(tick)

    i = bisect_right(_SNP500_DATES, tick) - 1

    if i < 0:
        raise ValueError(
            f"No S&P 500 constituent data available for {tick.date()}"
        )
    return list(_SNP500_MEMBERS[i])

def getUsHistoricalEpsBvps(ticker_symbol: str, freq: str = "quarterly"):
    """
    Fetches historical EPS and computes BVPS.
    freq: 'quarterly' or 'annual'
    """
    ticker = yf.Ticker(ticker_symbol)
    
    if freq == "quarterly":
        income_stmt = ticker.quarterly_income_stmt
        balance_sheet = ticker.quarterly_balance_sheet
    else:
        income_stmt = ticker.income_stmt
        balance_sheet = ticker.balance_sheet
        
    df = pd.DataFrame()
    
    # 1. EPS (Diluted EPS is standard)
    if "Diluted EPS" in income_stmt.index:
        df["EPS"] = income_stmt.loc["Diluted EPS"]
    elif "Basic EPS" in income_stmt.index:
        df["EPS"] = income_stmt.loc["Basic EPS"]
        
    # 2. Book Value per Share (BVPS)
    # Total Stockholder Equity / Ordinary (or Diluted) Shares Number
    equity_row = None
    for row_name in ["Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity"]:
        if row_name in balance_sheet.index:
            equity_row = row_name
            break
            
    shares_row = None
    for row_name in ["Diluted Average Shares", "Ordinary Shares Number", "Basic Average Shares"]:
        if row_name in income_stmt.index:
            shares_row = income_stmt.loc[row_name]
            break
        elif row_name in balance_sheet.index:
            shares_row = balance_sheet.loc[row_name]
            break

    if equity_row is not None and shares_row is not None:
        equity = balance_sheet.loc[equity_row]
        df["Stockholders_Equity"] = equity
        df["Shares_Outstanding"] = shares_row
        df["BVPS"] = equity / shares_row

    # Clean and sort by date ascending
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df

def test():
    getKospi200Tickers()

if __name__=="__main__":
    test()