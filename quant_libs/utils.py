from math import exp
import datetime

def singleton(cls):
    instances = {}
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance

def avg(l):
    if len(l)==0: return 0
    return sum(l)/len(l)

def stdev(l):
    if len(l)<=1: return 0
    m = avg(l)
    return (sum((ll-m)**2 for ll in l)/len(l))**0.5

def interquartile(l):
    if len(l)==0: return 0
    elif len(l)==1: return [l]*3
    elif len(l)==2: return [min(l), (l[0]+l[1])/2, max(l)]
    ll = l[:]
    ll.sort()
    return [ll[len(ll)//4], ll[len(ll)//2], ll[len(ll)*3//4]]


def positiveRatio(l):
    if len(l) == 0: return 0
    return sum(ll > 0 for ll in l) / len(l)

def sign(n):
    if n > 0:
        return 1
    elif n < 0:
        return -1
    else:
        return 0

def transpose(l_2d):
    n_row = len(l_2d)
    n_col = len(l_2d[0])
    transposed = []
    for c in range(n_col):
        row = [l_2d[r][c] for r in range(n_row)]
        transposed.append(row[:])
    return transposed[:]

def sigmoid(x):
    return 1 / (1 + exp(-x))

def getDst(region,tick):
    # In Seoul time
    if region=="US":
        if datetime.datetime(2026,3,8)<tick<datetime.datetime(2026,11,1):
            return True
        elif datetime.datetime(2025,3,9)<tick<datetime.datetime(2025,11,2):
            return True
        elif datetime.datetime(2024,3,10)<tick<datetime.datetime(2024,11,3):
            return True
        elif datetime.datetime(2023,3,12)<tick<datetime.datetime(2023,11,5):
            return True
        elif datetime.datetime(2022,3,13)<tick<datetime.datetime(2022,11,6):
            return True
        elif datetime.datetime(2021,3,14)<tick<datetime.datetime(2021,11,7):
            return True
    elif region=="EU":
        if datetime.datetime(2026,3,29)<tick<datetime.datetime(2026,10,27):
            return True
        elif datetime.datetime(2025,3,30)<tick<datetime.datetime(2025,10,26):
            return True
        elif datetime.datetime(2024,3,21)<tick<datetime.datetime(2024,10,27):
            return True
        elif datetime.datetime(2023,3,26)<tick<datetime.datetime(2023,10,29):
            return True
        elif datetime.datetime(2022,3,27)<tick<datetime.datetime(2022,10,30):
            return True
        elif datetime.datetime(2021,3,28)<tick<datetime.datetime(2021,10,31):
            return True
        elif datetime.datetime(2020,3,29)<tick<datetime.datetime(2020,10,25):
            return True
        elif datetime.datetime(2019,3,31)<tick<datetime.datetime(2019,10,27):
            return True
        elif datetime.datetime(2018,3,25)<tick<datetime.datetime(2018,10,28):
            return True
        elif datetime.datetime(2017,3,26)<tick<datetime.datetime(2017,10,29):
            return True
        elif datetime.datetime(2016,3,27)<tick<datetime.datetime(2016,10,30):
            return True
        elif datetime.datetime(2015,3,29)<tick<datetime.datetime(2015,10,31):
            return True
        elif datetime.datetime(2014,3,30)<tick<datetime.datetime(2014,10,25):
            return True
        elif datetime.datetime(2013,3,31)<tick<datetime.datetime(2013,10,27):
            return True
        elif datetime.datetime(2012,3,25)<tick<datetime.datetime(2012,10,28):
            return True
        elif datetime.datetime(2011,3,27)<tick<datetime.datetime(2011,10,30):
            return True
        elif datetime.datetime(2010,3,28)<tick<datetime.datetime(2010,10,31):
            return True
    elif region=="AU":
        if datetime.datetime(2023,10,1)<tick<datetime.datetime(2024,4,7):
            return True
        elif datetime.datetime(2022,10,2)<tick<datetime.datetime(2023,4,2):
            return True
        elif datetime.datetime(2021,10,3)<tick<datetime.datetime(2022,4,3):
            return True
    elif region=="NZ":
        if datetime.datetime(2023,9,24)<tick<datetime.datetime(2024,4,7):
            return True
        elif datetime.datetime(2022,9,25)<tick<datetime.datetime(2023,4,2):
            return True
        elif datetime.datetime(2021,9,26)<tick<datetime.datetime(2022,4,3):
            return True

    return False

def trimDictChart(chart, from_date, to_date):
    keys = list(chart)
    #keys.remove("t")
    for ti in reversed(range(len(chart["t"]))):
        if chart["t"][ti] > to_date or chart["t"][ti] < from_date:
            for k in keys:
                del chart[k][ti]
    return chart