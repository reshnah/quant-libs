from quant_libs.utils import *
import sys

@singleton
class IndicatorSetting:
    def __init__(self):
        self.return_dict = False

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

def stochastic(chart, params=[12,26,9]):
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
    if IndicatorSetting().return_dict:
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

def macd(chart, params=[12,26,9]):
    
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
    if IndicatorSetting().return_dict:
        return {"MACD":MACD[:],"signal":MACD_signal[:],"hist":MACD_hist[:]}
    else:
        return (MACD[:],MACD_signal[:],MACD_hist[:])
    
def atr(chart, params=[14]):
    
    param = params[0]   # 14
    ATR = []
    trs = []
    for ti in range(len(chart["c"])):
        tr = max(chart["h"][ti], chart["c"][max(0, ti-1)])-min(chart["l"][ti], chart["c"][max(0, ti-1)])
        if ti == 0:
            ATR.append(tr)
            trs = [tr]*param
        else:
            # ATR.append((ATR[-1]*(param-1)+tr)/param)
            trs = [tr]+trs[:-1]
            ATR.append(sum(trs)/param)
    return ATR[:]

def adx(chart, params=[14]):
    # KW verified
    param = params[0]   # 14
    
    ATR = atr(chart, params)

    ADX = []
    PDI = []
    NDI = []
    pdms = [0]*param
    ndms = [0]*param
    pdis = [0]*param
    ndis = [0]*param
    apdm = 50
    andm = 50
    for ti in range(len(chart["c"])):
        um = chart["h"][ti]-chart["h"][max(ti-1,0)]
        dm = chart["l"][max(ti-1, 0)]-chart["l"][ti]
        if (um>dm)&(um>0): pdm = um
        else: pdm = 0
        if (dm>um)&(dm>0): ndm = dm
        else: ndm = 0
        #pdms = [pdm]+pdms[:-1]
        #ndms = [ndm]+ndms[:-1]
        #pdis = [pdm/ATR[ti]*100]+pdis[:-1]
        #ndis = [ndm/ATR[ti]*100]+ndis[:-1]
        # SMA
        #apdm = sum(pdms)/param
        #andm = sum(ndms)/param
        # MA
        #apdm = (apdm*(param-1)+pdm)/param
        #andm = (andm*(param-1)+ndm)/param
        # EMA
        apdm = (pdm+apdm*(((param+1)/2)-1))/((param+1)/2)
        andm = (ndm+andm*(((param+1)/2)-1))/((param+1)/2)
        try:
            PDI.append(apdm*100/ATR[ti])
            NDI.append(andm*100/ATR[ti])
            if False:
                if len(PDI)==0:
                    PDI.append(pdm/ATR[ti]*100)
                    NDI.append(ndm/ATR[ti]*100)
                else:
                    # EMA
                    PDI.append((pdm/ATR[ti]*100+PDI[-1]*(((param+1)/2)-1))/((param+1)/2))
                    NDI.append((ndm/ATR[ti]*100+NDI[-1]*(((param+1)/2)-1))/((param+1)/2))
                    # Smoothed MA
                    #PDI.append((pdm/ATR[ti]*100+PDI[-1]*(param-1))/param)
                    #NDI.append((ndm/ATR[ti]*100+NDI[-1]*(param-1))/param)
            #PDI.append(sum(pdis)/param)
            #NDI.append(sum(ndis)/param)

            #PDI.append(sum(pdms)*100/sum(ATR[max(ti-param,0):ti]))
            #NDI.append(sum(ndms)*100/sum(ATR[max(ti-param,0):ti]))
        except ZeroDivisionError:
            #print("ZeroDivisionError",apdm,andm)
            PDI.append(0)
            NDI.append(0)
        if ti==0:
            ADX.append(100*abs((PDI[-1]-NDI[-1])/(PDI[-1]+NDI[-1]+0.00001)))
        else:
            #ADX.append((ADX[-1]*(param-1)+100*abs((PDI[-1]-NDI[-1])/(PDI[-1]+NDI[-1]+0.00001)))/param)
            # EMA
            ADX.append((ADX[-1]*(((param+1)/2)-1)+100*abs((PDI[-1]-NDI[-1])/(PDI[-1]+NDI[-1]+0.00001)))/((param+1)/2))
    if IndicatorSetting().return_dict:
        return {"ADX":ADX[:], "PDI":PDI[:], "NDI":NDI[:]}
    else:
        return (ADX[:], PDI[:], NDI[:])
    
def bollingerBand(chart, params=[14, 2]):
    period = params[0]   # 14
    stdmult = params[1]  # 2

    upper = []
    lower = []
    pb = []
    for ti in range(len(chart["c"])):
        if ti==0:
            sma = chart["c"][ti]
            ema = chart["c"][ti]
            s = 0
        else:
            sma = sum(chart["c"][max(0,ti-period+1):ti+1])/(ti+1-max(0,ti-period+1))
            ema = (chart["c"][ti]+ema*(((period+1)/2)-1))/((period+1)/2)
            s = stdev(chart["c"][max(0,ti-period+1):ti+1])
        upper.append(ema+s*stdmult)
        lower.append(ema-s*stdmult)
        if upper[-1]==lower[-1]:
            pb.append(0.5)
        else:
            pb.append((chart["c"][ti]-lower[-1])/(upper[-1]-lower[-1]))
    if IndicatorSetting().return_dict:
        return {"upper":upper[:], "lower":lower[:],"pb":pb[:]}
    else:
        return (upper[:], lower[:], pb[:])
    
def williamsPR(chart, params=[14]):
    # KW verified
    param = params[0]   # 14
    Williams = []
    for ti in range(len(chart["c"])):
        Williams.append((max(chart["h"][max(0, ti-param+1):ti+1])-chart["c"][ti])/(
        max(chart["h"][max(0, ti-param+1):ti+1])-min(chart["l"][max(0, ti-param+1):ti+1])+0.0001)*-100)
    return Williams[:]
def ultimateOsc(chart, params=[14, 21, 28]):
    bps = [chart["c"][0]-chart["l"][0]]*max(params)
    trs = [chart["h"][0]-chart["l"][0]]*max(params)
    UO = []
    for ti in range(len(chart["c"])):
        bps = [chart["c"][ti]-min(chart["c"][max(0, ti-1)], chart["l"][ti])]+bps[0:-1]
        trs = [max(chart["c"][max(0, ti-1)], chart["h"][ti])-min(chart["c"][max(0, ti-1)], chart["l"][ti])]+trs[0:-1]
        avg0 = sum(bps[0:params[0]])/sum(trs[0:params[0]] + [0.00001])
        avg1 = sum(bps[0:params[1]])/sum(trs[0:params[1]] + [0.00001])
        avg2 = sum(bps[0:params[2]])/sum(trs[0:params[2]] + [0.00001])
        UO.append(100*(avg0*4+avg1*2+avg2*1)/7)
    return UO[:]

def awesomeOsc(chart, params=[5,34]):
    AO = []
    ma0 = 0
    ma1 = 0
    for ti in range(len(chart["c"])):
        if ti == 0:
            ma0 = (chart["h"][ti]+chart["l"][ti])/2
            ma1 = (chart["h"][ti]+chart["l"][ti])/2
        else:
            ma0 = (ma0*(params[0]-1)+(chart["h"][ti]+chart["l"][ti])/2)/params[0]
            ma1 = (ma1*(params[1]-1)+(chart["h"][ti]+chart["l"][ti])/2)/params[1]
        AO.append(ma0-ma1)
    return AO[:]

def bullBearPower(chart, params=[7]):
    param = params[0]   # 7
    bulls = []
    bears = []
    ma = 0
    for ti in range(len(chart["c"])):
        if ti == 0:
            ma = chart["c"][ti]
        else:
            ma = (ma*((param+1)/2-1)+chart["c"][ti])/((param+1)/2)
        bulls.append(chart["h"][ti]-ma)
        bears.append(ma-chart["l"][ti])
    if IndicatorSetting().return_dict:
        return {"bulls":bulls[:],"bears":bears[:]}
    else:
        return (bulls[:],bears[:])
    
def ichimokuCloud(chart, params=[9, 26,52]):
    conversion_period = params[0]   # 9
    base_period = params[1] # 26
    span_period = params[2] # 52
    lag = params[3] # 26
    span_a = []
    span_b = []
    c_line = [] # Conversion Line
    b_line = [] # Base Line
    for ti in range(len(chart["c"])):
        pl = min(chart["l"][max(0,ti-conversion_period+1):ti+1])
        ph = max(chart["h"][max(0,ti-conversion_period+1):ti+1])
        cl = (ph+pl)/2
        pl = min(chart["l"][max(0,ti-base_period+1):ti+1])
        ph = max(chart["h"][max(0,ti-base_period+1):ti+1])
        bl = (ph+pl)/2
        c_line.append(cl)
        b_line.append(bl)
        span_a.append((cl+bl)/2)
        pl = min(chart["l"][max(0,ti-span_period+1):ti+1])
        ph = max(chart["h"][max(0,ti-span_period+1):ti+1])
        span_b.append((ph+pl)/2)
        lagging_span = 0    # TODO
    #c_line = [c_line[0]]*base_period+c_line[:-base_period]
    #b_line = [b_line[0]]*base_period+b_line[:-base_period]
    span_a = [span_a[0]]*(lag-1)+span_a[:-lag+1]
    span_b = [span_b[0]]*(lag-1)+span_b[:-lag+1]

    if IndicatorSetting().return_dict:
        return {"spanA":span_a[:], "spanB":span_b[:], "base":b_line[:],"conv":c_line[:]}
    else:
        return (span_a[:], span_b[:])
def moneyFlowIndex(chart, params):
    # KW verified
    period= params[0]
    typicals = []
    #mfs = []
    mfis = []
    for ti in range(len(chart["c"])):
        typicals.append((chart["h"][ti]+chart["l"][ti]+chart["c"][ti])/3)
        #mfs.append(typicals[ti]*chart["v"][ti])
    for ti in range(len(chart["c"])):
        pmf = 0
        nmf = 0
        for tii in range(max(1,ti-period+1),ti+1):
            if typicals[tii]>typicals[tii-1]:
                pmf += typicals[tii]*chart["v"][tii]
            elif typicals[tii]<typicals[tii-1]:
                nmf += typicals[tii]*chart["v"][tii]
        mfis.append(100*(pmf/(pmf+nmf+0.0000001)))
    return mfis[:]

def obvOscillator(chart, params):
    period= params[0]
    obvs = [0]
    for ti in range(1,len(chart["c"])):
        if chart["c"][ti]>chart["c"][ti-1]:
            obvs.append(obvs[-1]+chart["v"][ti])
        elif chart["c"][ti]<chart["c"][ti-1]:
            obvs.append(obvs[-1]-chart["v"][ti])
        else:
            obvs.append(obvs[-1])

    period = params[0]
    mult = 2/(period+1)
    ema = [sum(obvs[0:period])/period]*period
    for c in obvs[period:]:
        ema.append((c-ema[-1])*mult+ema[-1])
    obvoscs = []
    for ti in range(len(chart["c"])):
        obvoscs.append(ema[ti]-obvs[ti])
    return obvoscs[:]

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
    if len(ticks) <= 1:
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
    if len(profits_by_t)<=1: return 0
    return sum(profits_by_t)/len(profits_by_t)/stdev(profits_by_t)
