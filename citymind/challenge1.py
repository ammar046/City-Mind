# challenge1: plonk buildings on the grid with CSP + backtracking + forward checking.
# if backtracking times out we fall back to min-conflicts repair (messy but works).
#
# weird but important detail: "3 hops to hospital" is checked two ways.
#   - while placing: use full grid neighbors (what roads WOULD exist before Kruskal eats half of them)
#   - after roads: validate_built_road_network() checks again on ONLY built edges so we dont lie to ourselves

import random
import time
from collections import deque

from graph import (residential, hospital, school, industrial,
                   powerplant, depot, empty)

alltypes = [residential, hospital, school, industrial, powerplant, depot]

# these two cant be next to industrial zones
indConflict = {school, hospital}


def nodes_within_built_road_hops(graph, startid, maxhops):
    # BFS but only on roads that are actually built and not flooded (graph.neighbors)
    dist = {startid: 0}
    q = deque([startid])
    while q:
        nid = q.popleft()
        d = dist[nid]
        if d >= maxhops:
            continue
        for nbid, _ in graph.neighbors(nid):
            if nbid not in dist:
                dist[nbid] = d + 1
                q.append(nbid)
    return set(dist.keys())


def validate_built_road_network(graph):
    # same rules as CSP but distances measured on real MST roads, not imaginary full grid
    issues = []
    hospnodes = [n for n in graph.allnodes() if n.kind == hospital]
    indnodes = [n for n in graph.allnodes() if n.kind == industrial]

    for n in graph.allnodes():
        if n.kind != residential:
            continue
        if not hospnodes:
            continue
        reachable = nodes_within_built_road_hops(graph, n.nodeid, 3)
        if not any(h.nodeid in reachable for h in hospnodes):
            issues.append(
                f"Node {n.nodeid} Residential: no hospital within 3 hops on built roads "
                f"(planned grid may still be OK)"
            )

    for n in graph.allnodes():
        if n.kind != powerplant:
            continue
        if not indnodes:
            continue
        reachable = nodes_within_built_road_hops(graph, n.nodeid, 2)
        if not any(i.nodeid in reachable for i in indnodes):
            issues.append(
                f"Node {n.nodeid} PowerPlant: no industrial within 2 hops on built roads "
                f"(planned grid may still be OK)"
            )

    return issues


class CSPLayout:
    def __init__(self, graph):
        self.graph = graph
        self.rows  = graph.rows
        self.cols  = graph.cols

        # how many of each type to place
        # keeping these small means backtracking finds a valid layout in milliseconds
        total = self.rows * self.cols
        self.targets = {
            residential: max(4,  total // 6),
            hospital:    max(2,  total // 12),
            school:      max(1,  total // 18),
            industrial:  max(1,  total // 16),
            powerplant:  max(1,  total // 22),
            depot:       max(1,  total // 28),
        }
        self.log = []

    def run(self):
        self.log  = []
        self.deadline = time.time() + 0.4   # bail after 0.4s and use min-conflicts
        for n in self.graph.allnodes():
            n.settype(empty, 0.0)

        order   = self._order()
        domains = {nid: list(alltypes) for nid in order}

        ok = self._backtrack(order, 0, domains)
        if ok:
            self._fillremaining()
            self._setdensities()
            self.log.append("CSP backtracking found a valid layout")
            self.lastrule = "none"
            return True
        else:
            self.log.append("Backtracking could not find perfect layout running min-conflicts repair")
            conflictname, desc = self._minconflicts()
            self.lastrule = conflictname
            self.log.append(desc)
            self._setdensities()
            return False

    def _order(self):
        # shuffle so we get different cities each run
        ids = list(self.graph.nodes.keys())
        random.shuffle(ids)
        return ids

    def _backtrack(self, order, idx, domains):
        if time.time() > self.deadline:
            # wall clock limit hit bail and let min-conflicts handle it
            return False
        if idx == len(order):
            return self._countplaced() >= self._mintotal()

        nid  = order[idx]
        node = self.graph.nodes[nid]

        vals = list(domains[nid])
        random.shuffle(vals)

        for val in vals:
            if self._countoftype(val) >= self.targets.get(val, 9999):
                continue
            if self._consistent(nid, val):
                node.settype(val, 0.0)
                saved  = self._forwardcheck(nid, val, domains)
                result = self._backtrack(order, idx + 1, domains)
                if result:
                    return True
                self._restoredomains(saved, domains)
                node.settype(empty, 0.0)

        # if we already have enough nodes placed this spot can stay empty
        if self._countplaced() >= self._mintotal():
            return self._backtrack(order, idx + 1, domains)

        return False

    def _forwardcheck(self, nid, val, domains):
        # after placing industrial somewhere remove school and hospital
        # from neighbor domains so we catch conflicts before going deeper
        saved = {}
        if val == industrial:
            for nbid in self.graph.gridnbrs(nid):
                removed = []
                if school   in domains[nbid]:
                    domains[nbid].remove(school)
                    removed.append(school)
                if hospital in domains[nbid]:
                    domains[nbid].remove(hospital)
                    removed.append(hospital)
                if removed:
                    saved[nbid] = removed
        return saved

    def _restoredomains(self, saved, domains):
        for nbid, vals in saved.items():
            for v in vals:
                if v not in domains[nbid]:
                    domains[nbid].append(v)

    def _consistent(self, nid, val):
        nbrs = self.graph.gridnbrs(nid)

        if val == industrial:
            for nbid in nbrs:
                if self.graph.nodes[nbid].kind in indConflict:
                    return False

        if val in indConflict:
            for nbid in nbrs:
                if self.graph.nodes[nbid].kind == industrial:
                    return False

        # residential must be within 3 planned road hops of at least one hospital
        if val == residential:
            hospnodes = [n for n in self.graph.allnodes() if n.kind == hospital]
            if hospnodes:
                reachable = self._planned_road_hops(nid, 3)
                if not any(h.nodeid in reachable for h in hospnodes):
                    return False

        # powerplant must be within 2 planned road hops of at least one industrial
        if val == powerplant:
            indnodes = [n for n in self.graph.allnodes() if n.kind == industrial]
            if indnodes:
                reachable = self._planned_road_hops(nid, 2)
                if not any(i.nodeid in reachable for i in indnodes):
                    return False

        return True

    def _planned_road_hops(self, startid, maxhops):
        # flood fill on grid squares (NSEW), ignores which edges Kruskal later keeps
        visited = {startid}
        frontier = [startid]
        for _ in range(maxhops):
            nxt = []
            for nid in frontier:
                for nbid in self.graph.gridnbrs(nid):
                    if nbid not in visited:
                        visited.add(nbid)
                        nxt.append(nbid)
            frontier = nxt
            if not frontier:
                break
        return visited

    def _countplaced(self):
        return sum(1 for n in self.graph.allnodes() if n.kind != empty)

    def _countoftype(self, t):
        return sum(1 for n in self.graph.allnodes() if n.kind == t)

    def _mintotal(self):
        return sum(self.targets.values())

    def _fillremaining(self):
        # any unassigned cell: try residential, then school, then just leave as residential
        # MUST check constraints so backtracking's valid state isn't broken
        fallback_types = [residential, school, hospital, powerplant, depot]
        for n in self.graph.allnodes():
            if n.kind == empty:
                placed = False
                for t in fallback_types:
                    if self._consistent(n.nodeid, t):
                        n.settype(t, 0.0)
                        placed = True
                        break
                if not placed:
                    # nothing fits — assign residential anyway
                    # (a minor violation is better than leaving empty)
                    n.settype(residential, 0.0)

    def _setdensities(self):
        # rough population estimates based on building type
        densitymap = {
            residential: (60, 150),
            hospital:    (10, 30),
            school:      (20, 50),
            industrial:  (5,  20),
            powerplant:  (2,  10),
            depot:       (2,  8),
            empty:       (0,  0),
        }
        for n in self.graph.allnodes():
            lo, hi = densitymap.get(n.kind, (10, 50))
            n.density = random.uniform(lo, hi)

    def _minconflicts(self):
        # start with a random assignment then keep fixing the worst violated nodes
        typelist = []
        for t, count in self.targets.items():
            typelist.extend([t] * count)
        while len(typelist) < self.rows * self.cols:
            typelist.append(residential)
        typelist = typelist[:self.rows * self.cols]
        random.shuffle(typelist)

        nodes = self.graph.allnodes()
        for i, n in enumerate(nodes):
            n.settype(typelist[i], 0.0)

        for _ in range(700):
            violations = self._getviolations()
            if not violations:
                break
            badnode    = random.choice(violations)
            candidates = [t for t in alltypes if self._consistent(badnode.nodeid, t)]
            if candidates:
                badnode.settype(random.choice(candidates), 0.0)

        remaining = self._getviolations()
        if remaining:
            conflict = self._identifyconflict()
            desc     = f"MinConflicts: {len(remaining)} violations remain main conflict is {conflict}"
        else:
            desc     = "MinConflicts repaired all violations successfully"
            conflict = "none"
        return conflict, desc

    def _getviolations(self):
        return [n for n in self.graph.allnodes()
                if not self._consistent(n.nodeid, n.kind)]

    def _identifyconflict(self):
        # count violations per rule using proper BFS hop counting (not Manhattan distance)
        counts = {
            "Industrial adjacent to School or Hospital": 0,
            "Residential more than 3 hops from Hospital": 0,
            "PowerPlant more than 2 hops from Industrial": 0,
        }

        for n in self.graph.allnodes():
            if n.kind == industrial:
                for nbid in self.graph.gridnbrs(n.nodeid):
                    if self.graph.nodes[nbid].kind in indConflict:
                        counts["Industrial adjacent to School or Hospital"] += 1

        hospnodes = [n for n in self.graph.allnodes() if n.kind == hospital]
        for n in self.graph.allnodes():
            if n.kind == residential:
                reachable = self._planned_road_hops(n.nodeid, 3)
                close = any(h.nodeid in reachable for h in hospnodes)
                if not close:
                    counts["Residential more than 3 hops from Hospital"] += 1

        indnodes = [n for n in self.graph.allnodes() if n.kind == industrial]
        for n in self.graph.allnodes():
            if n.kind == powerplant:
                reachable = self._planned_road_hops(n.nodeid, 2)
                close = any(i.nodeid in reachable for i in indnodes)
                if not close:
                    counts["PowerPlant more than 2 hops from Industrial"] += 1

        worst = max(counts, key=lambda k: counts[k])
        return f"{worst} ({counts[worst]} violations)"

    def validate(self):
        # sanity check current assignment on planned grid (not post-MST)
        issues = []

        for n in self.graph.allnodes():
            if n.kind == industrial:
                for nbid in self.graph.gridnbrs(n.nodeid):
                    nbkind = self.graph.nodes[nbid].kind
                    if nbkind in indConflict:
                        issues.append(
                            f"Node {n.nodeid} Industrial is adjacent to {nbkind} at node {nbid}"
                        )

        hospnodes = [n for n in self.graph.allnodes() if n.kind == hospital]
        for n in self.graph.allnodes():
            if n.kind == residential:
                reachable = self._planned_road_hops(n.nodeid, 3)
                close = any(h.nodeid in reachable for h in hospnodes)
                if not close:
                    issues.append(
                        f"Node {n.nodeid} Residential is too far from any hospital "
                        f"(planned network: >3 hops)"
                    )

        indnodes = [n for n in self.graph.allnodes() if n.kind == industrial]
        for n in self.graph.allnodes():
            if n.kind == powerplant:
                reachable = self._planned_road_hops(n.nodeid, 2)
                close = any(i.nodeid in reachable for i in indnodes)
                if not close:
                    issues.append(
                        f"Node {n.nodeid} PowerPlant is too far from any industrial zone "
                        f"(planned network: >2 hops)"
                    )

        return issues
