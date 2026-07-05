"""Turn "the divisions I want to train" into a concrete equipment demand, priced
in IC and resources using the loaded game data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .gamedata import GameData


@dataclass
class EquipmentDemand:
    equipment: str
    units: float  # how many pieces are needed
    unit_cost_ic: float  # build_cost_ic per piece
    total_ic: float  # units * unit_cost_ic
    resources_per_unit: Dict[str, float] = field(default_factory=dict)


@dataclass
class Demand:
    by_equipment: Dict[str, EquipmentDemand]
    unknown_battalions: List[str] = field(default_factory=list)

    @property
    def total_ic(self) -> float:
        return sum(d.total_ic for d in self.by_equipment.values())

    def sorted(self) -> List[EquipmentDemand]:
        return sorted(self.by_equipment.values(), key=lambda d: d.total_ic, reverse=True)


def demand_for_order(gd: GameData, order: List[Tuple[str, int]]) -> Demand:
    """order = [(template_name, count), ...]. Sums each template's battalion
    equipment needs × count, then prices in IC and resources."""
    equip_units: Dict[str, float] = {}
    unknown: List[str] = []

    for template_name, count in order:
        tmpl = gd.templates.get(template_name)
        if tmpl is None:
            unknown.append(f"template:{template_name}")
            continue
        for bn, n in tmpl.battalions.items():
            batt = gd.battalions.get(bn)
            if batt is None:
                unknown.append(f"battalion:{bn}")
                continue
            for equip, qty in batt.need.items():
                equip_units[equip] = equip_units.get(equip, 0.0) + qty * n * count

    return _price(gd, equip_units, unknown)


def demand_for_battalions(gd: GameData, battalions: Dict[str, int]) -> Demand:
    """Ad-hoc demand from a raw battalion -> count map (no template needed)."""
    equip_units: Dict[str, float] = {}
    unknown: List[str] = []
    for bn, n in battalions.items():
        batt = gd.battalions.get(bn)
        if batt is None:
            unknown.append(f"battalion:{bn}")
            continue
        for equip, qty in batt.need.items():
            equip_units[equip] = equip_units.get(equip, 0.0) + qty * n
    return _price(gd, equip_units, unknown)


def _price(gd: GameData, equip_units: Dict[str, float], unknown: List[str]) -> Demand:
    by_equipment: Dict[str, EquipmentDemand] = {}
    for equip, units in equip_units.items():
        cost = gd.cost_of(equip)
        by_equipment[equip] = EquipmentDemand(
            equipment=equip,
            units=units,
            unit_cost_ic=cost,
            total_ic=units * cost,
            resources_per_unit=gd.resources_of(equip),
        )
    return Demand(by_equipment=by_equipment, unknown_battalions=unknown)
