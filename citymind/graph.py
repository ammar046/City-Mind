# graph.py: single CityGraph everyone shares. flood a road here and routing sees it instantly.
import math

# string labels for node kinds (matches project spec wording)
residential = "Residential"
hospital    = "Hospital"
school      = "School"
industrial  = "Industrial"
powerplant  = "PowerPlant"
depot       = "AmbulanceDepot"
empty       = "Empty"

# travel cost multipliers (project spec: High / Medium / Low only)
riskMult = {"High": 1.5, "Medium": 1.2, "Low": 1.0}


class CityNode:
    def __init__(self, nodeid, row, col):
        self.nodeid  = nodeid
        self.row     = row
        self.col     = col
        self.kind    = empty     # what type of location this is
        self.density = 0.0      # how many people are here roughly
        self.riskidx = 1.0      # gets updated by challenge 5
        self.blocked = False    # true if this spot is inaccessible
        self.cluster = -1       # which k-means cluster this ended up in
        self.risklvl = "Low"    # High Medium or Low
        self.ambcov  = False    # true if an ambulance can reach this fast enough

    def settype(self, kind, density=0.0):
        self.kind    = kind
        self.density = density

    def updaterisk(self, lvl):
        # updates the risk level and immediately changes the cost multiplier
        self.risklvl = lvl
        self.riskidx = riskMult.get(lvl, 1.0)

    def __repr__(self):
        return f"Node({self.nodeid} {self.kind} row={self.row} col={self.col})"


class CityEdge:
    def __init__(self, src, dst, basecost=1.0):
        self.src      = src
        self.dst      = dst
        self.basecost = basecost
        self.blocked  = False
        self.built    = False   # only True if kruskal actually selected this road

    @property
    def cost(self):
        # cant drive through a flooded road
        if self.blocked:
            return float("inf")
        # destination risk level multiplies the cost
        return self.basecost * self.dst.riskidx

    def block(self):
        self.blocked = True

    def unblock(self):
        self.blocked = False


class CityGraph:
    def __init__(self, rows, cols):
        self.rows    = rows
        self.cols    = cols
        self.nodes   = {}    # nodeid to CityNode
        self.adjlist = {}    # nodeid to list of edges
        self.edgemap = {}    # (src dst) pair to edge object

        # anything that registers here gets called when a road is blocked
        # challenge 4 uses this to know when to replan
        self.onblocked = []
        # called when a road becomes passable again (e.g. flood recedes)
        self.onunblocked = []

        # challenge 2: one designated primary hospital for depot redundancy (spec)
        self.primary_hospital_id = None
        self.primary_redundancy_path   = None  # list of node ids for UI
        self.secondary_redundancy_path = None

        for r in range(rows):
            for c in range(cols):
                nid = r * cols + c
                nd  = CityNode(nid, r, c)
                self.nodes[nid]   = nd
                self.adjlist[nid] = []

    def addedge(self, srcid, dstid, basecost=1.0):
        # roads go both ways
        src = self.nodes[srcid]
        dst = self.nodes[dstid]
        e1  = CityEdge(src, dst, basecost)
        e2  = CityEdge(dst, src, basecost)
        self.adjlist[srcid].append(e1)
        self.adjlist[dstid].append(e2)
        self.edgemap[(srcid, dstid)] = e1
        self.edgemap[(dstid, srcid)] = e2

    def hasedge(self, srcid, dstid):
        return (srcid, dstid) in self.edgemap

    def getedge(self, srcid, dstid):
        return self.edgemap.get((srcid, dstid), None)

    def blockroad(self, srcid, dstid):
        # marks both directions blocked then notifies listeners
        for pair in [(srcid, dstid), (dstid, srcid)]:
            e = self.edgemap.get(pair)
            if e:
                e.block()
        for fn in self.onblocked:
            fn(srcid, dstid)

    def unblockroad(self, srcid, dstid):
        for pair in [(srcid, dstid), (dstid, srcid)]:
            e = self.edgemap.get(pair)
            if e:
                e.unblock()
        for fn in self.onunblocked:
            fn(srcid, dstid)

    def allnodes(self):
        return list(self.nodes.values())

    def edgesof(self, nodeid):
        # only passable non blocked edges
        return [e for e in self.adjlist[nodeid] if not e.blocked]

    def allegedgesraw(self):
        # every edge including blocked ones, deduped
        seen = set()
        out  = []
        for eid, e in self.edgemap.items():
            key = tuple(sorted([e.src.nodeid, e.dst.nodeid]))
            if key not in seen:
                seen.add(key)
                out.append(e)
        return out

    def min_passable_built_edge_cost(self):
        """
        Minimum effective travel cost among built, passable edges (deduped).
        Used for an admissible A* heuristic: each step costs at least this much,
        so true cost >= c_min * manhattan_hops on the grid.
        Returns 0.0 if no such edge (heuristic becomes zero → Dijkstra-like).
        """
        m = float("inf")
        for e in self.allegedgesraw():
            if not e.built or e.blocked:
                continue
            c = e.cost
            if math.isfinite(c) and c < m:
                m = c
        return 0.0 if m == float("inf") else m

    def neighbors(self, nodeid):
        # returns (neighborid cost) pairs for passable roads only
        result = []
        for e in self.adjlist[nodeid]:
            if not e.blocked:
                result.append((e.dst.nodeid, e.cost))
        return result

    def euclidean(self, a, b):
        na = self.nodes[a]
        nb = self.nodes[b]
        return math.sqrt((na.row - nb.row)**2 + (na.col - nb.col)**2)

    def manhattan(self, a, b):
        na = self.nodes[a]
        nb = self.nodes[b]
        return abs(na.row - nb.row) + abs(na.col - nb.col)

    def bfshops(self, startid):
        # hop counts from startid ignoring whether roads are blocked
        # used during layout planning before roads exist
        dist  = {startid: 0}
        queue = [startid]
        while queue:
            cur = queue.pop(0)
            for e in self.adjlist[cur]:
                nid = e.dst.nodeid
                if nid not in dist:
                    dist[nid] = dist[cur] + 1
                    queue.append(nid)
        return dist

    def nodeof(self, row, col):
        return self.nodes[row * self.cols + col]

    def gridnbrs(self, nodeid):
        # up down left right neighbors on the grid regardless of road edges
        n   = self.nodes[nodeid]
        out = []
        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            r2, c2 = n.row + dr, n.col + dc
            if 0 <= r2 < self.rows and 0 <= c2 < self.cols:
                out.append(r2 * self.cols + c2)
        return out

    def refreshriskcosts(self):
        # edge costs are computed live as properties so they update automatically
        # this method exists as a hook for any future caching logic
        pass

    def assign_primary_hospital(self):
        # spec wants one "primary" hospital; we pick smallest id so its always the same run to run
        ids = sorted(n.nodeid for n in self.allnodes() if n.kind == hospital)
        self.primary_hospital_id = ids[0] if ids else None

    def __repr__(self):
        ec = len(self.edgemap) // 2
        return f"CityGraph({self.rows}x{self.cols} {len(self.nodes)} nodes {ec} edges)"
