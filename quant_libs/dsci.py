from quant_libs.utils import *
import numpy as np

@singleton
class DSciSetting:
    def __init__(self):
        self.return_dict = False
        self.debug = False
    def enableDebug(self):
        self.debug = True
    def disableDebug(self):
        self.debug = False


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
            from matplotlib import pyplot as plt
            plt.scatter([d[0] for d in data_input], [d[1] for d in data_input], cmap="viridis", alpha=0.5)
            plt.scatter([data_input[cid][0] for cid in centroid_ids],
                        [data_input[cid][1] for cid in centroid_ids], marker="x", c="red", s=200, linewidths=3)
            plt.show()
    
    return [data_input[c] for c in centroid_ids]

def testKMeansPp():
    import random
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

def kMeans(data_input, num_cluster, distance_func, iteration=10):
    labels = []
    centroids = kMeansPp(data_input, num_cluster, distance_func)

    for _ in range(iteration):
        labels = []
        for di in range(len(data_input)):
            nearest_centroid_id = -1
            nearest_distance = float("inf")
            for ci in range(len(centroids)):
                distance_from_centroid = distance_func(data_input[di], centroids[ci])
                if nearest_distance > distance_from_centroid:
                    nearest_distance = distance_from_centroid
                    nearest_centroid_id = ci
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




    return labels[:]


