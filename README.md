# HOI4 Factory Optimizer

A tool for **Hearts of Iron IV** that looks at the divisions you want to train,
reads their **actual** equipment requirements, and works out how to allocate your
military factories so you can field those divisions as fast as possible — balanced
so no single equipment type becomes the bottleneck, with resource-draw awareness.

It is **mod-agnostic**: it reads the real equipment / template / battalion
definitions from your active game + mods, so nothing about the equipment or
resource list is hard-coded. If a mod adds new units or equipment, it just works.

## Why "hybrid" (read this first)

HOI4 mods are declarative data/script. Assigning military factories to production
lines is a manual player action, and the game exposes **no modding hook** that
fires when you queue a division, reads its equipment shortfall, and reassigns your
factories. The AI production system only steers **AI countries**. So the seamless
"queue a division → factories auto-rebalance" experience **cannot** be a pure
Workshop mod. This project is therefore a **hybrid**:

- **[`tool/`](tool) — the optimizer engine (this does the real work).** A
  standard-library Python program that reads your game/mod data and prints the
  optimal balanced factory allocation, which you apply in-game. Advisory, but it
  genuinely does the analysis you want.
- **[`mod/`](mod) — a thin in-game companion mod.** Reserved for the small amount
  of in-game surfacing that's actually feasible (tooltips/reminders/GUI tweaks).
  Cannot itself optimize or assign factories.

Full analysis: [`docs/DESIGN.md`](docs/DESIGN.md).

## Quick start (the tool)

```bash
cd tool
python -m hoi4opt --battalions "infantry:6,artillery:1,anti_tank:1" \
                  --divisions 24 --factories 40
```

Example output (real 1.19 data, 308 equipment types loaded):

```
Target: 24x division [infantry:6,artillery:1,anti_tank:1]
Total production cost: 12,487 IC across 4 equipment types
Factories: 40/40 assigned @ 4.5x1 = 4.50 IC/day each

equipment                    fact     need        IC  units/d   days
--------------------------------------------------------------------
infantry_equipment             15   14,640     6,295    157.0   93.3
support_equipment              11      720     2,880     12.4   58.2
anti_tank_equipment            10      576     2,304     11.2   51.2
artillery_equipment             4      288     1,008      5.1   56.0

Estimated completion: 93.3 days (bottleneck: infantry_equipment)
Resource draw at this pace: aluminium 12.4/d, steel 371.5/d, tungsten 27.6/d
```

See [`tool/README.md`](tool/README.md) for all flags (templates, mods, resource
budgets, efficiency, etc.).

## Install the in-game mod (optional)

```powershell
pwsh -File scripts/deploy-mod.ps1     # or: bash scripts/deploy-mod.sh
```

Then enable **Factory Optimizer Companion** in the HOI4 launcher. It currently
makes no gameplay changes (safe no-op) — the value is the tool.

## Repo layout

```
hoi4-factory-optimizer/
├── tool/            # the optimizer engine (Python, stdlib only) + tests
│   └── hoi4opt/     # pdxparse, gamedata, needs, optimize, cli
├── mod/             # thin in-game HOI4 companion mod (descriptor.mod)
├── scripts/         # deploy-mod.ps1 / deploy-mod.sh
└── docs/            # design & feasibility notes
```

## Status
v0.1 — working end to end against real game data (parser, demand, balanced
allocation, resource awareness, tests).

**Next up:** an in-game **"Optimize" button** on the production screen — verified
feasible via scripted GUI + `add_equipment_production` finite lines, including
engine-computed truck/train (logistics) needs via `get_supply_vehicles`. Design
and evidence: [`docs/INGAME_BUTTON.md`](docs/INGAME_BUTTON.md). Also planned:
save-game parsing to auto-detect factories/stockpiles/queue for the CLI tool.

## License
MIT — see [`LICENSE`](LICENSE).
