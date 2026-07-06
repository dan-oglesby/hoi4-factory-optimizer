"""Generate the in-game companion mod's optimizer script from actual game+mod data.

This is what keeps the in-game button mod-agnostic: PDX script cannot enumerate
equipment at runtime, so we enumerate it HERE, at generation time, from the same
`gamedata` loader the CLI advisor uses — and emit an unrolled scripted effect
(`fo_run_optimizer`) that:

  1. reads per-archetype deficits via engine dynamic variables
     (num_target_equipment_in_armies@X - num_equipment_in_armies@X - num_equipment@X),
  2. reads engine-computed truck/train logistics need via get_supply_vehicles_temp
     (trucks = the supply_truck archetype; trains = the type=train archetype),
  3. weights deficits by the best *researched* variant's build_cost_ic
     (has_tech chains generated from common/technologies enable_equipments),
  4. allocates free military factories proportionally to IC demand, and
  5. creates finite production lines via add_equipment_production with
     amount = <deficit variable> (self-terminating: line completes and releases
     its factories when the deficit is filled) and a literal
     requested_factories ladder (the effect does not accept variables there).

Designer equipment (module_slots: tank chassis, plane airframes, ship hulls)
cannot be produced by script without a player-designed variant, so those
archetypes are excluded and reported.

Regenerate whenever the mod list changes:
    python -m hoi4opt.genmod --game-root "..." [--mod DIR ...]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from . import gamedata, pdxparse
from .gamedata import GameData

GENERATED_HEADER = (
    "# GENERATED FILE - do not hand-edit.\n"
    "# Produced by `python -m hoi4opt.genmod` from the active game+mod data.\n"
    "# Regenerate after changing your mod list so the equipment set matches.\n"
)


@dataclass
class Variant:
    token: str
    cost: float
    techs: Optional[List[str]]  # None => active from start (no research gate)


@dataclass
class ArchPlan:
    archetype: str
    variants: List[Variant]  # best (newest) first
    is_truck: bool = False
    is_train: bool = False


@dataclass
class GenModel:
    plans: List[ArchPlan]
    excluded: List[Tuple[str, str]] = field(default_factory=list)  # (token, reason)


# --------------------------------------------------------------------------- #
# Model building
# --------------------------------------------------------------------------- #
def build_model(gd: GameData) -> GenModel:
    needed = set()
    for b in gd.battalions.values():
        needed.update(b.need.keys())
    trucks = {e.name for e in gd.equipment.values() if e.is_archetype and e.supply_truck}
    trains = {e.name for e in gd.equipment.values() if e.is_archetype and "train" in e.types}
    needed |= trucks | trains

    plans: List[ArchPlan] = []
    excluded: List[Tuple[str, str]] = []
    for arch in sorted(needed):
        eq = gd.equipment.get(arch)
        if eq is None:
            excluded.append((arch, "not defined in common/units/equipment"))
            continue
        if eq.has_module_slots:
            excluded.append((arch, "designer equipment (module-based); assign manually"))
            continue

        variants = [
            v
            for v in gd.equipment.values()
            if v.archetype == arch and not v.has_module_slots
        ]
        candidates = variants if variants else ([eq] if eq.is_buildable != "no" else [])

        avail: List[Variant] = []
        for v in candidates:
            if v.is_buildable == "no":
                continue
            if v.active == "yes":
                techs: Optional[List[str]] = None
            else:
                found = gd.unlock_techs.get(v.name) or []
                if not found:
                    continue  # no way to determine unlock -> unsafe to produce
                techs = list(found)
            avail.append(Variant(v.name, v.resolved_cost(gd.equipment), techs))
        if not avail:
            excluded.append((arch, "no buildable variant with a known unlock"))
            continue

        # best-first: newest year, then highest priority; stable tiebreak on
        # token descending so infantry_equipment_3 beats _2 when metadata ties.
        avail.sort(key=lambda v: v.token, reverse=True)
        avail.sort(
            key=lambda v: (
                -(gd.equipment[v.token].year or 0),
                -(gd.equipment[v.token].priority or 0),
            )
        )
        plans.append(ArchPlan(arch, avail, is_truck=arch in trucks, is_train=arch in trains))
    return GenModel(plans=plans, excluded=excluded)


# --------------------------------------------------------------------------- #
# Script emission
# --------------------------------------------------------------------------- #
class _W:
    """Tiny indented-line writer."""

    def __init__(self) -> None:
        self.lines: List[str] = []

    def w(self, depth: int, text: str = "") -> None:
        self.lines.append(("\t" * depth + text) if text else "")

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def _tech_limit(techs: List[str]) -> str:
    if len(techs) == 1:
        return f"has_tech = {techs[0]}"
    return "OR = { " + " ".join(f"has_tech = {t}" for t in techs) + " }"


def _emit_variant_chain(
    out: _W, depth: int, plan: ArchPlan, body: Callable[[Variant, int], None]
) -> None:
    """if/else_if/else over the plan's variants, best-first. An always-active
    variant terminates the chain (later variants are strictly worse)."""
    first = True
    for v in plan.variants:
        if v.techs is None:
            if first:
                body(v, depth)  # unconditional and first: no wrapper needed
            else:
                out.w(depth, "else = {")
                body(v, depth + 1)
                out.w(depth, "}")
            return
        kw = "if" if first else "else_if"
        out.w(depth, f"{kw} = {{ limit = {{ {_tech_limit(v.techs)} }}")
        body(v, depth + 1)
        out.w(depth, "}")
        first = False
    # no always-active fallback: chain simply ends (nothing produced / cost 0)


def _emit_ladder(
    out: _W,
    depth: int,
    share_var: str,
    max_per_line: int,
    add_block: Callable[[int], str],
) -> None:
    """requested_factories only accepts literal integers (every vanilla usage is
    literal; not documented to accept variables), so branch on the share."""
    first = True
    for rf in range(max_per_line, 0, -1):
        kw = "if" if first else "else_if"
        out.w(depth, f"{kw} = {{ limit = {{ check_variable = {{ {share_var} > {rf - 1}.5 }} }}")
        out.w(depth + 1, add_block(rf))
        out.w(depth, "}")
        first = False


def emit_scripted_effect(
    model: GenModel,
    max_per_line: int = 15,
    cooldown_days: int = 7,
    start_efficiency: Optional[int] = None,
) -> str:
    out = _W()
    out.w(0, GENERATED_HEADER.rstrip())
    out.w(0)
    out.w(0, "fo_run_optimizer = {")
    d = 1
    out.w(d, "# -- inputs ------------------------------------------------------")
    out.w(d, "set_temp_variable = { fo_free = num_of_available_military_factories }")
    out.w(d, "set_variable = { fo_last_free = fo_free }")
    out.w(d, "set_temp_variable = { fo_total_ic = 0 }")
    out.w(d)
    out.w(d, "# engine-computed logistics need (railways, hub motorization, supply draw)")
    out.w(d, "get_supply_vehicles_temp = { var = fo_truck_have type = truck }")
    out.w(d, "get_supply_vehicles_temp = { var = fo_truck_need type = truck need = yes }")
    out.w(d, "set_temp_variable = { fo_truck_def = { value = fo_truck_need subtract = fo_truck_have max = 0 } }")
    out.w(d, "get_supply_vehicles_temp = { var = fo_train_have type = train }")
    out.w(d, "get_supply_vehicles_temp = { var = fo_train_need type = train need = yes }")
    out.w(d, "set_temp_variable = { fo_train_def = { value = fo_train_need subtract = fo_train_have max = 0 } }")
    out.w(d)

    # ---- pass 1: deficits, costs, IC weights --------------------------------
    for plan in model.plans:
        x = plan.archetype
        out.w(d, f"# ---- {x} ----")
        out.w(d, f"set_temp_variable = {{ fo_def_{x} = num_target_equipment_in_armies@{x} }}")
        out.w(d, f"subtract_from_temp_variable = {{ fo_def_{x} = num_equipment_in_armies@{x} }}")
        out.w(d, f"subtract_from_temp_variable = {{ fo_def_{x} = num_equipment@{x} }}")
        out.w(d, f"set_temp_variable = {{ fo_def_{x} = {{ value = fo_def_{x} max = 0 }} }}")
        if plan.is_truck:
            out.w(d, "# trucks: supply-system need can exceed the army-side need; take the max")
            out.w(d, f"set_temp_variable = {{ fo_def_{x} = {{ value = fo_def_{x} max = fo_truck_def }} }}")
        if plan.is_train:
            out.w(d, "# trains: demand is purely supply-side")
            out.w(d, f"set_temp_variable = {{ fo_def_{x} = {{ value = fo_def_{x} max = fo_train_def }} }}")
        out.w(d, f"set_temp_variable = {{ fo_def_{x} = {{ value = fo_def_{x} round = yes }} }}")
        out.w(d, f"set_temp_variable = {{ fo_cost_{x} = 0 }}")

        def cost_body(v: Variant, depth: int, _x: str = x) -> None:
            out.w(depth, f"set_temp_variable = {{ fo_cost_{_x} = {v.cost:g} }}")

        _emit_variant_chain(out, d, plan, cost_body)
        out.w(d, f"set_temp_variable = {{ fo_ic_{x} = {{ value = fo_def_{x} multiply = fo_cost_{x} }} }}")
        out.w(d, f"add_to_temp_variable = {{ fo_total_ic = fo_ic_{x} }}")
        out.w(d)

    # ---- reset persistent report vars ---------------------------------------
    out.w(d, "# report variables (shown in the button tooltip)")
    for plan in model.plans:
        out.w(d, f"set_variable = {{ fo_plan_{plan.archetype} = 0 }}")
        out.w(d, f"set_variable = {{ fo_amount_{plan.archetype} = 0 }}")
    out.w(d)

    # ---- allocation + orders -------------------------------------------------
    out.w(d, "if = {")
    out.w(d + 1, "limit = {")
    out.w(d + 2, "check_variable = { fo_total_ic > 0.5 }")
    out.w(d + 2, "check_variable = { fo_free > 0.5 }")
    out.w(d + 1, "}")
    dd = d + 1
    out.w(dd, "# proportional-to-IC shares (floor), per-line cap, remainder to the")
    out.w(dd, "# largest-demand line - same policy as the CLI advisor")
    out.w(dd, "set_temp_variable = { fo_used = 0 }")
    out.w(dd, "set_temp_variable = { fo_max_ic = 0 }")
    out.w(dd, "set_temp_variable = { fo_max_idx = -1 }")
    for k, plan in enumerate(model.plans):
        x = plan.archetype
        out.w(dd, f"set_temp_variable = {{ fo_share_{x} = {{ value = fo_ic_{x} multiply = fo_free divide = fo_total_ic subtract = 0.5 round = yes max = 0 min = {max_per_line} }} }}")
        out.w(dd, f"add_to_temp_variable = {{ fo_used = fo_share_{x} }}")
        out.w(dd, f"if = {{ limit = {{ check_variable = {{ fo_ic_{x} > fo_max_ic }} }}")
        out.w(dd + 1, f"set_temp_variable = {{ fo_max_ic = fo_ic_{x} }}")
        out.w(dd + 1, f"set_temp_variable = {{ fo_max_idx = {k} }}")
        out.w(dd, "}")
    out.w(dd, "set_temp_variable = { fo_left = { value = fo_free subtract = fo_used max = 0 } }")
    for k, plan in enumerate(model.plans):
        x = plan.archetype
        out.w(dd, f"if = {{ limit = {{ check_variable = {{ fo_max_idx = {k} }} }}")
        out.w(dd + 1, f"set_temp_variable = {{ fo_share_{x} = {{ value = fo_share_{x} add = fo_left min = {max_per_line} }} }}")
        out.w(dd, "}")
    out.w(dd)
    out.w(dd, "# create finite lines: amount = deficit, so each line completes and")
    out.w(dd, "# releases its factories once the need is filled")
    eff = f" efficiency = {start_efficiency}" if start_efficiency is not None else ""
    for plan in model.plans:
        x = plan.archetype
        out.w(dd, f"if = {{ limit = {{ check_variable = {{ fo_share_{x} > 0.5 }} check_variable = {{ fo_def_{x} > 0.5 }} }}")
        out.w(dd + 1, f"set_variable = {{ fo_plan_{x} = fo_share_{x} }}")
        out.w(dd + 1, f"set_variable = {{ fo_amount_{x} = fo_def_{x} }}")

        def order_body(v: Variant, depth: int, _x: str = x) -> None:
            _emit_ladder(
                out,
                depth,
                f"fo_share_{_x}",
                max_per_line,
                lambda rf, _v=v: (
                    f"add_equipment_production = {{ equipment = {{ type = {_v.token} }} "
                    f"requested_factories = {rf} amount = fo_amount_{_x}{eff} }}"
                ),
            )

        _emit_variant_chain(out, dd + 1, plan, order_body)
        out.w(dd, "}")
    out.w(dd)
    out.w(dd, f"set_country_flag = {{ flag = fo_cooldown days = {cooldown_days} value = 1 }}")
    out.w(dd, "set_variable = { fo_has_plan = 1 }")
    out.w(d, "}")
    out.w(d, "else = {")
    out.w(d + 1, "set_variable = { fo_has_plan = 0 }")
    out.w(d, "}")
    out.w(0, "}")
    return out.text()


# --------------------------------------------------------------------------- #
# Localization emission
# --------------------------------------------------------------------------- #
def emit_generated_loc(model: GenModel) -> str:
    plan_lines = []
    for plan in model.plans:
        x = plan.archetype
        plan_lines.append(f"[?fo_plan_{x}|0] fac -> [?fo_amount_{x}|0]x ${x}$")
    plan_str = "\\n".join(plan_lines)
    excluded_str = ", ".join(t for t, _ in model.excluded) or "none"
    return (
        "l_english:\n"
        f' FO_PLAN_LINES:0 "{plan_str}"\n'
        f' FO_EXCLUDED_LIST:0 "{excluded_str}"\n'
    )


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def generate(
    game_root: str | Path,
    mods: Optional[List[str | Path]] = None,
    out_dir: Optional[str | Path] = None,
    max_per_line: int = 15,
    cooldown_days: int = 7,
    start_efficiency: Optional[int] = None,
) -> GenModel:
    gd = gamedata.load(game_root, mods=mods)
    model = build_model(gd)

    out = Path(out_dir) if out_dir else Path(__file__).resolve().parents[2] / "mod"
    fx_path = out / "common" / "scripted_effects" / "fo_optimizer_scripted_effects.txt"
    loc_path = out / "localisation" / "english" / "fo_optimizer_generated_l_english.yml"
    fx_path.parent.mkdir(parents=True, exist_ok=True)
    loc_path.parent.mkdir(parents=True, exist_ok=True)

    fx_text = emit_scripted_effect(
        model,
        max_per_line=max_per_line,
        cooldown_days=cooldown_days,
        start_efficiency=start_efficiency,
    )
    fx_path.write_text(fx_text, encoding="utf-8")
    # PDX localization requires a UTF-8 BOM
    loc_path.write_text(emit_generated_loc(model), encoding="utf-8-sig")

    # sanity: the generated script must round-trip through our own parser
    parsed = pdxparse.parse(fx_text)
    if parsed.get_block("fo_run_optimizer") is None:
        raise RuntimeError("generated script failed to parse - bug in emitter")
    return model


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="hoi4opt.genmod",
        description="Generate the in-game optimizer mod script from actual game+mod data.",
    )
    p.add_argument("--game-root", default=r"C:\Program Files (x86)\Steam\steamapps\common\Hearts of Iron IV")
    p.add_argument("--mod", action="append", default=[], metavar="DIR",
                   help="Mod root directory (repeatable; later = higher priority).")
    p.add_argument("--out", default=None, metavar="DIR",
                   help="Mod output directory (default: this repo's mod/).")
    p.add_argument("--max-per-line", type=int, default=15,
                   help="Factory cap per created line / ladder top (default 15).")
    p.add_argument("--cooldown-days", type=int, default=7,
                   help="Button cooldown in days after a run (default 7).")
    p.add_argument("--start-efficiency", type=int, default=None,
                   help="Optional efficiency (0-100) for created lines. Omitted by "
                        "default: starting above base efficiency would be a cheat.")
    args = p.parse_args(argv)

    model = generate(
        args.game_root,
        mods=args.mod,
        out_dir=args.out,
        max_per_line=args.max_per_line,
        cooldown_days=args.cooldown_days,
        start_efficiency=args.start_efficiency,
    )
    print(f"Included archetypes ({len(model.plans)}):")
    for plan in model.plans:
        kind = " [trucks]" if plan.is_truck else (" [trains]" if plan.is_train else "")
        chain = " > ".join(v.token for v in plan.variants)
        print(f"  {plan.archetype}{kind}: {chain}")
    if model.excluded:
        print(f"Excluded ({len(model.excluded)}):")
        for token, reason in model.excluded:
            print(f"  {token}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
