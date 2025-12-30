from math import exp
import datetime
from quant_libs.logger import *

def avg(l):
    if len(l)==0: return 0
    return sum(l)/len(l)

def min_n(data_list, n):
    """
    Finds the N-th minimum unique value in a list using a single pass (O(N)).

    Args:
        data_list: A list of numbers.
        n: The rank of the minimum to find (e.g., 2 for second minimum).

    Returns:
        The N-th minimum value, or an error message.
    """
    if not isinstance(n, int) or n < 1:
        return "Error: The rank 'n' must be a positive integer."
    
    # 1. Initialize a list to hold the 'n' smallest unique elements found so far.
    # It should be sorted (implicitly maintained) and contain no duplicates.
    n_smallest = [] 

    # 2. Iterate through each number in the input list
    for num in data_list:
        
        # Check if the number is already one of the 'n' smallest unique numbers
        if num in n_smallest:
            continue # Skip duplicates
        
        # Find the correct insertion point to maintain sorted order
        inserted = False
        for i in range(len(n_smallest)):
            if num < n_smallest[i]:
                # Insert the new smaller number at the correct position
                n_smallest.insert(i, num)
                inserted = True
                break
        
        # If the number wasn't smaller than any current element,
        # but the list is not yet full, append it
        if not inserted and len(n_smallest) < n:
            n_smallest.append(num)
        
        # 3. Maintain size constraint: only keep the 'n' smallest
        # If the list is now larger than 'n', remove the largest element (which is at the end)
        if len(n_smallest) > n:
            n_smallest.pop()

    # 4. Check results
    if len(n_smallest) < n:
        return f"Error: The list only contains {len(n_smallest)} unique elements. Cannot find the {n}-th minimum."

    # The N-th minimum is the last element in the 'n_smallest' list (at index n-1)
    return n_smallest[-1]

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

def softThreshold(x, a):
    if x > a:
        return x-a
    elif x < -a:
        return x+a
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

def sigmoid(x, a=1):
    try:
        return 1/(1+exp(-x*a))
    except:
        print(x)
        raise

def wAvg(l, ws):
    if len(l)==0: return 0
    return sum(ll*ww for ll, ww in zip(l, ws)) / sum(ws)

def wStdev(l, ws):
    if len(l)<=1: return 0
    m = wAvg(l, ws)
    return (sum(((ll-m)**2) * ww for ll, ww in zip(l, ws))/sum(ws))**0.5

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

def isKrHoliday(dt):
    holidays = ["241225","250101","250128","250129","250130","250303","250405","250505","250506","250606","250815","251003",
                "251006","251007","251008","251009",]
    dt_str = dt.strftime("%y%m%d")
    return dt_str in holidays

def getNextMonthFirstDate(dt):
    """
    Calculates the first day of the month following the given datetime object.
    Uses only the built-in 'datetime' module.
    """
    current_year = dt.year
    current_month = dt.month

    # Check if the current month is December (12)
    if current_month == 12:
        # If it is December, the next month is January (1) and the year increments
        next_month = 1
        next_year = current_year + 1
    else:
        # Otherwise, the month simply increments, and the year stays the same
        next_month = current_month + 1
        next_year = current_year
    
    # Return a new datetime object set to the calculated year, month, and day 1
    return datetime.datetime(next_year, next_month, 1)

def waitForHms(h, m, s, valid_hour=6):
    while True:
        now = datetime.datetime.now()
        remain = ((h*60*60 + m*60 + s) - (now.hour*60*60 + now.minute*60 + now.second))%(24*60*60)
        remain_h = remain//3600
        remain_m = (remain%3600)//60
        remain_s = (remain%60)
        print(strNow()+"Waiting for %02d:%02d:%02d (%02d:%02d:%02d remain)  "%(h, m, s, remain_h, remain_m, remain_s),end="\r")
        if (h*60*60 + m*60 + s <= now.hour*60*60 + now.minute*60 + now.second < (h+valid_hour)*60*60 + m*60 + s) or \
            ((now.hour+24)*60*60 + now.minute*60 + now.second < (h+valid_hour)*60*60 + m*60 + s):
            print("")
            break
        time.sleep(1)