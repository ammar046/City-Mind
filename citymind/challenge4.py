# challenge4: A* router for the medic team. graph can change mid route so we hook onblocked/onunblocked.
#
# nearest_first=True: pick next civilian with cheapest shortest path from here (weighted "nearest").
# nearest_first=False: walk the list in order but skip to next reachable if head is cut off ([DEFER]).
#
# heuristic is c_min * manhattan so we stay admissible when edges are 0.8 vs 1.0 and risk bumps cost.

import heapq


class AStarRouter:
    def __init__(self, graph, nearest_first=True):
        self.graph         = graph
        self.nearest_first = nearest_first
        self.log           = []
        self.curpath      = []   # current planned route as node id list
        self.curidx       = 0    # how far along the path we are
        self.targets      = []   # original ordered list of all civilian node ids
        self.unvisited    = []   # remaining civilians in the same order (FIFO)
        self.curstep      = 0    # how many civilians we have dispatched toward
        self.rescuedcount = 0    # civilians physically reached
        self.pos          = None
        self.done         = False
        self.nextgoal     = None  # current routing target (may defer past blocked heads)
        self.failed       = False  # True if we failed strict "reach all" requirement

        self.graph.onblocked.append(self._onroadblocked)
        self.graph.onunblocked.append(self._onroadunblocked)

    def _onroadunblocked(self, srcid, dstid):
        # road came back: maybe we can finish a mission that previously hard-failed
        if self.done and not self.failed:
            return
        if self.failed:
            self.failed = False
            self.done = False
            self.log.append(
                f"[REOPEN] Road {srcid}<->{dstid} cleared — resuming mission from node {self.pos}"
            )
        else:
            self.log.append(
                f"[REOPEN] Road {srcid}<->{dstid} passable — recalculating shortest path "
                f"from node {self.pos}"
            )
        self._replan()

    def _seq_step_label(self):
        # little "3/4 civilians" style counter for logs
        if not self.targets or not self.unvisited:
            return 0, len(self.targets)
        k = len(self.targets) - len(self.unvisited) + 1
        return k, len(self.targets)

    def _onroadblocked(self, srcid, dstid):
        # if the flooded edge is still ahead of us on curpath, throw away plan and replan from pos
        if not self.curpath or self.done:
            return
        remaining = self.curpath[self.curidx:]
        for i in range(len(remaining) - 1):
            a, b = remaining[i], remaining[i + 1]
            if (a == srcid and b == dstid) or (a == dstid and b == srcid):
                self.log.append(
                    f"[REPLAN] Road {srcid}<->{dstid} blocked on route — "
                    f"recalculating shortest path from node {self.pos}"
                )
                self._replan()
                return

    def _shortest_path(self, startid, goalid):
        # classic A*; f = g + h, h scales manhattan by cheapest edge in the graph
        g    = self.graph
        cmin = g.min_passable_built_edge_cost()

        def heuristic(nid):
            return cmin * g.manhattan(nid, goalid)

        tie       = 0
        openset   = [(heuristic(startid), tie, 0.0, startid)]
        came_from = {}
        g_score   = {startid: 0.0}
        closed    = set()

        while openset:
            _f, _t, cost, cur = heapq.heappop(openset)
            if cur in closed:
                continue
            closed.add(cur)

            if cur == goalid:
                path = []
                node = goalid
                while node != startid:
                    path.append(node)
                    node = came_from[node]
                path.append(startid)
                path.reverse()
                return path, cost

            for nbid, ecost in g.neighbors(cur):
                if nbid in closed:
                    continue
                newcost = cost + ecost
                if newcost < g_score.get(nbid, float("inf")):
                    g_score[nbid] = newcost
                    came_from[nbid] = cur
                    h = heuristic(nbid)
                    tie += 1
                    heapq.heappush(openset, (newcost + h, tie, newcost, nbid))

        return [], float("inf")

    def setup(self, startid, civilianids):
        self.pos          = startid
        self.targets      = list(civilianids)
        self.unvisited    = list(civilianids)
        self.curstep      = 0
        self.rescuedcount = 0
        self.done         = False
        self.failed       = False
        self.curidx       = 0
        self.nextgoal     = None
        self.log          = []
        self._replan()

    def _fail_no_reachable_survivor(self):
        self.failed = True
        self.done   = True
        self.curpath   = []
        self.curidx    = 0
        self.nextgoal  = None
        rem = list(self.unvisited)
        self.log.append(
            f"MISSION FAILED: no path from node {self.pos} to any remaining civilian "
            f"{rem} — graph cut off (cannot reach all)"
        )

    def _replan(self):
        if self.failed:
            return

        # no one left to save
        if not self.unvisited:
            self.done    = True
            self.curpath = []
            if self.rescuedcount == len(self.targets):
                self.log.append("MISSION COMPLETE: All civilians reached")
            else:
                self.log.append(
                    f"MISSION FAILED: Only rescued {self.rescuedcount}/{len(self.targets)} civilians"
                )
            return

        preferred = self.unvisited[0]
        goal, path = None, None
        best_cost = float("inf")
        best_idx  = None

        if self.nearest_first:
            for i, candidate in enumerate(self.unvisited):
                p, c = self._shortest_path(self.pos, candidate)
                if not p:
                    continue
                if c < best_cost - 1e-9 or (
                    abs(c - best_cost) < 1e-9 and (best_idx is None or i < best_idx)
                ):
                    best_cost, goal, path, best_idx = c, candidate, p, i
        else:
            for i, candidate in enumerate(self.unvisited):
                p, c = self._shortest_path(self.pos, candidate)
                if p:
                    goal, path, best_cost, best_idx = candidate, p, c, i
                    break

        if not path:
            self._fail_no_reachable_survivor()
            return

        if goal != preferred:
            if self.nearest_first:
                self.log.append(
                    f"[NEAREST] Chosen survivor {goal} (route cost {best_cost:.2f}) "
                    f"before in-list head {preferred} — minimum travel from node {self.pos}"
                )
            else:
                self.log.append(
                    f"[DEFER] No path to in-order survivor {preferred}; "
                    f"continuing mission toward {goal} (shortest path, reach-all)"
                )

        self.nextgoal = goal
        self.curpath  = path
        self.curidx   = 0
        k, m = self._seq_step_label()
        mode = "nearest-cost" if self.nearest_first else "in-order"
        self.log.append(
            f"[ROUTE] Target civilian node {goal} (progress {k}/{m}, {mode}), "
            f"{len(path) - 1} edge(s) on shortest path"
        )

    def step(self):
        if self.done or not self.curpath:
            return self.pos

        self.curidx += 1
        # reached end of current path segment = at a civilian (or intermediate, shouldnt happen)
        if self.curidx >= len(self.curpath):
            self.pos = self.curpath[-1]
            self.log.append(
                f"[RESCUE] Reached civilian at node {self.pos} "
                f"({self.rescuedcount + 1}/{len(self.targets)} in sequence)"
            )
            self.rescuedcount += 1
            self.curstep      += 1
            if self.unvisited and self.unvisited[0] == self.nextgoal:
                self.unvisited.pop(0)
            elif self.nextgoal in self.unvisited:
                self.unvisited.remove(self.nextgoal)
            self.nextgoal = None
            self._replan()
        else:
            self.pos = self.curpath[self.curidx]

        return self.pos

    def getfullpath(self):
        if not self.curpath:
            return []
        return self.curpath[self.curidx:]
