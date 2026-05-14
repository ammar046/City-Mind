# simulation.py: glues all 5 challenges into one stepped run (see numsteps at bottom).
# order is strict: layout, roads, crime ML, ambulance GA, then the A* router.
# one nextstep() = one sim tick. floods use wall clock timers; UI should call expire_floods() each frame too.

import random
import time
from graph import CityGraph, hospital, depot, residential
from challenge1 import CSPLayout, validate_built_road_network
from challenge2 import RoadBuilder
from challenge3 import GeneticAmbulance
from challenge4 import AStarRouter
from challenge5 import CrimeRisk

gridrows = 8
gridcols = 8
numsteps = 50  # spec evaluation scenario
# Floods block roads for a random duration in real time (seconds), then clear (Challenge 4 dynamic graph).
flood_duration_min_s = 4.0
flood_duration_max_s = 4.0
# Challenge 4: True = pick next survivor with minimum shortest-path cost (demo option).
# False = visit civilians in stated sequence (spec); defer if head unreachable.
router_nearest_first = False


class Simulation:
    def __init__(self):
        self.graph     = CityGraph(gridrows, gridcols)
        self.step      = 0
        self.maxsteps  = numsteps
        self.eventlog  = []
        self.running   = False
        self.finished  = False

        self.layout    = None
        self.roads     = None
        self.ambulance = None
        self.router    = None
        self.crime     = None

        self.ambplaces     = []
        self.teampos       = None
        self.civilians     = []
        self.flooded       = []   # roads that were blocked this session
        self.floodcount    = 0   # total roads flooded during simulation
        self.active_floods = []   # list of {a,b,expires}; same road can flood twice with stacked timers
        self.reroutecount  = 0   # total times A* had to replan
        self._router_was_done = False  # for one-shot mission outcome log when router finishes
        self.officermap    = {}  # nodeid -> officer count (Challenge 5 output)
        self.built_network_issues = []  # post-MST hop violations (challenge1)

        self.onstep = None   # optional callback for UI

    def _log(self, msg):
        self.eventlog.append(f"Step {self.step}: {msg}")

    def _flush_router_log(self):
        # router keeps its own tiny log; we merge it into the big event log for the UI
        if not self.router:
            return
        for msg in self.router.log:
            self._log(msg)
            if msg.startswith("[REPLAN]"):
                self.reroutecount += 1
        self.router.log = []

    def setup(self):
        self.active_floods = []
        self._router_was_done = False
        self._log("Initializing CityMind")

        # challenge 1 - CSP layout planning
        self.layout = CSPLayout(self.graph)
        valid       = self.layout.run()
        for msg in self.layout.log:
            self._log(msg)
        issues = self.layout.validate()
        if issues:
            self._log(f"Layout has {len(issues)} constraint violation(s)")
        else:
            self._log("Layout valid 0 violations")

        # challenge 2 - kruskal road network
        self.roads = RoadBuilder(self.graph)
        self.roads.buildalledges()
        self.roads.run()
        for msg in self.roads.log:
            self._log(msg)

        self.built_network_issues = validate_built_road_network(self.graph)
        if self.built_network_issues:
            self._log(
                f"Post-road layout check: {len(self.built_network_issues)} issue(s) "
                f"under built MST (residential/hospital or powerplant/industrial hops)"
            )
            for line in self.built_network_issues[:12]:
                self._log(f"  [built-road] {line}")
            if len(self.built_network_issues) > 12:
                self._log(
                    f"  ... and {len(self.built_network_issues) - 12} more (planned-grid CSP may still be valid)"
                )
        else:
            self._log(
                "Post-road layout check: residential/hospital (≤3) and powerplant/industrial (≤2) "
                "satisfied on built roads"
            )

        # challenge 5 - crime risk needs roads to exist for distance calculations
        self.crime = CrimeRisk(self.graph)
        self.crime.run()
        for msg in self.crime.log:
            self._log(msg)

        # allocate 10 police officers to the highest-risk nodes
        self.officermap = self._allocateofficers(10)
        hotspots = sorted(self.officermap.items(), key=lambda kv: kv[1], reverse=True)
        top3 = [(self.graph.nodes[nid].kind, cnt) for nid, cnt in hotspots[:3]]
        self._log(
            f"Police allocation: 10 officers deployed to {len(self.officermap)} high-risk zones "
            f"(top zones: {top3})"
        )

        # challenge 3 - GA ambulance placement using updated edge costs from crime
        self.ambulance = GeneticAmbulance(self.graph)
        self.ambplaces = self.ambulance.run()
        for msg in self.ambulance.log[-2:]:
            self._log(msg)

        # challenge 4 - A* routing setup
        self.router = AStarRouter(self.graph, nearest_first=router_nearest_first)
        self.civilians = self._pickcivilians()
        start          = self._pickstart()
        self.teampos   = start
        civ_ids = [c.nodeid for c in self.civilians]
        self.router.setup(start, civ_ids)
        rmode = "nearest survivor (min route cost)" if router_nearest_first else "in-list order + defer"
        self._log(
            f"[ROUTING] Start {start}; survivors {civ_ids}; mode: {rmode}"
        )
        self._flush_router_log()

        self.running  = True
        self.finished = False

    def _pickcivilians(self):
        # pick 4 residential high density nodes as trapped civilians
        picks = [n for n in self.graph.allnodes()
                 if n.kind == residential and n.density > 40]
        random.shuffle(picks)
        return picks[:4] or self.graph.allnodes()[:4]

    def _allocateofficers(self, total_officers=10):
        # spread 10 cops: highs get at least one each, leftovers go to mediums (simple heuristic)
        nodes = self.graph.allnodes()
        high  = [n for n in nodes if n.risklvl == "High"]
        med   = [n for n in nodes if n.risklvl == "Medium"]

        allocation = {}
        remaining  = total_officers

        if high:
            # each high-risk node gets at least 1 officer
            per_high = max(1, remaining // max(1, len(high)))
            for n in high:
                give = min(per_high, remaining)
                allocation[n.nodeid] = give
                remaining -= give
                if remaining <= 0:
                    break

        # spread remainder across medium nodes
        if remaining > 0 and med:
            per_med = max(1, remaining // max(1, len(med)))
            for n in med:
                give = min(per_med, remaining)
                allocation[n.nodeid] = allocation.get(n.nodeid, 0) + give
                remaining -= give
                if remaining <= 0:
                    break

        return allocation

    def _pickstart(self):
        # team starts from depot if one exists otherwise hospital
        dep  = next((n for n in self.graph.allnodes() if n.kind == depot),    None)
        hosp = next((n for n in self.graph.allnodes() if n.kind == hospital), None)
        if dep:
            return dep.nodeid
        if hosp:
            return hosp.nodeid
        return 0

    def expire_floods(self, now=None):
        # when timer hits we unblock; if two floods stacked on same edge wait until both expire
        if not self.active_floods:
            return
        now = time.monotonic() if now is None else now
        expired = [e for e in self.active_floods if now >= e["expires"]]
        self.active_floods = [e for e in self.active_floods if now < e["expires"]]
        for e in expired:
            a, b = e["a"], e["b"]
            lo, hi = min(a, b), max(a, b)
            still = any(
                min(x["a"], x["b"]) == lo and max(x["a"], x["b"]) == hi for x in self.active_floods
            )
            if not still:
                self.graph.unblockroad(a, b)
                self._log(
                    f"[FLOOD CLEARED] Road {a}<->{b} passable again — shared graph updated"
                )
                self._flush_router_log()

    def nextstep(self):
        if self.finished or not self.running:
            return

        self.expire_floods()
        self.step += 1

        # random road flood chance increases after step 3
        if self.step > 3 and random.random() < 0.40:
            self._floodrandomroad()

        # move the medical team one step (router may emit [RESCUE], [ROUTE], mission lines)
        if not self.router.done:
            prevpos      = self.teampos
            newpos       = self.router.step()
            self.teampos = newpos
            if newpos != prevpos:
                self._log(f"[MOVE] Team {prevpos} → {newpos}")
            self._flush_router_log()

        # refresh crime risk every 4 steps so edge costs evolve during simulation
        if self.step % 4 == 0:
            self.crime.run()
            self.officermap = self._allocateofficers(10)
            self._log(
                "[INTEGRATE] Crime model refreshed — edge weights and officer map updated "
                "(ambulance GA re-runs every 10 steps on same graph)"
            )

        # re-run GA ambulance placement every 10 steps as risk weights have shifted
        if self.step % 10 == 0 and not self.finished:
            self.ambplaces = self.ambulance.run()
            self._log(
                f"[INTEGRATE] Ambulance GA re-run — nodes {self.ambplaces}, "
                f"worst-case response dist {self.ambulance.bestmaxdist:.2f}"
            )

        # Log once when the router reaches a terminal state; simulation keeps running until maxsteps.
        if not self.router.done:
            self._router_was_done = False
        elif not self._router_was_done:
            self._router_was_done = True
            if self.router.rescuedcount == len(self.civilians):
                self._log("[OUTCOME] All civilians reached (routing complete before final step)")
            else:
                self._log(
                    f"[OUTCOME] Routing ended early — rescued {self.router.rescuedcount}/"
                    f"{len(self.civilians)} (may improve if flooded roads clear)"
                )

        if self.step >= self.maxsteps:
            self._log(
                f"[OUTCOME] Simulation complete ({self.maxsteps} steps) — "
                f"civilians rescued {self.router.rescuedcount}/{len(self.civilians)}"
            )
            self.finished = True

        if self.onstep:
            self.onstep(self.step)

    def _floodrandomroad(self):
        picks = [e for e in self.roads.getactualedges() if not e.blocked]
        if not picks:
            return
        e = random.choice(picks)
        a, b = e.src.nodeid, e.dst.nodeid
        duration = random.uniform(flood_duration_min_s, flood_duration_max_s)
        self._log(
            f"[FLOOD] Road {a}<->{b} impassable for ~{duration:.1f}s — shared graph updated"
        )
        self.flooded.append((a, b))
        self.floodcount += 1
        self.active_floods.append(
            {"a": a, "b": b, "expires": time.monotonic() + duration}
        )
        # Synchronous onblocked → [REPLAN] + [ROUTE] queued on router
        self.graph.blockroad(a, b)
        self._flush_router_log()

    def runall(self):
        while not self.finished and self.step < self.maxsteps:
            self.nextstep()

    def statusdict(self):
        violations = self.layout.validate() if self.layout else []
        return {
            "layout":       f"Valid ({len(violations)} violations)",
            "roadcost":     f"{self.roads.totalcost:.2f}" if self.roads else "N/A",
            "ambplaces":    self.ambplaces,
            "maxdist":      f"{self.ambulance.bestmaxdist:.2f}" if self.ambulance and self.ambulance.bestmaxdist < 1e8 else "N/A",
            "teampos":      self.teampos,
            "route":        self.router.getfullpath() if self.router else [],
            "remaining":    len(self.router.unvisited) if self.router else 0,
            "rescued":      self.router.rescuedcount if self.router else 0,
            "step":         self.step,
            "done":         self.finished,
            "floodcount":   self.floodcount,
            "activefloods": len(self.active_floods),
            "reroutecount": self.reroutecount,
            "officermap":   self.officermap,
            "violations":   len(violations),
            "conflictrule": getattr(self.layout, "lastrule", ""),
            "built_network_violations": len(self.built_network_issues),
        }
