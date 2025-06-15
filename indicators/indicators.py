

def rsi(chart, params=[14]):
    arr = []
    avg_gain = 0
    avg_loss = 0
    for ti in range(len(chart["c"])):
        u_sum = max(chart["c"][ti]-chart["c"][max(0, ti-1)], 0)
        d_sum = max(chart["c"][max(0, ti-1)]-chart["c"][ti], 0)
        avg_gain = (avg_gain*(params[0]-1.0)+u_sum)/params[0]
        avg_loss = (avg_loss*(params[0]-1.0)+d_sum)/params[0]
        rs = avg_gain/(avg_loss+0.0000000001)
        arr.append(100-100/(1+rs))
    return arr[:]

def stochastic(chart, params=[12,26,9], return_dict=False):
    k = 50
    k_ema = 50
    old_k = 50
    ks = []
    smooth_k = 50
    d = 50
    arr_d = []
    arr_k = []

    for ti in range(len(chart["c"])):
        if ti == 0:
            k = 100*(chart["c"][ti]-chart["l"][ti])/(chart["h"][ti]-chart["l"][ti]+0.0001)
            ks = [k]*params[1]
            smooth_k = k
            k_ema = k
        else:
            k = 100*(chart["c"][ti]-min(chart["l"][max(0, ti-params[0]+1):ti+1]))/(
            max(chart["h"][max(0, ti-params[0]+1):ti+1])-min(chart["l"][max(0, ti-params[0]+1):ti+1])+0.0001)
            k_ema = k*2/(1+params[1])+k_ema*(1-2/(1+params[1]))
            smooth_k = (smooth_k*(params[2]-1)+k)/params[2]
            ks = [k]+ks[:-1]
        d = (k+d*(((params[1]+1)/2)-1))/((params[1]+1)/2)  # kiwoom: geometric mean
        arr_k.append(k)
        arr_d.append(d)
    if return_dict:
        return {"%K":arr_k[:],"%D":arr_d[:]}
    else:
        return (arr_k[:],arr_d[:])

def stochasticRsi(chart, params=[14]):
    arr_rsi = rsi(chart, params[0])
    arr = []
    for ti in range(len(chart["c"])):
        arr.append((arr_rsi[ti]-min(arr_rsi[max(0, ti-params[0]+1):ti+1]))/(
        0.00001+max(arr_rsi[max(0, ti-params[0]+1):ti+1])-min(arr_rsi[max(0, ti-params[0]+1):ti+1]))*100)
    return arr[:]

def cci(chart, params=[9]):
    
    arr = []
    mdev = 0
    tp_ma = (chart["c"][0]+chart["h"][0]+chart["l"][0])/3.0
    mdevs = [mdev]*params[0]
    tps = [tp_ma]*params[0]
    for ti in range(len(chart["c"])):
        tp = (chart["c"][ti]+chart["h"][ti]+chart["l"][ti])/3
        #tps = [tp]+tps[:-1]
        #tp_ma = (tp_ma*(param-1)+tp)/param
        tp_ma = (tp+tp_ma*(((params[0]+1)/2)-1))/((params[0]+1)/2)  # EMA
        #tp_ma = sum(tps)/param
        #mdev = ((param-1)*mdev+abs(tp-tp_ma))/param
        mdev = (abs(tp-tp_ma)+mdev*(((params[0]+1)/2)-1))/((params[0]+1)/2)  # EMA
        #mdevs = [abs(tp-tp_ma)]+mdevs[:-1]
        #mdev = sum(mdevs)/param
        arr.append((tp-tp_ma)/(0.015*mdev+0.0000000001))
    return arr[:]

def macd(chart, params=[12,26,9], return_dict=False):
    
    # KW verified
    param0 = params[0]  # 12
    param1 = params[1]  # 26
    param2 = params[2]  # 9
    MACD = []
    MACD_signal = []
    MACD_hist = []
    ma0 = chart["c"][0]
    ma1 = chart["c"][0]
    for ti in range(len(chart["c"])):
        t0 = (param0+1.0)/2
        t1 = (param1+1.0)/2
        ma0 = (ma0*(t0-1)+chart["c"][ti])/t0
        ma1 = (ma1*(t1-1)+chart["c"][ti])/t1
        MACD.append(ma0-ma1)
        if ti == 0:
            MACD_signal.append(MACD[-1])
        else:
            MACD_signal.append((MACD_signal[-1]*(((param2+1.0)/2)-1)+MACD[-1])/((param2+1.0)/2))
        MACD_hist.append(MACD[-1]-MACD_signal[-1])
    if return_dict:
        return {"MACD":MACD[:],"signal":MACD_signal[:],"hist":MACD_hist[:]}
    else:
        return (MACD[:],MACD_signal[:],MACD_hist[:])

def ema(closes, period):
    mult = 2/(period+1)
    ema = [sum(closes[0:period])/period]*period
    for c in closes[period:]:
        ema.append((c-ema[-1])*mult+ema[-1])
    return ema

def vwap(chart):
    vwaps = []
    cumulative_tpv = 0
    cumulative_v = 0
    # print(len(chart["t"]), chart["t"][0],chart["t"][-1])
    if chart["t"][0].day == chart["t"][-1].day:
        print("Warning@VWAP: Chart is too short to represent correct VWAP")
    for i in range(len(chart["t"])):
        if chart["t"][i].day != chart["t"][i-1].day:
            cumulative_tpv = 0
            cumulative_v = 0
        tp = (chart["h"][i]+chart["l"][i]+chart["c"][i])/3
        cumulative_tpv += tp*chart["v"][i]
        cumulative_v += chart["v"][i]
        if cumulative_v == 0:
            if len(vwaps) != 0:
                vwaps.append(vwaps[-1])
            else:
                vwaps.append(0)
        else:
            vwaps.append(cumulative_tpv/cumulative_v)
    return vwaps

def sign(d):
    if d > 0:
        return 1
    elif d < 0:
        return -1
    else:
        return 0

def sigmoid(x, a=1):
    try:
        return 1/(1+exp(-x*a))
    except:
        print(x)
        raise

def mdd(profits, geometric=True):
    max_deposit = 1.
    deposit = 1.
    mdd = 0.
    for p in profits:
        deposit *= (p+1)
        max_deposit = max(max_deposit, deposit)
        mdd = min(mdd, deposit/max_deposit-1)
    return mdd

def sharpe(profits, ticks, trange, tunit):
    if len(ticks) == 0:
        return 0
    profits_by_t = []
    tick = trange[0]+tunit
    while tick-tunit < trange[1]:
        profit = 0
        while len(ticks) != 0 and ticks[0] < tick:
            profit += profits[0]
            profits = profits[1:]
            ticks = ticks[1:]
        profits_by_t.append(profit)
        tick = tick+tunit

    return sum(profits_by_t)/len(profits_by_t)/stdev(profits_by_t)