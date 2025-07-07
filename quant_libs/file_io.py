from quant_libs.utils import *
import time, datetime
import csv
import psutil
import os

@singleton
class FileIoSetting:
    log_path = ""
    log_level = 0
    def __init__(self):
        return


chart_tag_map = {"time": "t",
                 "date": "t",
                 "datetime": "t",
                 "open": "o",
                 "price": "c", "close": "c",
                 "low": "l",
                 "high": "h",
                 "volume": "v"}

class open_wait:
    def __init__(self, filename, mode):
        self.filename = filename
        self.mode = mode
        self.file = None

    def __enter__(self):
        #print(f"[{os.path.basename(self.filename)}]: Entering context. Opening file '{self.filename}' in mode '{self.mode}'...")
        while True:
            try:
                self.file = open(self.filename, self.mode)
                return self.file
            except PermissionError:
                filepath = os.path.abspath(self.filename)
                for proc in psutil.process_iter(['pid', 'name', 'open_files']):
                    try:
                        if proc.info['open_files']:
                            for file in proc.info['open_files']:
                                if os.path.abspath(file.path) == filepath:
                                    print(f"File '{filepath}' is being used by process:")
                                    print(f"  PID: {proc.info['pid']}")
                                    print(f"  Name: {proc.info['name']}")
                    except:
                        pass
                print(f"{self.filename} is being used by another process.")
                time.sleep(5)
                continue
            except IOError as e:
                #print(f"[{os.path.basename(self.filename)}]: Error opening file: {e}")
                # You might want to re-raise or handle this differently based on your needs
                raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            #print(f"[{os.path.basename(self.filename)}]: Exiting context. Closing file '{self.filename}'...")
            self.file.close()

        if exc_type:
            #print(f"[{os.path.basename(self.filename)}]: An exception occurred!")
            #print(f"[{os.path.basename(self.filename)}]: Type: {exc_type.__name__}")
            #print(f"[{os.path.basename(self.filename)}]: Value: {exc_val}")
            # print(f"[{os.path.basename(self.filename)}]: Traceback: {traceback.format_tb(exc_tb)}") # Uncomment to see full traceback
            # Returning False (or None) will re-raise the exception
            return False
        #else:
        #    print(f"[{os.path.basename(self.filename)}]: No exception occurred. Context exited cleanly.")
        return False # Ensure exceptions are propagated by default

def importCsvChartDict(csv_path):
    chart = {"t": [], "o": [], "h": [], "l": [], "c": [], "v": []}
    with open(csv_path, newline='') as f:
        reader = csv.reader(f, delimiter=',')        
        first_row = next(reader)
        first_row = [f.lower() for f in first_row]
        for row in reader:
            for ri, header in enumerate(first_row):
                k = chart_tag_map[header]
                if k=="t":
                    try:
                        chart["t"].append(datetime.datetime.strptime(row[ri], "%Y-%m-%d %H:%M:%S"))
                    except:
                        chart["t"].append(datetime.datetime.strptime(row[ri], "%Y-%m-%d"))
                else:
                    chart[k].append(float(row[ri]))
            #print(row)
        # Error
        #chart["o"][1:] = chart["c"][:-1]
        #for s in "tochlv":
        #    chart[s] = chart[s][1:]
    if len(chart["v"])==0:
        del chart["v"]
    return chart


def importReversedCsvChartDict(csv_path):
    chart = {"t": [], "o": [], "h": [], "l": [], "c": [], "v": []}
    with open(csv_path, newline='') as f:
        reader = csv.reader(f, delimiter=',')        
        first_row = next(reader)
        first_row = [f.lower() for f in first_row]
        for row in reader:
            for ri, header in enumerate(first_row):
                k = chart_tag_map[header]
                if k=="t":
                    try:
                        chart["t"].append(datetime.datetime.strptime(row[ri], "%Y-%m-%d %H:%M:%S"))
                    except:
                        chart["t"].append(datetime.datetime.strptime(row[ri], "%Y-%m-%d"))
                elif k=="v":
                    chart[k].append(float(row[ri]))
                else:
                    chart[k].append(1/float(row[ri]))
            #print(row)
        # Error
        #chart["o"][1:] = chart["c"][:-1]
        #for s in "tochlv":
        #    chart[s] = chart[s][1:]
    if len(chart["v"])==0:
        del chart["v"]
    return chart

def exportCsvChart(chart, csv_path):
    if type(chart)==dict:
        with open(csv_path, "w") as fout:
            if "v" in chart:
                fout.writelines("Datetime,Open,High,Low,Price,Volume\n")
                for ti in range(len(chart["t"])):
                    fout.writelines(f'{chart["t"][ti].strftime("%Y-%m-%d %H:%M:%S")},'
                                    f'{chart["o"][ti]},{chart["h"][ti]},{chart["l"][ti]},{chart["c"][ti]},{chart["v"][ti]}\n')
            else:
                fout.writelines("Datetime,Open,High,Low,Price\n")
                for ti in range(len(chart["t"])):
                    fout.writelines(f'{chart["t"][ti].strftime("%Y-%m-%d %H:%M:%S")},{chart["o"][ti]},{chart["h"][ti]},{chart["l"][ti]},{chart["c"][ti]}\n')
            

# TODO: merge
# TODO: resolution adjust