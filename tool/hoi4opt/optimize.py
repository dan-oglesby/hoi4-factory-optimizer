"""Balanced military-factory allocation.

Goal: given the equipment demand for the divisions you want and a number of
military factories, split the factories across equipment types so all the needed
equipment finishes as close to simultaneously as possible. That is what
"maximizes the divisions you can field" means in practice — you are gated by the
*slowest* equipment type, so you want to minimize the max completion time.

Key fact that makes this tractable: every military factory contributes the same
IC/day to whatever line it's on. If equipment type i needs C_i total IC and gets
f_i factories, its completion time is proportional to C_i / f_i. Minimizing the
maximum C_i / f_i subject to sum(f_i) = N is solved by allocating factories in
proportion to C_i. We then handle the integer rounding (largest remainder), the
per-line factory cap, and resource limits.

Resource handling: each equipment declares `resources = { steel = 2, ... }` per
unit. Given a per-day resource budget, we detect lines whose resource draw would
exceed supply and cap them, redistributing freed factories to the next-most
demanding lines that still have resource headroom. This is a first-order,
transparent heuristic — see docs/DESIGN.md for the modeling notes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .needs import Demand, EquipmentDemand


@dataclass
class LineAllocation:
    equipment: str
    factories: int
    total_ic: float
    ic_per_day: float
    units_per_day: float
    days_to_complete: float
    resources_per_day: Dict[str, float] = field(default_factory=dict)


@dataclass
class Plan:
    lines: List[LineAllocation]
    factories_used: int
    factories_available: int
    completion_days: float  # the slowest line (the bottleneck)
    bottleneck: Optional[str]
    resource_totals: Dict[str, float] = field(default_factory=dict)
    resource_warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _largest_remainder(weights: List[float], total: int) -> List[int]:
    """Apportion `total` integer units across items proportional to weights."""
    s = sum(weights)
    if s <= 0 or total <= 0:
        return [0] * len(weights)
    raw = [w / s * total for w in weights]
    base = [int(x) for x in raw]
    remainder = total - sum(base)
    # hand out the leftover to the largest fractional parts
    order = sorted(range(len(weights)), key=lambda i: raw[i] - base[i], reverse=True)
    for k in range(remainder):
        base[order[k % len(order)]] += 1
    return base


def allocate(
    demand: Demand,
    factories: int,
    factory_output: float = 4.5,
    efficiency: float = 1.0,
    max_per_line: int = 15,
    resource_budget: Optional[Dict[str, float]] = None,
) -> Plan:
    """Compute a balanced allocation.

    factory_output * efficiency = IC/day produced per factory (defaults reflect a
    ~4.5 base military factory at full efficiency; the *proportions* are
    independent of this constant, it only scales the day estimates).
    """
    items: List[EquipmentDemand] = [d for d in demand.sorted() if d.total_ic > 0]
    notes: List[str] = []
    if not items:
        return Plan([], 0, factories, 0.0, None, notes=["No equipment demand to allocate."])

    per_factory = factory_output * efficiency

    # 1) Ideal proportional split by total IC.
    weights = [d.total_ic for d in items]
    alloc = _largest_remainder(weights, factories)

    # 2) Enforce per-line cap, spilling excess onto lines with headroom.
    alloc = _apply_caps(alloc, weights, max_per_line, factories, notes)

    # 3) Resource-aware correction (optional).
    warnings: List[str] = []
    if resource_budget:
        alloc = _apply_resource_budget(
            items, alloc, weights, per_factory, resource_budget, max_per_line, warnings
        )

    # 4) Build the plan.
    lines: List[LineAllocation] = []
    resource_totals: Dict[str, float] = {}
    for d, f in zip(items, alloc):
        ic_day = f * per_factory
        units_day = ic_day / d.unit_cost_ic if d.unit_cost_ic > 0 else 0.0
        days = d.total_ic / ic_day if ic_day > 0 else float("inf")
        res_day = {r: v * units_day for r, v in d.resources_per_unit.items()}
        for r, v in res_day.items():
            resource_totals[r] = resource_totals.get(r, 0.0) + v
        lines.append(
            LineAllocation(
                equipment=d.equipment,
                factories=f,
                total_ic=d.total_ic,
                ic_per_day=ic_day,
                units_per_day=units_day,
                days_to_complete=days,
                resources_per_day=res_day,
            )
        )

    active = [ln for ln in lines if ln.factories > 0]
    completion = max((ln.days_to_complete for ln in active), default=0.0)
    bottleneck = None
    if active:
        slow = max(active, key=lambda ln: ln.days_to_complete)
        bottleneck = slow.equipment

    if resource_budget:
        for r, used in resource_totals.items():
            cap = resource_budget.get(r)
            if cap is not None and used > cap + 1e-6:
                warnings.append(
                    f"{r}: plan draws {used:.1f}/day but budget is {cap:.1f}/day"
                )

    lines.sort(key=lambda ln: ln.total_ic, reverse=True)
    return Plan(
        lines=lines,
        factories_used=sum(alloc),
        factories_available=factories,
        completion_days=completion,
        bottleneck=bottleneck,
        resource_totals=resource_totals,
        resource_warnings=warnings,
        notes=notes,
    )


def _apply_caps(
    alloc: List[int], weights: List[float], max_per_line: int, factories: int, notes: List[str]
) -> List[int]:
    alloc = list(alloc)
    while True:
        overflow = 0
        capped = [False] * len(alloc)
        for i in range(len(alloc)):
            if alloc[i] > max_per_line:
                overflow += alloc[i] - max_per_line
                alloc[i] = max_per_line
        if overflow == 0:
            break
        # redistribute overflow to lines under the cap, by weight
        room_idx = [i for i in range(len(alloc)) if alloc[i] < max_per_line]
        if not room_idx:
            notes.append(
                f"All lines hit the {max_per_line}-factory cap; "
                f"{overflow} factories left unassigned."
            )
            break
        room_weights = [weights[i] for i in room_idx]
        extra = _largest_remainder(room_weights, overflow)
        for k, i in enumerate(room_idx):
            alloc[i] += extra[k]
        # loop again in case redistribution pushed a line over the cap
    return alloc


def _apply_resource_budget(
    items: List[EquipmentDemand],
    alloc: List[int],
    weights: List[float],
    per_factory: float,
    budget: Dict[str, float],
    max_per_line: int,
    warnings: List[str],
) -> List[int]:
    """Reduce factories on lines that bust a resource budget, one resource at a
    time, freeing factories to lines that don't consume the scarce resource."""
    alloc = list(alloc)
    for _ in range(len(items) * 2):  # bounded fixpoint
        # compute per-resource draw
        draw: Dict[str, float] = {}
        contrib: Dict[str, List[int]] = {}
        for i, d in enumerate(items):
            units_day = (alloc[i] * per_factory / d.unit_cost_ic) if d.unit_cost_ic > 0 else 0
            for r, v in d.resources_per_unit.items():
                draw[r] = draw.get(r, 0.0) + v * units_day
                contrib.setdefault(r, []).append(i)
        # find the worst over-budget resource
        worst = None
        worst_over = 0.0
        for r, used in draw.items():
            cap = budget.get(r)
            if cap is not None and used - cap > worst_over:
                worst_over = used - cap
                worst = r
        if worst is None:
            break
        # take one factory from the heaviest consumer of `worst`, give it to the
        # heaviest line that doesn't use `worst` (else the highest-weight other line)
        consumers = [i for i in contrib[worst] if alloc[i] > 0]
        if not consumers:
            break
        giver = max(consumers, key=lambda i: items[i].resources_per_unit.get(worst, 0) * weights[i])
        non_users = [
            i for i in range(len(items))
            if worst not in items[i].resources_per_unit and alloc[i] < max_per_line
        ]
        pool = non_users or [
            i for i in range(len(items)) if i != giver and alloc[i] < max_per_line
        ]
        if not pool:
            # No line can absorb the moved factory without also using the scarce
            # resource (or all have hit the cap). Reallocation can't fix a genuine
            # supply shortfall — keep the factories working and let the warning
            # report the shortage rather than idling factories.
            break
        taker = max(pool, key=lambda i: weights[i])
        alloc[giver] -= 1
        alloc[taker] += 1
    return alloc
