
def singleton(cls):
    instances = {}
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance

def stdev(l):
    m = sum(l)/len(l)
    return (sum((ll-m)**2 for ll in l) / len(l))**0.5