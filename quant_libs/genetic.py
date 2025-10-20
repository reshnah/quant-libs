import random

class Chromosome:
    #genes = []
    #ranges = []
    #domains = []

    tag = ""
    intensities = 0.1
    eval_func = None




    INT = "I"
    FLOAT = "F"
    LABEL = "L"
    BOOL = "B"
    TRISTATE = "T"

    CONSTANT = "C"
    MUTANTABLE = "M"


    def __init__(self, tag, chromosome_group, domains, ranges, eval_func):
        self.chromosome_group = chromosome_group
        self.genes = []
        self.ranges = []
        self.domains = []
        self.genes_mutant = []

        if type(tag)!=str:
            raise TypeError
        self.tag = tag
        self.domains = domains[:]
        self.ranges = ranges[:]
        for i in range(len(domains)):
            self.genes.append(0)
        self.eval_func = eval_func

    def setEvalFunc(self, eval_func):
        self.eval_func = eval_func

    def randomize(self):
        for idx, r, domain in zip(range(len(self.genes)), self.ranges, self.domains):
            if domain[0] == "F":
                self.genes[idx] = random.random() * (r[1] - r[0]) + r[0]
            elif domain[0] == "I" or domain[0] == "L":
                self.genes[idx] = random.randrange(r[0], r[1] + 1)
            elif domain[0] == "B":
                self.genes[idx] = bool(random.getrandbits(1))
            elif domain[0] == "T":
                self.genes[idx] = random.randrange(-1, 2)
            else:
                raise ValueError
        return

    def genMutant(self):
        self.genes_mutant = []
        if type(self.intensities)==float:
            self.intensities = [self.intensities]*len(self.genes)
        for idx, r, domain, intensity in zip(range(len(self.genes)),self.ranges,self.domains, self.intensities):
            if domain[1]==self.CONSTANT:
                self.genes_mutant.append(self.genes[idx])
                continue
            if domain[0]=="F":
                self.genes_mutant.append(random.gauss(self.genes[idx],(r[1]-r[0])*intensity*0.28867513459481288225457439025098))
                self.genes_mutant[-1] = min(max(r[0],self.genes_mutant[-1]),r[1])
            elif domain[0]=="I":
                # TODO: reflect range
                self.genes_mutant.append(int(random.gauss(self.genes[idx], (r[1]-r[0])*intensity*0.28867513459481288225457439025098)+0.5))
                self.genes_mutant[-1] = min(max(r[0], self.genes_mutant[-1]), r[1])
            elif domain[0]=="L":
                if random.random()<intensity:
                    self.genes_mutant.append(random.randrange(r[0], r[1]+1))
                else:
                    self.genes_mutant.append(self.genes[idx])
            elif domain[0]=="B":
                if random.random()<intensity:
                    self.genes_mutant.append(not self.genes[idx])
                else:
                    self.genes_mutant.append(self.genes[idx])
            elif domain[0]=="T":
                rand = random.random()
                if rand < intensity/2:
                    self.genes_mutant.append((self.genes[idx]+2)%3-1)
                elif rand < intensity:
                    self.genes_mutant.append((self.genes[idx]+1)%3-1)
                else:
                    self.genes_mutant.append(self.genes[idx])
            else:
                raise ValueError
        return

    def overwriteGenes(self, chromosome):
        self.genes = chromosome.genes[:]

    def evaluate(self, *args):
        if self.eval_func is None:
            raise AssertionError
        return self.eval_func(self.genes, *args)

    def evaluateMutant(self, *args):
        if self.eval_func is None:
            raise AssertionError
        #self.genMutant()
        return self.eval_func(self.genes_mutant, *args)

    def mutate(self):
        if len(self.genes_mutant)!=0:
            self.genes = self.genes_mutant[:]
            self.genes_mutant = []
    def loadString(self, s):
        s = s.split("=")
        self.tag = s[0]
        self.genes = eval(s[1])
    def __repr__(self):
        return "%s=%s"%(self.tag, self.genes)

class Species:

    INT = "I"
    FLOAT = "F"
    LABEL = "L"
    BOOL = "B"
    TRISTATE = "T"

    CONSTANT = "C"
    MUTANTABLE = "M"

    score = 0

    def __init__(self):
        self.chromosomes = []
        return

    def addChromosome(self, tag, chromosome_group, domains, ranges, eval_func):
        self.chromosomes.append(Chromosome(tag, chromosome_group, domains, ranges, eval_func))

    def appendChromosome(self, chromosome):
        self.chromosomes.append(chromosome.copy())

    def getChromosome(self, idx):
        return self.chromosomes[idx]

    def setChromosome(self, idx, chromosome):
        self.chromosomes[idx].overwriteGenes(chromosome)
    def setChromosomeConstant(self, idx):
        self.chromosomes[idx].domains[1].replace("M", "C")
    def setChromosomeMutantable(self, idx):
        self.chromosomes[idx].domains[1].replace("C", "M")
    @staticmethod
    def crossover(child, parents):
        num_parents = len(parents)
        num_chromosomes = len(parents[0].chromosomes)
        for ci in range(num_chromosomes):
            rn = random.random() * num_parents
            child.setChromosome(ci, parents[int(rn)].getChromosome(ci))

    def randomize(self, chromosome_group=None):
        for ci in range(len(self.chromosomes)):
            if (chromosome_group is None) or (self.chromosomes[ci].chromosome_group==chromosome_group):
                self.chromosomes[ci].randomize()

    def genMutant(self, chromosome_group=None):
        for ci in range(len(self.chromosomes)):
            self.chromosomes[ci].genMutant()

    def mutate(self, chromosome_group=None):
        for ci in range(len(self.chromosomes)):
            if (chromosome_group is None) or (self.chromosomes[ci].chromosome_group==chromosome_group):
                self.chromosomes[ci].mutate()

    def evaluate(self, chromosome_group, *args):
        result = []
        for ci in range(len(self.chromosomes)):
            if self.chromosomes[ci].chromosome_group==chromosome_group:
                result.append(self.chromosomes[ci].evaluate(*args))
        return result

    def evaluateMutant(self, chromosome_group, *args):
        result = []
        for ci in range(len(self.chromosomes)):
            if self.chromosomes[ci].chromosome_group==chromosome_group:
                result.append(self.chromosomes[ci].evaluateMutant(*args))
        return result

    def loadString(self, s):
        s = s.split("|")
        if len(s) != len(self.chromosomes):
            raise ValueError
        for ci in range(len(self.chromosomes)):
            self.chromosomes[ci].loadString(s[ci])

    def getCopy(self):
        new_one = Species()
        new_one.loadString(str(self))
        return new_one

    def __repr__(self):
        s = ""
        for ci in range(len(self.chromosomes)):
            s = s + "%s|"%(self.chromosomes[ci])
        return s[:-1]