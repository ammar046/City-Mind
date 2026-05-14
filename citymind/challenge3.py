# challenge3: where to park 3 ambulances so the farthest citizen isnt too far (minimax).
# GA because brute force placements explodes. we precompute Dijkstra from every candidate node once
# then evolution is cheap.

import random
import math


class GeneticAmbulance:
    def __init__(self, graph, numambs=3, popsize=30, gens=40):
        self.graph    = graph
        self.numambs  = numambs
        self.popsize  = popsize
        self.gens     = gens
        self.log      = []
        self.bestplaces  = []
        self.bestmaxdist = float("inf")

    def _citizennodes(self):
        # only nodes with actual people in them count for response time
        return [n for n in self.graph.allnodes() if n.density > 0 and not n.blocked]

    def _candidatenodes(self):
        # ambulances can park anywhere that isnt blocked
        return [n for n in self.graph.allnodes() if not n.blocked]

    def _dijkstra(self, startid):
        # proper shortest path using effective road costs
        import heapq
        dist = {nid: float("inf") for nid in self.graph.nodes}
        dist[startid] = 0.0
        heap = [(0.0, startid)]
        while heap:
            d, cur = heapq.heappop(heap)
            if d > dist[cur]:
                continue
            for nbid, cost in self.graph.neighbors(cur):
                nd = d + cost
                if nd < dist[nbid]:
                    dist[nbid] = nd
                    heapq.heappush(heap, (nd, nbid))
        return dist

    def _evaluate(self, placement, alldists, citizens):
        # fitness = 1 / worst case response time
        # higher is better since we want to minimize worst case distance
        maxdist = 0.0
        for c in citizens:
            nearest = min(alldists[p].get(c.nodeid, float("inf")) for p in placement)
            if nearest > maxdist:
                maxdist = nearest
        if maxdist == 0:
            return 1e9, 0.0
        return 1.0 / maxdist, maxdist

    def run(self):
        self.log   = []
        citizens   = self._citizennodes()
        candidates = self._candidatenodes()

        if len(candidates) < self.numambs:
            self.log.append("Not enough nodes to place ambulances")
            return []

        candids = [n.nodeid for n in candidates]

        # precompute shortest paths from every candidate position once
        # this makes fitness evaluation really fast during evolution
        alldists = {}
        for cid in candids:
            alldists[cid] = self._dijkstra(cid)

        # random initial population
        pop = [random.sample(candids, self.numambs) for _ in range(self.popsize)]

        bestindiv = None
        bestmaxd  = float("inf")

        for gen in range(self.gens):
            scored = []
            for indiv in pop:
                fit, maxd = self._evaluate(indiv, alldists, citizens)
                scored.append((fit, maxd, indiv))
                if maxd < bestmaxd:
                    bestmaxd  = maxd
                    bestindiv = indiv[:]

            scored.sort(key=lambda x: x[0], reverse=True)

            # top half survives
            survivors = [s[2] for s in scored[:self.popsize // 2]]

            # crossover pairs to produce children
            children  = []
            for i in range(0, len(survivors) - 1, 2):
                p1, p2 = survivors[i], survivors[i + 1]
                child  = p1[:]
                swapidx = random.randint(0, self.numambs - 1)
                child[swapidx] = p2[swapidx]
                # fix duplicates caused by crossover
                seen = set()
                for j in range(len(child)):
                    if child[j] in seen:
                        unused = [c for c in candids if c not in seen]
                        if unused:
                            child[j] = random.choice(unused)
                    seen.add(child[j])
                children.append(child)

            # 20% mutation chance - randomly relocate one ambulance
            mutated = []
            for indiv in survivors + children:
                if random.random() < 0.20:
                    ind2 = indiv[:]
                    idx  = random.randint(0, self.numambs - 1)
                    ind2[idx] = random.choice(candids)
                    # fix duplicates
                    seen = set()
                    for j in range(len(ind2)):
                        if ind2[j] in seen:
                            unused = [c for c in candids if c not in seen]
                            if unused:
                                ind2[j] = random.choice(unused)
                        seen.add(ind2[j])
                    mutated.append(ind2)
                else:
                    mutated.append(indiv)

            pop = mutated
            while len(pop) < self.popsize:
                pop.append(random.sample(candids, self.numambs))

        self.bestplaces  = bestindiv if bestindiv else random.sample(candids, self.numambs)
        self.bestmaxdist = bestmaxd

        self._updatecoverage(alldists, citizens)

        self.log.append(
            f"GA done ambulances placed at nodes {self.bestplaces} "
            f"max response dist {self.bestmaxdist:.2f}"
        )
        return self.bestplaces

    def _updatecoverage(self, alldists, citizens):
        # paint ambcov on nodes for the UI heatmap (slightly loose threshold looks nicer)
        threshold = self.bestmaxdist * 1.1
        for n in self.graph.allnodes():
            n.ambcov = False
        for p in self.bestplaces:
            for nid, d in alldists[p].items():
                if d <= threshold:
                    self.graph.nodes[nid].ambcov = True
