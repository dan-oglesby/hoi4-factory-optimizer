"""Command-line interface for hoi4opt.

Examples
--------
Ad-hoc composition (no template file needed), 40 factories:
    python -m hoi4opt --game-root "C:/.../Hearts of Iron IV" \
        --battalions "infantry:6,artillery:1,anti_tank:1" --factories 40

From a country's templates, training 24 of a named template:
    python -m hoi4opt --game-root "..." \
        --templates "history/units/GER_1936.txt" \
        --order "7 Infantry:24" --factories 60 \
        --resources "steel=200,tungsten=30"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from . import gamedata, needs, optimize

DEFAULT_GAME_ROOT = r"C:\Program Files (x86)\Steam\steamapps\common\Hearts of Iron IV"


def _parse_pairs(s: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for chunk in s.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        k, _, v = chunk.partition("=")
        if not v:
            k, _, v = chunk.rpartition(":")
        out[k.strip()] = float(v.strip())
    return out


def _parse_counts(s: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for chunk in s.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, cnt = chunk.rpartition(":")
        out[name.strip()] = int(cnt.strip())
    return out


def _parse_order(values: List[str]) -> List[Tuple[str, int]]:
    order: List[Tuple[str, int]] = []
    for v in values:
        name, _, cnt = v.rpartition(":")
        order.append((name.strip(), int(cnt.strip())))
    return order


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hoi4opt",
        description="Balanced HOI4 military-factory allocation for the divisions you want to train.",
    )
    p.add_argument("--game-root", default=DEFAULT_GAME_ROOT, help="HOI4 install directory.")
    p.add_argument("--mod", action="append", default=[], metavar="DIR",
                   help="Mod root directory (repeatable; later = higher load-order priority).")
    p.add_argument("--templates", action="append", default=[], metavar="FILE",
                   help="File containing division_template blocks (repeatable).")
    p.add_argument("--order", action="append", default=[], metavar="TEMPLATE:COUNT",
                   help="Train COUNT of a named template (repeatable).")
    p.add_argument("--battalions", metavar="name:count,...",
                   help="Ad-hoc composition of ONE division by battalion counts.")
    p.add_argument("--divisions", type=int, default=1,
                   help="How many of the --battalions division to build (default 1).")
    p.add_argument("--factories", type=int, required=True, help="Military factories available.")
    p.add_argument("--factory-output", type=float, default=4.5,
                   help="IC/day per factory at full efficiency (default 4.5).")
    p.add_argument("--efficiency", type=float, default=1.0,
                   help="Assumed production efficiency 0..1 (default 1.0).")
    p.add_argument("--max-per-line", type=int, default=15,
                   help="Max factories per production line (default 15).")
    p.add_argument("--resources", metavar="steel=..,tungsten=..",
                   help="Optional per-day resource budget; lines busting it get trimmed.")
    p.add_argument("--list-templates", action="store_true",
                   help="List templates found in --templates files and exit.")
    return p


def _fmt_days(d: float) -> str:
    return "inf" if d == float("inf") else f"{d:.1f}"


def run(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    gd = gamedata.load(args.game_root, mods=args.mod, template_files=args.templates)

    if args.list_templates:
        if not gd.templates:
            print("No templates found. Pass --templates <file>.")
            return 1
        for name, t in sorted(gd.templates.items()):
            comp = ", ".join(f"{k}x{v}" for k, v in t.battalions.items())
            print(f"  {name}: {comp}")
        return 0

    # Build demand
    if args.battalions:
        batts = _parse_counts(args.battalions)
        batts = {k: v * args.divisions for k, v in batts.items()}
        demand = needs.demand_for_battalions(gd, batts)
        subject = f"{args.divisions}x division [{args.battalions}]"
    elif args.order:
        order = _parse_order(args.order)
        demand = needs.demand_for_order(gd, order)
        subject = ", ".join(f"{c}x {n}" for n, c in order)
    else:
        print("error: pass --battalions or --order (or --list-templates).", file=sys.stderr)
        return 2

    if demand.unknown_battalions:
        print("WARNING: unresolved names (check spelling / load the right mod/template files):")
        for u in sorted(set(demand.unknown_battalions)):
            print(f"  - {u}")
        print()

    resource_budget = _parse_pairs(args.resources) if args.resources else None
    plan = optimize.allocate(
        demand,
        factories=args.factories,
        factory_output=args.factory_output,
        efficiency=args.efficiency,
        max_per_line=args.max_per_line,
        resource_budget=resource_budget,
    )

    # ---- report ----
    print(f"Target: {subject}")
    print(f"Equipment types loaded: {len(gd.equipment)}   battalions: {len(gd.battalions)}")
    print(f"Total production cost: {demand.total_ic:,.0f} IC "
          f"across {len([d for d in demand.by_equipment.values() if d.total_ic>0])} equipment types")
    print(f"Factories: {plan.factories_used}/{plan.factories_available} assigned "
          f"@ {args.factory_output}x{args.efficiency:g} = {args.factory_output*args.efficiency:.2f} IC/day each\n")

    hdr = f"{'equipment':<28}{'fact':>5}{'need':>9}{'IC':>10}{'units/d':>9}{'days':>7}"
    print(hdr)
    print("-" * len(hdr))
    for ln in plan.lines:
        d = demand.by_equipment[ln.equipment]
        print(f"{ln.equipment:<28}{ln.factories:>5}{d.units:>9,.0f}"
              f"{ln.total_ic:>10,.0f}{ln.units_per_day:>9.1f}{_fmt_days(ln.days_to_complete):>7}")

    print()
    print(f"Estimated completion: {_fmt_days(plan.completion_days)} days "
          f"(bottleneck: {plan.bottleneck})")
    if plan.resource_totals:
        res = ", ".join(f"{r} {v:.1f}/d" for r, v in sorted(plan.resource_totals.items()))
        print(f"Resource draw at this pace: {res}")
    for w in plan.resource_warnings:
        print(f"  ! {w}")
    for n in plan.notes:
        print(f"  note: {n}")
    return 0


def main() -> None:  # console-script entrypoint
    raise SystemExit(run())


if __name__ == "__main__":
    main()
