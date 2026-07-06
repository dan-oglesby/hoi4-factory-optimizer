# Design & feasibility analysis

## What we want

Given the set of division templates the player wants to train, and the current
game state (equipment stockpiles, active production lines, factory count,
resources), compute a **factory allocation across equipment types** that
maximizes how quickly those divisions can actually be completed — balancing so
no single equipment type becomes the bottleneck, and respecting resource limits.

Must be **flexible about what equipment/resources exist** — read the real
definitions from the active game + mods, never hard-code an equipment list.

## Why a pure in-game mod can't do the "automatic" part

HOI4 modding is declarative (PDX script, GFX/GUI, localization, defines). Relevant
limitations:

1. **No factory-assignment effect for the player.** Assigning military factories
   to a production line is a UI action. There is no scripted `effect` or
   `on_action` that lets a mod add/remove factories from the human player's
   production lines algorithmically.
2. **No "division queued" trigger.** There is no `on_action` that fires when the
   player adds a template to the training queue, and no scripted way to read a
   template's per-equipment shortfall as live data to compute against.
3. **AI production ≠ player production.** `common/ai_strategy`,
   `ai_strategy_plans`, `role_ratios`, and the production defines steer how
   **AI countries** build. They do not touch the human player's manual production.

Net: the seamless *automatic* "queue a division → factories auto-rebalance"
experience is **out of scope for a Workshop mod**. Anyone claiming otherwise is
either using an external tool or memory-editing.

> **2026-07 update — big refinement:** a *player-clicked* in-game rebalance
> button **is feasible**. Script can read per-archetype army deficits and
> engine-computed truck/train needs, and `add_equipment_production` can create
> finite self-terminating lines from free factories. See
> [`INGAME_BUTTON.md`](INGAME_BUTTON.md) for the verified design and its limits
> (free factories only; no removal/edit of existing lines; no reading of line
> state).

## Feasible approaches

### A. External companion tool (recommended) — delivers the real feature
A program (Python) that:
- **Discovers game + active mod data**: parses `common/units/equipment/*`,
  division templates, and resource/production `defines` from the base game and
  every active mod (respecting load order) to build a live map of *what equipment
  exists*, its build cost (IC), resource cost, and output — no hard-coded lists.
- **Reads current state** from either a **save game** parse (stockpiles, lines,
  factory count, what's training) or manual input.
- **Optimizes**: allocates factories across the needed equipment types to
  maximize divisions completed per unit time, balancing shortfalls and honoring
  resource constraints (a small LP/greedy allocation).
- **Outputs a plan**: "Assign N factories to X, M to Y…" plus expected time to
  field the divisions and the binding resource constraint.
- Optional later: re-parse periodically / on save to keep the plan current.

Tradeoff: **advisory** — you still click to set factories in-game. But it is the
only approach that actually does the requested analysis, and it is genuinely
mod-agnostic.

### B. In-game info/QoL mod (limited)
A small mod that surfaces helpful production info or presets in-game. Cannot do
the optimization or the auto-assignment; mostly cosmetic relative to the goal.

### C. Hybrid
External optimizer (A) as the engine, plus a thin in-game mod (B) for any
in-game surfacing that's actually possible. Most work, incremental value over A.

## Open questions for the user
- Confirm approach (A / B / C).
- Save-parsing vs. manual state entry for the "current state" input.
- Which HOI4 version + which mod set to target first for the data parser.

## References to gather (parser targets)
- `.../Hearts of Iron IV/common/units/equipment/` (equipment archetypes + costs)
- `.../common/units/` (division template + battalion equipment needs)
- `.../common/defines/` (production/resource defines)
- Active mod `descriptor.mod` files + `mod/` load order
- Save game format (Clausewitz text / ironman binary — text is parseable)
