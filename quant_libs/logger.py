from quant_libs.singleton import singleton
import time
import datetime

@singleton
class LoggerSetting:
    log_path = ""
    log_level = 0
    def __init__(self):
        return

def strNow():
    s = "[" + time.strftime("%H:%M:%S", time.localtime()) + "]"
    return s

def strToday(length = 6):
    if length==8:
        return time.strftime("%Y%m%d", time.localtime())
    elif length==6:
        return time.strftime("%y%m%d", time.localtime())
    elif length==4:
        return time.strftime("%m%d", time.localtime())

def datetimeToday():
    return datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

def stdLog(s):
    print(strNow()+s)
    fout = open(LoggerSetting().log_path+"log%s.txt"%(strToday(6)), "a")
    fout.writelines(strNow()+s+"\n")
    fout.close()