"""Load HOI4 game data (equipment archetypes, battalions, division templates) from
the base game plus any active mods, honoring load order.

Everything here reads the *actual* files, so it is inherently mod-agnostic: if a
mod adds `space_marine_equipment` with `resources = { unobtainium = 5 }`, this code
picks it up with no changes. Nothing about the equipment or resource list is
hard-coded.

Mod overlay model (v0.1): a mod file at the same relative path as a base file
*replaces* it (this matches HOI4's default "same-path replace" behavior for most
`common/units/**` files). `replace_path` directives and partial-file merges are
not yet modeled; see docs/DESIGN.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import pdxparse
from .pdxparse import Block


@dataclass
class Equipment:
    name: str
    is_archetype: bool
    archetype: Optional[str]  # parent archetype name, if this is a variant
    build_cost_ic: Optional[float]
    resources: Dict[str, float] = field(default_factory=dict)

    def resolved_cost(self, table: "Dict[str, Equipment]") -> float:
        """build_cost_ic, inheriting from the archetype chain when unset."""
        eq = self
        seen = set()
        while eq is not None and eq.name not in seen:
            if eq.build_cost_ic is not None:
                return eq.build_cost_ic
            seen.add(eq.name)
            eq = table.get(eq.archetype) if eq.archetype else None
        return 0.0

    def resolved_resources(self, table: "Dict[str, Equipment]") -> Dict[str, float]:
        eq = self
        seen = set()
        while eq is not None and eq.name not in seen:
            if eq.resources:
                return dict(eq.resources)
            seen.add(eq.name)
            eq = table.get(eq.archetype) if eq.archetype else None
        return {}


@dataclass
class Battalion:
    name: str
    need: Dict[str, float] = field(default_factory=dict)  # equipment archetype -> qty
    training_time: Optional[float] = None
    manpower: Optional[float] = None


@dataclass
class Template:
    name: str
    # battalion name -> count (regiments and support merged; support still counts
    # its equipment need the same way for production purposes)
    battalions: Dict[str, int] = field(default_factory=dict)


@dataclass
class GameData:
    equipment: Dict[str, Equipment]
    battalions: Dict[str, Battalion]
    templates: Dict[str, Template]

    def cost_of(self, equip: str) -> float:
        eq = self.equipment.get(equip)
        return eq.resolved_cost(self.equipment) if eq else 0.0

    def resources_of(self, equip: str) -> Dict[str, float]:
        eq = self.equipment.get(equip)
        return eq.resolved_resources(self.equipment) if eq else {}


# --------------------------------------------------------------------------- #
# File resolution (base game + mods, later roots win by relative path)
# --------------------------------------------------------------------------- #
def _resolve_files(roots: List[Path], subdir: str, pattern: str = "*.txt") -> List[Path]:
    """Return the effective file list for `subdir`, with later roots overriding
    earlier ones by relative filename."""
    by_rel: Dict[str, Path] = {}
    for root in roots:
        base = root / subdir
        if not base.exists():
            continue
        for p in sorted(base.rglob(pattern)):
            rel = p.relative_to(base).as_posix()
            by_rel[rel] = p
    return list(by_rel.values())


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #
def _load_equipment(roots: List[Path]) -> Dict[str, Equipment]:
    out: Dict[str, Equipment] = {}
    for path in _resolve_files(roots, "common/units/equipment"):
        try:
            root = pdxparse.parse_file(path)
        except Exception:
            continue
        equipments = root.get_block("equipments")
        if equipments is None:
            continue
        for name, val in equipments.pairs():
            if not isinstance(val, Block):
                continue
            resources = {}
            res_block = val.get_block("resources")
            if res_block is not None:
                for rk, rv in res_block.pairs():
                    if isinstance(rv, str):
                        try:
                            resources[rk] = float(rv)
                        except ValueError:
                            pass
            out[name] = Equipment(
                name=name,
                is_archetype=(val.get_str("is_archetype") == "yes"),
                archetype=val.get_str("archetype"),
                build_cost_ic=val.get_float("build_cost_ic"),
                resources=resources,
            )
    return out


def _load_battalions(roots: List[Path]) -> Dict[str, Battalion]:
    out: Dict[str, Battalion] = {}
    for path in _resolve_files(roots, "common/units"):
        # skip the equipment/ subtree and non-subunit files gracefully
        try:
            root = pdxparse.parse_file(path)
        except Exception:
            continue
        sub_units = root.get_block("sub_units")
        if sub_units is None:
            continue
        for name, val in sub_units.pairs():
            if not isinstance(val, Block):
                continue
            need: Dict[str, float] = {}
            need_block = val.get_block("need")
            if need_block is not None:
                for ek, ev in need_block.pairs():
                    if isinstance(ev, str):
                        try:
                            need[ek] = float(ev)
                        except ValueError:
                            pass
            out[name] = Battalion(
                name=name,
                need=need,
                training_time=val.get_float("training_time"),
                manpower=val.get_float("manpower"),
            )
    return out


def _template_from_block(blk: Block) -> Optional[Template]:
    name = blk.get_str("name")
    counts: Dict[str, int] = {}
    for section in ("regiments", "support"):
        sec = blk.get_block(section)
        if sec is None:
            continue
        for bn, _ in sec.pairs():
            counts[bn] = counts.get(bn, 0) + 1
    if not counts:
        return None
    return Template(name=name or "(unnamed)", battalions=counts)


def load_templates_from_file(path: Path) -> Dict[str, Template]:
    """Parse every `division_template = { ... }` in a history/units-style file."""
    out: Dict[str, Template] = {}
    try:
        root = pdxparse.parse_file(path)
    except Exception:
        return out
    for val in root.get_all("division_template"):
        if isinstance(val, Block):
            tmpl = _template_from_block(val)
            if tmpl:
                out[tmpl.name] = tmpl
    return out


def load(
    game_root: str | Path,
    mods: Optional[List[str | Path]] = None,
    template_files: Optional[List[str | Path]] = None,
) -> GameData:
    """Load equipment + battalions from base game and mods (load order = list
    order, later wins). Optionally also load division templates from files."""
    roots = [Path(game_root)] + [Path(m) for m in (mods or [])]
    equipment = _load_equipment(roots)
    battalions = _load_battalions(roots)
    templates: Dict[str, Template] = {}
    for tf in template_files or []:
        templates.update(load_templates_from_file(Path(tf)))
    return GameData(equipment=equipment, battalions=battalions, templates=templates)
