# challenge5: fake crime pipeline for the project.
# 1) k-means on [density, industrial proximity] with no labels
# 2) invent a numeric "crime rate" from density + distance to industry + cluster id + noise
# 3) bucket into High/Medium/Low and train our own decision tree (gini splits)
# 4) write risklvl back onto nodes so edge.cost picks up multipliers from graph.py
#
# we dropped an old "Critical" fourth label so we match the course pdf (only 3 bands).

import random
import math
from graph import industrial


class KMeans:
    # rolling our own k-means so we can explain every line in the viva
    def __init__(self, k=3, maxiters=100):
        self.k        = k
        self.maxiters = maxiters
        self.centers  = []

    def _dist(self, a, b):
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    def fit(self, points):
        self.centers = random.sample(points, self.k)

        for _ in range(self.maxiters):
            assignments = [
                min(range(self.k), key=lambda ci: self._dist(p, self.centers[ci]))
                for p in points
            ]

            newcenters = []
            for ci in range(self.k):
                members = [points[i] for i, a in enumerate(assignments) if a == ci]
                if not members:
                    newcenters.append(self.centers[ci])
                else:
                    dim  = len(members[0])
                    newc = [sum(m[d] for m in members) / len(members) for d in range(dim)]
                    newcenters.append(newc)

            if newcenters == self.centers:
                break
            self.centers = newcenters

        return assignments


class DecisionTreeNode:
    def __init__(self):
        self.feature = None
        self.thresh  = None
        self.left    = None
        self.right   = None
        self.label   = None  # set if this is a leaf


class DecisionTree:
    # hand rolled decision tree using gini impurity splits
    def __init__(self, maxdepth=5):
        self.maxdepth = maxdepth
        self.root     = None

    def _gini(self, labels):
        if not labels:
            return 0.0
        total  = len(labels)
        counts = {}
        for l in labels:
            counts[l] = counts.get(l, 0) + 1
        return 1.0 - sum((v / total) ** 2 for v in counts.values())

    def _bestsplit(self, X, y):
        bestgain = -1
        bestf    = None
        bestth   = None
        basegini = self._gini(y)
        n        = len(y)

        for f in range(len(X[0])):
            vals = sorted(set(x[f] for x in X))
            for i in range(len(vals) - 1):
                th = (vals[i] + vals[i + 1]) / 2
                ly = [y[i2] for i2, x in enumerate(X) if x[f] <= th]
                ry = [y[i2] for i2, x in enumerate(X) if x[f] >  th]
                if not ly or not ry:
                    continue
                gain = basegini - (len(ly)/n)*self._gini(ly) - (len(ry)/n)*self._gini(ry)
                if gain > bestgain:
                    bestgain = gain
                    bestf    = f
                    bestth   = th
        return bestf, bestth

    def _build(self, X, y, depth):
        nd = DecisionTreeNode()
        counts = {}
        for l in y:
            counts[l] = counts.get(l, 0) + 1

        if not y or depth == 0 or len(set(y)) == 1:
            nd.label = max(counts, key=counts.get) if counts else "Low"
            return nd

        f, th = self._bestsplit(X, y)
        if f is None:
            nd.label = max(counts, key=counts.get)
            return nd

        nd.feature = f
        nd.thresh  = th
        lidx = [i for i, x in enumerate(X) if x[f] <= th]
        ridx = [i for i, x in enumerate(X) if x[f] >  th]
        nd.left  = self._build([X[i] for i in lidx], [y[i] for i in lidx], depth - 1)
        nd.right = self._build([X[i] for i in ridx], [y[i] for i in ridx], depth - 1)
        return nd

    def fit(self, X, y):
        self.root = self._build(X, y, self.maxdepth)

    def _predictone(self, x, node):
        if node.label is not None:
            return node.label
        if x[node.feature] <= node.thresh:
            return self._predictone(x, node.left)
        return self._predictone(x, node.right)

    def predict(self, X):
        return [self._predictone(x, self.root) for x in X]


class CrimeRisk:
    def __init__(self, graph):
        self.graph = graph
        self.log   = []
        self.km    = KMeans(k=3)
        self.dt    = DecisionTree(maxdepth=5)

    def _indprox(self, node):
        # how close this node is to industrial zones
        # industrial proximity drives crime risk in our model
        # rationale: industrial areas bring transient workers, less residential oversight
        indnodes = [n for n in self.graph.allnodes() if n.kind == industrial]
        if not indnodes:
            return 0.0
        minwhat = min(self.graph.manhattan(node.nodeid, i.nodeid) for i in indnodes)
        return 1.0 / (1.0 + minwhat)

    def _feats(self):
        nodes = self.graph.allnodes()
        maxd  = max(n.density for n in nodes) or 1.0
        feats = []
        for n in nodes:
            normd  = n.density / maxd
            indprx = self._indprox(n)
            feats.append([normd, indprx])
        return nodes, feats

    def _syntheticrate(self, node, clusterid, indprx):
        # crime rate formula:
        # high density = more people = more opportunity for crime (log-scaled to prevent overflow)
        # close to industrial = more transient traffic = higher risk
        # higher cluster id = marginally more risk (clusters sorted by density)
        # thresholds: High >= 50, Medium >= 25, else Low
        import math as _math
        base   = _math.log1p(node.density) * 4.0   # log1p(150)*4 ~20 max
        ibonus = indprx * 35                        # 0..35
        cbonus = clusterid * 6                      # 0..12
        noise  = random.uniform(-4, 4)
        return max(0.0, base + ibonus + cbonus + noise)

    def run(self):
        self.log = []
        nodes, feats = self._feats()

        # step 1 cluster by density and industrial proximity with k-means
        assignments = self.km.fit(feats)
        for i, n in enumerate(nodes):
            n.cluster = assignments[i]
        self.log.append(f"K-Means clustered {len(nodes)} nodes into 3 groups")

        # remap cluster ids so 0 is low density and 2 is high density
        cavg = {}
        for i, n in enumerate(nodes):
            cid = assignments[i]
            cavg.setdefault(cid, []).append(n.density)
        cavgmean    = {cid: sum(v) / len(v) for cid, v in cavg.items()}
        sortedclusters = sorted(cavgmean, key=cavgmean.get)
        remap = {old: new for new, old in enumerate(sortedclusters)}
        for n in nodes:
            n.cluster = remap.get(n.cluster, n.cluster)

        # step 2 generate synthetic crime labels (three tiers per project statement)
        # High >= 45, Medium >= 25, else Low — former "Critical" band (very high rate) folds into High
        X, y   = [], []
        indprxs = [f[1] for f in feats]
        for i, n in enumerate(nodes):
            rate = self._syntheticrate(n, n.cluster, indprxs[i])
            if rate >= 45:
                label = "High"
            elif rate >= 25:
                label = "Medium"
            else:
                label = "Low"
            X.append(feats[i] + [float(n.cluster)])
            y.append(label)

        self.log.append(
            f"Synthetic dataset: {y.count('High')} High, {y.count('Medium')} Medium, "
            f"{y.count('Low')} Low (three risk levels per spec)"
        )

        # step 3 train decision tree on the labeled data
        self.dt.fit(X, y)
        preds = self.dt.predict(X)

        # step 4 push predictions back into the shared graph
        # this affects effective_cost on every edge going forward
        for i, n in enumerate(nodes):
            n.updaterisk(preds[i])
        self.graph.refreshriskcosts()

        high = preds.count("High")
        med  = preds.count("Medium")
        low  = preds.count("Low")
        self.log.append(
            f"Risk applied: {high} High, {med} Medium, {low} Low — edge costs updated (1.5x / 1.2x / 1.0x)"
        )
        # surface unsupervised vs supervised distinction for viva clarity
        self.log.append(
            "ML pipeline: Step 1 UNSUPERVISED (K-Means, no labels) "
            "-> Step 3 SUPERVISED (Decision Tree, uses generated labels)"
        )
        return preds
