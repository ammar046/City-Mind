# challenge2: Kruskal MST over the grid, then hack in a second disjoint path hospital<->depot.
# if one cheap extra edge isnt enough we keep activating off-primary edges until UCS finds plan B.

import heapq

from graph import residential, hospital, depot


class UnionFind:
    # bog standard disjoint set for cycle detection in Kruskal
    def __init__(self, n):
        self.parent = list(range(n))
        self.rank   = [0] * n

    def find(self, x):
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x, y):
        px, py = self.find(x), self.find(y)
        if px == py:
            return False
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1
        return True


class RoadBuilder:
    def __init__(self, graph):
        self.graph     = graph
        self.log       = []
        self.totalcost = 0.0

    def buildalledges(self):
        g = self.graph
        for r in range(g.rows):
            for c in range(g.cols):
                nid = r * g.cols + c
                if c + 1 < g.cols:
                    nid2 = r * g.cols + (c + 1)
                    cost = self._edgecost(nid, nid2)
                    if not g.hasedge(nid, nid2):
                        g.addedge(nid, nid2, cost)
                if r + 1 < g.rows:
                    nid2 = (r + 1) * g.cols + c
                    cost = self._edgecost(nid, nid2)
                    if not g.hasedge(nid, nid2):
                        g.addedge(nid, nid2, cost)

    def _edgecost(self, srcid, dstid):
        src = self.graph.nodes[srcid]
        dst = self.graph.nodes[dstid]
        if src.kind == residential or dst.kind == residential:
            return 0.8
        return 1.0

    @staticmethod
    def _dedupe_edges(g):
        seen = set()
        out  = []
        for e in g.allegedgesraw():
            k = tuple(sorted([e.src.nodeid, e.dst.nodeid]))
            if k not in seen:
                seen.add(k)
                out.append(e)
        return out

    @staticmethod
    def _built_edges_deduped(g):
        return [
            e for e in RoadBuilder._dedupe_edges(g)
            if e.built and not e.blocked
        ]

    @staticmethod
    def _bfs_path_from_edges(src, dst, edge_list):
        vis = {src}
        q   = [[src]]
        while q:
            p   = q.pop(0)
            cur = p[-1]
            if cur == dst:
                return p
            for e in edge_list:
                nb = None
                if e.src.nodeid == cur:
                    nb = e.dst.nodeid
                elif e.dst.nodeid == cur:
                    nb = e.src.nodeid
                if nb is not None and nb not in vis:
                    vis.add(nb)
                    q.append(p + [nb])
        return []

    @staticmethod
    def _primary_pair_set(path):
        s = set()
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            s.add((a, b))
            s.add((b, a))
        return s

    @staticmethod
    def _edge_on_primary_path(e, primary_pairs):
        a, b = e.src.nodeid, e.dst.nodeid
        return (a, b) in primary_pairs or (b, a) in primary_pairs

    def _ucs_secondary_path(self, g, hospid, depotid, primary_pairs):
        # uniform cost search, cant reuse edges from the first path (edge disjoint)
        available = []
        for e in self._dedupe_edges(g):
            if self._edge_on_primary_path(e, primary_pairs):
                continue
            available.append(e)

        openset = [(0.0, hospid, [hospid])]
        closed  = set()
        while openset:
            cost, cur, path = heapq.heappop(openset)
            if cur in closed:
                continue
            closed.add(cur)
            if cur == depotid:
                return path, cost
            for e in available:
                nb = None
                if e.src.nodeid == cur:
                    nb = e.dst.nodeid
                elif e.dst.nodeid == cur:
                    nb = e.src.nodeid
                if nb is not None and nb not in closed:
                    heapq.heappush(
                        openset,
                        (cost + e.basecost, nb, path + [nb]),
                    )
        return [], float("inf")

    def _activate_edge_undirected(self, g, e):
        # flip built=True both ways; return cost only if we actually added something new
        a, b = e.src.nodeid, e.dst.nodeid
        e0   = g.edgemap.get((a, b)) or g.edgemap.get((b, a))
        if not e0:
            return 0.0
        was_built = e0.built
        for pair in [(a, b), (b, a)]:
            if pair in g.edgemap:
                ed = g.edgemap[pair]
                ed.built   = True
                ed.blocked = False
        return 0.0 if was_built else e0.basecost

    def _materialize_path_edges(self, g, path):
        # turn every hop on this path into a real road if it wasnt already
        added_cost = 0.0
        new_edges  = 0
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            k1, k2 = (a, b), (b, a)
            e = g.edgemap.get(k1) or g.edgemap.get(k2)
            if not e:
                continue
            if not e.built:
                added_cost += e.basecost
                new_edges += 1
            for pair in (k1, k2):
                if pair in g.edgemap:
                    ed = g.edgemap[pair]
                    ed.built   = True
                    ed.blocked = False
        return added_cost, new_edges

    def run(self):
        self.log = []
        g = self.graph
        n = len(g.nodes)

        g.assign_primary_hospital()

        alledges = g.allegedgesraw()
        alledges.sort(key=lambda e: e.basecost)

        uf       = UnionFind(n)
        mstedges = []

        for e in alledges:
            sid = e.src.nodeid
            did = e.dst.nodeid
            if uf.union(sid, did):
                mstedges.append(e)
                if len(mstedges) == n - 1:
                    break  # tree has n-1 edges

        mstpairs = set()
        for e in mstedges:
            mstpairs.add((e.src.nodeid, e.dst.nodeid))
            mstpairs.add((e.dst.nodeid, e.src.nodeid))

        # everything not in MST starts blocked; challenge2 only drives on built=True edges
        for key, e in g.edgemap.items():
            e.blocked = key not in mstpairs

        for e in mstedges:
            k1 = (e.src.nodeid, e.dst.nodeid)
            k2 = (e.dst.nodeid, e.src.nodeid)
            if k1 in g.edgemap:
                g.edgemap[k1].blocked = False
                g.edgemap[k1].built   = True
            if k2 in g.edgemap:
                g.edgemap[k2].blocked = False
                g.edgemap[k2].built   = True

        self.totalcost = sum(e.basecost for e in mstedges)
        self.log.append(f"MST built with {len(mstedges)} roads total cost {self.totalcost:.2f}")

        self._addredundancy()
        return mstedges

    def _addredundancy(self):
        g = self.graph

        hospid = g.primary_hospital_id
        depotn = next((n for n in g.allnodes() if n.kind == depot), None)

        if hospid is None:
            self.log.append("No hospital in layout — cannot build depot redundancy route")
            g.primary_redundancy_path   = None
            g.secondary_redundancy_path = None
            return
        if depotn is None:
            self.log.append("No ambulance depot in layout — cannot build hospital redundancy route")
            g.primary_redundancy_path   = None
            g.secondary_redundancy_path = None
            return

        depotid = depotn.nodeid
        deduped = self._dedupe_edges(g)
        max_iter = len(deduped) + 24
        fallback_adds = 0

        for iteration in range(max_iter):
            built_list   = self._built_edges_deduped(g)
            primary_path = self._bfs_path_from_edges(hospid, depotid, built_list)

            if not primary_path:
                self.log.append(
                    "Redundancy: primary hospital and depot disconnected on built network"
                )
                g.primary_redundancy_path   = None
                g.secondary_redundancy_path = None
                return

            primary_pairs = self._primary_pair_set(primary_path)
            sec_path, _sec_cost = self._ucs_secondary_path(
                g, hospid, depotid, primary_pairs
            )

            if sec_path:
                add_cost, add_n = self._materialize_path_edges(g, sec_path)
                self.totalcost += add_cost
                self.log.append(
                    f"Redundancy: edge-disjoint secondary route "
                    f"({add_n} new segment(s), +{add_cost:.2f} cost)"
                )
                if fallback_adds:
                    self.log.append(
                        f"Redundancy: fallback added {fallback_adds} cheap off-primary edge(s) "
                        f"to enable disjoint routing"
                    )
                g.primary_redundancy_path   = primary_path
                g.secondary_redundancy_path = sec_path
                self.verify_redundancy(hospid, depotid)
                return

            candidates = [
                e for e in deduped
                if not e.built and not self._edge_on_primary_path(e, primary_pairs)
            ]
            candidates.sort(key=lambda e: e.basecost)

            if not candidates:
                self.log.append(
                    "Redundancy: exhausted candidates — no edge-disjoint second path possible"
                )
                g.primary_redundancy_path   = primary_path
                g.secondary_redundancy_path = None
                self.verify_redundancy(hospid, depotid)
                return

            pick = candidates[0]
            cadd = self._activate_edge_undirected(g, pick)
            self.totalcost += cadd
            fallback_adds += 1
            self.log.append(
                f"Redundancy fallback {fallback_adds}: activate off-primary edge "
                f"cost +{cadd:.2f} (attempt {iteration + 1})"
            )

        self.log.append("Redundancy: stopped after max fallback iterations")
        g.primary_redundancy_path   = None
        g.secondary_redundancy_path = None
        self.verify_redundancy(hospid, depotid)

    def verify_redundancy(self, hospid, depotid):
        g = self.graph

        def bfs_path(src, dst, skip=None):
            vis = {src}
            q   = [[src]]
            while q:
                p   = q.pop(0)
                cur = p[-1]
                if cur == dst:
                    return p
                for _key, e2 in g.edgemap.items():
                    if not e2.built or e2.blocked:
                        continue
                    nb = None
                    if e2.src.nodeid == cur:
                        nb = e2.dst.nodeid
                    elif e2.dst.nodeid == cur:
                        nb = e2.src.nodeid
                    if nb is not None and nb not in vis:
                        if skip and (
                            (cur, nb) == skip or (nb, cur) == skip
                        ):
                            continue
                        vis.add(nb)
                        q.append(p + [nb])
            return []

        primary = bfs_path(hospid, depotid)
        if not primary:
            self.log.append(
                "Verify: no path primary hospital–depot (graph disconnected)"
            )
            return
        all_ok = True
        for i in range(len(primary) - 1):
            skip = (primary[i], primary[i + 1])
            alt  = bfs_path(hospid, depotid, skip=skip)
            if not alt:
                all_ok = False
                break
        if all_ok:
            self.log.append(
                "Verify: primary hospital–depot redundancy OK "
                "(alternate path if any one edge on shortest route fails)"
            )
        else:
            self.log.append(
                "Verify: redundancy partial — not every edge on primary has a full alternate"
            )

    def getactualedges(self):
        seen = set()
        out  = []
        for key, e in self.graph.edgemap.items():
            k = tuple(sorted([e.src.nodeid, e.dst.nodeid]))
            if k not in seen and not e.blocked:
                seen.add(k)
                out.append(e)
        return out
