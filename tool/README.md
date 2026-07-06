# hoi4opt — the optimizer engine

Reads your **actual** HOI4 game + mod data (equipment archetypes, battalion
equipment `need`s, division templates), computes the equipment demand for the
divisions you want to train, and prints a **balanced military-factory allocation**
that minimizes the time to field them. Standard-library Python only — no installs.

## Quick start

```bash
cd tool

# Ad-hoc: 24 divisions of a hand-specified composition, 40 factories
python -m hoi4opt \
  --game-root "C:/Program Files (x86)/Steam/steamapps/common/Hearts of Iron IV" \
  --battalions "infantry:6,artillery:1,anti_tank:1,engineer:1" \
  --divisions 24 --factories 40

# From a country's real templates
python -m hoi4opt --game-root "..." \
  --templates "history/units/GER_1936.txt" --list-templates --factories 1
python -m hoi4opt --game-root "..." \
  --templates "history/units/GER_1936.txt" \
  --order "7 Infantry:24" --factories 60 --resources "steel=200,tungsten=30"

# With mods (load order = argument order; later wins)
python -m hoi4opt --game-root "..." \
  --mod "C:/.../mod/some_overhaul" --mod "C:/.../mod/my_tweaks" \
  --battalions "infantry:9" --factories 30
```

The default `--game-root` already points at the Steam install path, so you can
usually omit it.

## What it prints
- Total production cost (IC) of the order, split by equipment type.
- Factories assigned per equipment line (balanced so lines finish together).
- Units/day and days-to-complete per line, plus the **bottleneck**.
- Resource draw per day, and warnings if a `--resources` budget is exceeded.

## How the allocation works
Each military factory adds the same IC/day, so equipment type *i* with total cost
`C_i` and `f_i` factories finishes in time ∝ `C_i / f_i`. You are gated by the
slowest line, so minimizing the max completion time means allocating factories in
**proportion to IC demand**. The tool does that, then applies:
- integer rounding via largest-remainder,
- the per-line factory cap (default 15), redistributing the overflow,
- optional resource-budget trimming (moves factories off a scarce-resource line
  to lines that don't need it; if every line shares the shortage it keeps them
  working and just warns — you're genuinely supply-limited).

See [`../docs/DESIGN.md`](../docs/DESIGN.md) for modeling notes and limitations.

## Flags
| flag | meaning |
|------|---------|
| `--game-root DIR` | HOI4 install dir (has a sensible default). |
| `--mod DIR` | Add a mod root; repeat for load order (later wins). |
| `--templates FILE` | Load `division_template` blocks from a file; repeat. |
| `--order TEMPLATE:COUNT` | Train COUNT of a named template; repeat. |
| `--battalions name:count,...` | Ad-hoc single-division composition. |
| `--divisions N` | Build N of the `--battalions` division (default 1). |
| `--factories N` | Military factories available (**required**). |
| `--factory-output F` | IC/day per factory at full efficiency (default 4.5). |
| `--efficiency X` | Assumed efficiency 0..1 (default 1.0). |
| `--max-per-line N` | Factory cap per line (default 15). |
| `--resources k=v,...` | Per-day resource budget to respect. |
| `--list-templates` | List loaded templates and exit. |

## Tests
```bash
cd tool && python -m pytest -q
```

## genmod — generate the in-game mod script

`hoi4opt.genmod` reads the same game+mod data and **code-generates** the in-game
companion mod's optimizer effect (`../mod/common/scripted_effects/...`) plus its
localization — every equipment archetype, IC cost, and variant→tech unlock baked
in from your actual files. This is how the in-game button stays mod-agnostic:
change your mod list, regenerate, done.

```bash
cd tool
python -m hoi4opt.genmod                       # base game, default paths
python -m hoi4opt.genmod --mod "C:/.../mod/x"  # with mods (repeatable)
```

Flags: `--out DIR` (default: this repo's `mod/`), `--max-per-line N` (default 15),
`--cooldown-days N` (default 7), `--start-efficiency N` (off by default — a free
efficiency head start would be a cheat).

Design and verified engine facts: [`../docs/INGAME_BUTTON.md`](../docs/INGAME_BUTTON.md).

## Roadmap
- Parse a **save game** to auto-detect factories, stockpiles, in-progress lines,
  resources, and which templates are actually queued (currently supplied via
  flags). See DESIGN's open questions.
- Model production efficiency ramp-up and variant (not just archetype) costs.
- `replace_path` / partial-merge handling for mod overlays.
- genmod: special-project unlock detection (helicopters etc.), smarter leftover
  redistribution when the largest line hits the per-line cap.
