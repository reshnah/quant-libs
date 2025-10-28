import requests
import pandas as pd
import datetime
import FinanceDataReader as fdr
import pykrx
import os
import time


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
            return chart
        except (requests.exceptions.HTTPError,
                ConnectionError,
                ConnectionAbortedError,
                ConnectionRefusedError,
                ConnectionAbortedError) as err:
            print("Server Error: %s"%err)
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
        fout.writelines("Date,Price,Open,High,Low,Volume\n")
        p = c["c"]
        o = c["o"]
        h = c["h"]
        l = c["l"]
        v = c["v"]
        t = c["t"]
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

def test():
    getKospi200Tickers()

if __name__=="__main__":
    test()