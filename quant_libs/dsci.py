from quant_libs.utils import *
import numpy as np
from matplotlib import pyplot as plt
from typing import List, Union
import dill
import os

@singleton
class DSciSetting:
    def __init__(self):
        self.return_dict = False
        self.debug = False
    def enableDebug(self):
        self.debug = True
    def disableDebug(self):
        self.debug = False

class Kmeans:
    def __init__(self):
        self.centroids = []
        self.distance_func = None
        self.feature_weight = []
        return
    
    def getLabelAndDist(self, data_input):
        nearest_distance = float("inf")
        label = -1
        for ci, centroid in enumerate(self.centroids):
            dist = self.distance_func(data_input, centroid)
            if nearest_distance > dist:
                nearest_distance = dist
                label = ci
        return label, nearest_distance
    
    def getLabel(self, data_input):
        label, dist = self.getLabelAndDist(data_input)
        return label

    def kMeans(self, data_input, num_cluster, distance_func, iteration=10, wcss_en=False):
        labels = []

        self.centroids = kMeansPp(data_input, num_cluster, distance_func)
        self.distance_func = distance_func
        wcss = 0
        for _ in range(iteration):
            labels = []
            wcss = 0
            for di in range(len(data_input)):
                nearest_centroid_id = -1
                nearest_distance = float("inf")
                for ci in range(len(self.centroids)):
                    distance_from_centroid = distance_func(data_input[di], self.centroids[ci])
                    if nearest_distance > distance_from_centroid:
                        nearest_distance = distance_from_centroid
                        nearest_centroid_id = ci
                if wcss_en:
                    wcss += nearest_distance**2
                labels.append(nearest_centroid_id)

            for ci in range(len(self.centroids)):
                #cluster = []
                sum_data = np.array([0]*len(data_input[0]))
                cluster_size = 0
                for d, label in zip(data_input, labels):
                    if label!=ci: continue
                    #cluster.append(d)
                    # TODO: get new centroid for custom distance_func
                    sum_data = sum_data + np.array(d)
                    cluster_size += 1
                self.centroids[ci] = list(sum_data / cluster_size)
            if DSciSetting().debug:
                if len(data_input[0]) == 2:
                    plt.scatter([d[0] for d in data_input], [d[1] for d in data_input], c=labels, cmap="viridis", alpha=0.5)
                    plt.scatter([c[0] for c in self.centroids],
                                [c[1] for c in self.centroids], marker="x", c="red", s=200, linewidths=3)
                    plt.show()
        if wcss_en:
            return labels[:], wcss
        else:
            return labels[:]
    
    def exportKMeans(self, directory):
        if not os.path.isdir(directory):
            os.makedirs(directory)
        with open(directory + "/dist_func.pkl", "wb") as fout:
            dill.dump(self.distance_func, fout)
        with open(directory + "/centroids.txt", "w") as fout:
            fout.writelines(str(self.centroids))
    def importKMeans(self, directory):
        with open(directory + "/dist_func.pkl", "rb") as fin:
            self.distance_func = dill.load(fin)
        with open(directory + "/centroids.txt", "r") as fin:
            self.centroids = eval(fin.readline())

def kMeansPp(data_input, num_cluster, distance_func):
    import random
    centroid_ids = []
    centroid_ids.append(random.randint(0, len(data_input)-1))

    for itr in range(num_cluster-1):
        farthest_distance = 0
        farthest_i = -1
        for di in range(len(data_input)):
            if di in centroid_ids: continue
            distance_from_centroid = float("inf")
            # > python 3.5
            for centroid in centroid_ids:
                distance_from_centroid = min(distance_func(data_input[centroid], data_input[di]), distance_from_centroid)
            if farthest_distance < distance_from_centroid:
                farthest_i = di
                farthest_distance = distance_from_centroid
        centroid_ids.append(farthest_i)
    if DSciSetting().debug:
        if len(data_input[0]) == 2:            
            plt.scatter([d[0] for d in data_input], [d[1] for d in data_input], cmap="viridis", alpha=0.5)
            plt.scatter([data_input[cid][0] for cid in centroid_ids],
                        [data_input[cid][1] for cid in centroid_ids], marker="x", c="red", s=200, linewidths=3)
            plt.show()
    
    return [data_input[c] for c in centroid_ids]


def kMeans(data_input, num_cluster, distance_func, iteration=10, wcss_en=False):
    labels = []
    centroids = kMeansPp(data_input, num_cluster, distance_func)
    wcss = 0
    for _ in range(iteration):
        labels = []
        wcss = 0
        for di in range(len(data_input)):
            nearest_centroid_id = -1
            nearest_distance = float("inf")
            for ci in range(len(centroids)):
                distance_from_centroid = distance_func(data_input[di], centroids[ci])
                if nearest_distance > distance_from_centroid:
                    nearest_distance = distance_from_centroid
                    nearest_centroid_id = ci
            if wcss_en:
                wcss += nearest_distance**2
            labels.append(nearest_centroid_id)

        for ci in range(len(centroids)):
            #cluster = []
            sum_data = np.array([0]*len(data_input[0]))
            cluster_size = 0
            for d, label in zip(data_input, labels):
                if label!=ci: continue
                #cluster.append(d)
                # TODO: get new centroid for custom distance_func
                sum_data = sum_data + np.array(d)
                cluster_size += 1
            centroids[ci] = list(sum_data / cluster_size)
        if DSciSetting().debug:
            if len(data_input[0]) == 2:
                plt.scatter([d[0] for d in data_input], [d[1] for d in data_input], c=labels, cmap="viridis", alpha=0.5)
                plt.scatter([c[0] for c in centroids],
                            [c[1] for c in centroids], marker="x", c="red", s=200, linewidths=3)
                plt.show()
    if wcss_en:
        return labels[:], wcss
    else:
        return labels[:]

def getLabel(data_input, centroids, distance_func):
    # TODO
    return

def testKMeansPp():
    import random
    DSciSetting().enableDebug()
    data_input = []
    sigma = 0.3
    for _ in range(100):
        data_input.append([random.gauss(1, sigma), random.gauss(1, sigma)])
    for _ in range(50):
        data_input.append([random.gauss(2, sigma), random.gauss(2, sigma)])
    for _ in range(50):
        data_input.append([random.gauss(1, sigma), random.gauss(3, sigma)])
    def dist_metric(a, b):
        return sum((aa-bb)**2 for aa, bb in zip(a,b))**0.5
    kMeansPp(data_input, 3, dist_metric)


def testKMeans():
    import random
    DSciSetting().enableDebug()
    data_input = []
    sigma = 0.3
    for _ in range(100):
        data_input.append([random.gauss(1, sigma), random.gauss(1, sigma)])
    for _ in range(50):
        data_input.append([random.gauss(2, sigma), random.gauss(2, sigma)])
    for _ in range(50):
        data_input.append([random.gauss(1, sigma), random.gauss(3, sigma)])
    for _ in range(100):
        data_input.append([random.gauss(1.5, sigma), random.gauss(1.5, sigma)])
    def dist_metric(a, b):
        return sum((aa-bb)**2 for aa, bb in zip(a,b))**0.5
    kMeans(data_input, 4, dist_metric)

def testKMeansWcss():
    import random
    #DSciSetting().enableDebug()
    DSciSetting().disableDebug()
    data_input = []
    sigma = 0.3
    for _ in range(100):
        data_input.append([random.gauss(1, sigma), random.gauss(1, sigma)])
    for _ in range(50):
        data_input.append([random.gauss(2, sigma), random.gauss(2, sigma)])
    for _ in range(50):
        data_input.append([random.gauss(1, sigma), random.gauss(3, sigma)])
    for _ in range(100):
        data_input.append([random.gauss(3, sigma), random.gauss(1, sigma)])
    def dist_metric(a, b):
        return sum((aa-bb)**2 for aa, bb in zip(a,b))**0.5
    wcsses = []
    n_clusters = [2,3,4,5,6,7,8]
    for n_cluster in n_clusters:
        _, wcss = kMeans(data_input, n_cluster, dist_metric, wcss_en=True)
        wcsses.append(wcss)
    plt.plot(n_clusters, wcsses, marker=".")
    plt.show()
    
    plt.plot(n_clusters, np.array(wcsses)*np.array(n_clusters), marker=".")
    plt.show()

    plt.plot(n_clusters, np.array(wcsses)*(np.array(n_clusters)**0.5), marker=".")
    plt.show()


def testKMeansWcss2():
    import random
    #DSciSetting().enableDebug()
    DSciSetting().disableDebug()
    data_input = []
    sigma = 0.3
    n_cluster = 20
    centroids = []
    for __ in range(n_cluster):
        while True:
            x = random.randint(0, 6)
            y = random.randint(0, 6)
            if not [x,y] in centroids: break
        centroids.append([x, y])
        for _ in range(random.randint(50,100)):
            data_input.append([random.gauss(x, sigma), random.gauss(y, sigma)])
    def dist_metric(a, b):
        return sum((aa-bb)**2 for aa, bb in zip(a,b))**0.5
    wcsses = []
    n_clusters = list(range(2,36))
    for n_cluster in n_clusters:
        _, wcss = kMeans(data_input, n_cluster, dist_metric, wcss_en=True)
        wcsses.append(wcss)
    plt.plot(n_clusters, wcsses, marker=".")
    plt.show()
    
    plt.plot(n_clusters, np.array(wcsses)*np.array(n_clusters), marker=".")
    plt.show()

    plt.plot(n_clusters, np.array(wcsses)*(np.array(n_clusters)**0.5), marker=".")
    plt.show()

def testDistribution(
    data: List[Union[int, float]],
    interval: Union[int, float],
    title: str = "Line Graph Histogram (Frequency Polygon)",
    xlabel: str = "Data Values (Bins)",
    ylabel: str = "Frequency (Count)"
) -> None:
    """
    Calculates and plots a histogram as a line graph (frequency polygon).

    Args:
        data: A list of numeric data points.
        interval: The width of the bins (bin size).
        title: The title for the plot.
        xlabel: The label for the x-axis.
        ylabel: The label for the y-axis.
    """
    if not data:
        print("Error: The data list is empty.")
        return

    # Determine the bins based on the specified interval
    data.sort()
    min_val = min(data)
    max_val = max(data)
    avg_val = avg(data)
    avg90_val = avg(data[len(data)//20:len(data)-len(data)//20])
    avg50_val = avg(data[len(data)//4:len(data)-len(data)//4])
    avg80_val = avg(data[len(data)//10:len(data)-len(data)//10])
    # Ensure bins cover the entire range. Add a small epsilon to the max for safety.
    bins = np.arange(min_val, max_val + interval * 1.01, interval)

    # 1. Calculate the histogram data
    # 'hist' contains the counts, 'bin_edges' contains the boundaries
    hist, bin_edges = np.histogram(data, bins=bins)

    # 2. Calculate the midpoint for each bin
    # The line graph plots frequency against the midpoint of the bin
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    # 3. Create the plot
    plt.figure(figsize=(10, 6))
    
    # Plot the frequency polygon (line graph)
    plt.plot(bin_centers, hist, marker='o', linestyle='-', linewidth=2)
    
    # Add optional styling and labels
    plt.title(title, fontsize=16)
    plt.xlabel(xlabel, fontsize=14)
    plt.ylabel(ylabel, fontsize=14)
    plt.grid(axis='y', linestyle='--', alpha=0.7)


    position = 1.
    for (a, color, txt) in [(avg_val, "#000000", "Avg: "),
                               (avg90_val, "#101010", "Avg90: "),
                               (avg80_val, "#202020", "Avg80: "),
                               (avg50_val, "#303030", "Avg50: ")]:
        plt.plot([a, a], [0, max(hist)], color=color, linestyle='--')
        plt.text(a, max(hist)*position, f"{txt}{a}", color=color)
        position *= 0.95

    
    # Ensure x-ticks align somewhat with the bin centers/edges
    # This is a good general approach but can be adjusted
    #plt.xticks(bin_centers, rotation=45, ha='right') 
    
    #plt.tight_layout()
    plt.show()