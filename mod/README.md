# In-game companion mod

This is the **thin in-game half** of the hybrid. HOI4 mods are declarative and
**cannot** reassign the human player's factories or react to the training queue
(see [`../docs/DESIGN.md`](../docs/DESIGN.md)), so the real optimization lives in
the external tool under [`../tool`](../tool). This mod folder exists to carry any
in-game surfacing that *is* possible without breaking the honesty of the project.

## Current contents
- `descriptor.mod` — makes this a valid, selectable mod (currently no gameplay
  changes; enabling it is a no-op, safe to leave on).

## Planned, actually-feasible additions
- **An "Optimize" button on the production screen** (scripted GUI anchored to
  `production_tab`) that computes equipment + truck/train deficits in-game and
  creates finite, self-terminating production lines from free factories — see
  [`../docs/INGAME_BUTTON.md`](../docs/INGAME_BUTTON.md) for the verified design.
  The mod's script files will be **code-generated** by the external tool
  (`hoi4opt genmod`) from your active game+mods, preserving mod-agnosticism.

What remains impossible in-game: removing/editing existing production lines,
reading per-line factory counts, and anything fully automatic (no
"division queued" hook exists).

## Enabling it
Run [`../scripts/deploy-mod.ps1`](../scripts/deploy-mod.ps1) (or `deploy-mod.sh`)
to drop a pointer descriptor into your Paradox mod folder, then pick
"Factory Optimizer Companion" in the HOI4 launcher's mod list.
