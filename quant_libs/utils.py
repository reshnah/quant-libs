
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
    return transposed