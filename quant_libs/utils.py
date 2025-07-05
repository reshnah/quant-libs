
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
