"""Route Reliability Index (RRI) and Dijkstra pathfinding over the simulated graph.

HONESTY NOTE: the RRI is a hand-set logistic scoring formula over synthetic weather, slope and
closure-history inputs. It is not a trained model, and a high RRI never means a route is
operationally safe. Segment reliabilities are combined assuming independence.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Node, Route

RRI_VERSION = "HV-RRI-Formula v0.2 (rule-based, not trained)"
FUEL_L_PER_KM_ROAD = 0.8  # assumed aggregate convoy consumption, illustrative only
FUEL_L_PER_KM_AIR = 3.5   # assumed rotary-wing consumption, illustrative only
ROAD_COEF = {"intercept": 4.4, "rain_mm": -0.04, "snow_cm": -0.06, "slope_risk": -2.6, "closure_count": -0.25}
AIR_COEF = {"intercept": 3.0, "rain_mm": -0.02, "snow_cm": -0.14}


def risk_class(rri: float | None, closed: bool) -> str:
    if closed:
        return "closed"
    if rri is None or rri < 0.5:
        return "high"
    if rri < 0.7:
        return "elevated"
    if rri < 0.85:
        return "moderate"
    return "low"


def assess(r: dict, rain: float | None = None, snow: float | None = None) -> dict:
    """Assess a route snapshot dict. rain/snow override the stored scenario inputs (what-if)."""
    rain = r["rain_mm"] if rain is None else rain
    snow = r["snow_cm"] if snow is None else snow
    coef = AIR_COEF if r["mode"] == "air" else ROAD_COEF
    inputs = {"rain_mm": rain, "snow_cm": snow, "slope_risk": r["slope_risk"], "closure_count": r["closure_count"]}
    contrib = {"intercept": coef["intercept"]}
    for k, c in coef.items():
        if k != "intercept":
            contrib[k] = c * inputs[k]
    z = sum(contrib.values())
    rri = 1 / (1 + math.exp(-z))
    closed = bool(r.get("closed"))
    if r["mode"] == "air":
        time_h = r["base_time_h"] * (1 + 0.005 * rain + 0.01 * snow)
    else:
        time_h = r["base_time_h"] * (1 + 0.012 * rain + 0.02 * snow + 0.4 * r["slope_risk"])
    neg = sorted(((k, v) for k, v in contrib.items() if k != "intercept" and v < 0), key=lambda kv: kv[1])
    labels = {"rain_mm": "rainfall", "snow_cm": "snowfall", "slope_risk": "terrain/slope risk", "closure_count": "closure history"}
    if closed:
        why = "Segment is closed; reliability is not applicable until it reopens."
    elif neg:
        why = "Reliability is reduced mainly by " + ", ".join(f"{labels[k]} ({v:+.2f})" for k, v in neg[:3]) + " in the scoring formula."
    else:
        why = "No adverse factors in the scoring formula."
    return {"route_id": r["id"], "rri": None if closed else round(rri, 3), "risk": risk_class(rri, closed), "closed": closed,
            "time_h": round(time_h, 2), "inputs": inputs, "contributions": {k: round(v, 3) for k, v in contrib.items()},
            "explanation": why, "formula": RRI_VERSION}


def route_snapshot(r: Route) -> dict:
    return {"id": r.id, "a": r.a, "b": r.b, "mode": r.mode, "distance_km": r.distance_km, "base_time_h": r.base_time_h,
            "slope_risk": r.slope_risk, "closure_count": r.closure_count, "rain_mm": r.rain_mm, "snow_cm": r.snow_cm,
            "closed": r.status == "closed"}


@dataclass
class RouteNet:
    nodes: dict[str, dict]
    routes: dict[str, dict]
    _assess: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_db(cls, db: Session) -> "RouteNet":
        nodes = {n.id: {"id": n.id, "name": n.name, "kind": n.kind, "lat": n.lat, "lon": n.lon, "helipad": n.helipad} for n in db.scalars(select(Node))}
        routes = {r.id: route_snapshot(r) for r in db.scalars(select(Route))}
        return cls(nodes, routes)

    def copy(self) -> "RouteNet":
        return RouteNet(self.nodes, {k: dict(v) for k, v in self.routes.items()})

    def a(self, rid: str) -> dict:
        if rid not in self._assess:
            self._assess[rid] = assess(self.routes[rid])
        return self._assess[rid]

    def invalidate(self) -> None:
        self._assess.clear()

    def adjacency(self, mode: str, blocked: set[str]) -> dict[str, list[tuple[str, str]]]:
        adj: dict[str, list[tuple[str, str]]] = {}
        for r in self.routes.values():
            if r["mode"] != mode or r["closed"] or r["id"] in blocked:
                continue
            adj.setdefault(r["a"], []).append((r["b"], r["id"]))
            adj.setdefault(r["b"], []).append((r["a"], r["id"]))
        return adj

    def _cost(self, rid: str, objective: str) -> float:
        a = self.a(rid)
        if objective == "fastest":
            return a["time_h"]
        return -math.log(max(a["rri"] or 1e-3, 1e-3)) + 0.05 * a["time_h"]

    def shortest(self, src: str, dst: str, objective: str = "fastest", mode: str = "road", blocked: set[str] | None = None) -> dict | None:
        adj = self.adjacency(mode, blocked or set())
        dist, prev = {src: 0.0}, {}
        heap = [(0.0, src)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist.get(u, math.inf):
                continue
            if u == dst:
                break
            for v, rid in adj.get(u, []):
                nd = d + self._cost(rid, objective)
                if nd < dist.get(v, math.inf):
                    dist[v], prev[v] = nd, (u, rid)
                    heapq.heappush(heap, (nd, v))
        if dst not in dist:
            return None
        nodes, rids, cur = [dst], [], dst
        while cur != src:
            cur, rid = prev[cur][0], prev[cur][1]
            nodes.append(cur)
            rids.append(rid)
        nodes.reverse()
        rids.reverse()
        return self.describe(nodes, rids, mode, objective)

    def describe(self, nodes: list[str], rids: list[str], mode: str, objective: str) -> dict:
        segs, reliability, time_h, dist = [], 1.0, 0.0, 0.0
        for i, rid in enumerate(rids):
            a, r = self.a(rid), self.routes[rid]
            reliability *= a["rri"] or 0.0
            time_h += a["time_h"]
            dist += r["distance_km"]
            segs.append({"route_id": rid, "from": nodes[i], "to": nodes[i + 1], "time_h": a["time_h"], "rri": a["rri"], "risk": a["risk"]})
        fuel = dist * (FUEL_L_PER_KM_AIR if mode == "air" else FUEL_L_PER_KM_ROAD)
        return {"mode": mode, "objective": objective, "nodes": nodes, "route_ids": rids, "segments": segs,
                "distance_km": round(dist, 1), "time_h": round(time_h, 1), "reliability": round(reliability, 3),
                "weakest_rri": round(min((s["rri"] or 0) for s in segs), 3) if segs else 1.0, "fuel_l": round(fuel),
                "assumptions": "Fuel uses an illustrative per-km constant; reliability multiplies segment RRIs assuming independence."}

    def depots(self) -> list[str]:
        return [n["id"] for n in self.nodes.values() if n["kind"] in ("depot",)]

    def air_sources(self) -> list[str]:
        return [n["id"] for n in self.nodes.values() if n["kind"] in ("depot", "airfield")]

    def plan_to(self, dst: str, k_alt: int = 3) -> dict:
        """Best road plans (fastest vs most reliable) from the best depot, alternatives, and an air option."""
        best: dict[str, dict | None] = {"fastest": None, "reliable": None}
        for dep in self.depots():
            for obj in ("fastest", "reliable"):
                p = self.shortest(dep, dst, obj)
                if p is None:
                    continue
                cur = best[obj]
                key = (lambda x: x["time_h"]) if obj == "fastest" else (lambda x: -x["reliability"])
                if cur is None or key(p) < key(cur):
                    best[obj] = {**p, "origin": dep}
        alts: list[dict] = []
        seen = {tuple(p["route_ids"]) for p in best.values() if p}
        base = best["fastest"] or best["reliable"]
        if base:
            for rid in base["route_ids"]:
                for obj in ("fastest", "reliable"):
                    p = self.shortest(base["origin"], dst, obj, blocked={rid})
                    if p and tuple(p["route_ids"]) not in seen:
                        seen.add(tuple(p["route_ids"]))
                        alts.append({**p, "origin": base["origin"], "avoids": rid})
        alts.sort(key=lambda x: (-x["reliability"], x["time_h"]))
        air = None
        for src in self.air_sources():
            for r in self.routes.values():
                if r["mode"] == "air" and not r["closed"] and {r["a"], r["b"]} == {src, dst}:
                    p = self.describe([src, dst], [r["id"]], "air", "air")
                    if air is None or p["time_h"] < air["time_h"]:
                        air = {**p, "origin": src}
        return {"fastest": best["fastest"], "reliable": best["reliable"], "alternatives": alts[:k_alt], "air": air,
                "road_reachable": best["fastest"] is not None}
