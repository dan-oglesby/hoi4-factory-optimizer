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
- A localization/tooltip note or a purely-cosmetic decision reminding you to run
  the optimizer after changing your training queue.
- Optional GUI tweaks to the production screen *if* a non-intrusive hook exists.

Anything requiring "read the queue → compute → assign factories" stays in the
external tool by necessity.

## Enabling it
Run [`../scripts/deploy-mod.ps1`](../scripts/deploy-mod.ps1) (or `deploy-mod.sh`)
to drop a pointer descriptor into your Paradox mod folder, then pick
"Factory Optimizer Companion" in the HOI4 launcher's mod list.
