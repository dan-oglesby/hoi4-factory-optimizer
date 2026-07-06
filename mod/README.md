# In-game companion mod

This is the **thin in-game half** of the hybrid. HOI4 mods are declarative and
**cannot** reassign the human player's factories or react to the training queue
(see [`../docs/DESIGN.md`](../docs/DESIGN.md)), so the real optimization lives in
the external tool under [`../tool`](../tool). This mod folder exists to carry any
in-game surfacing that *is* possible without breaking the honesty of the project.

## Current contents
- `descriptor.mod` — makes this a valid, selectable mod.
- **The "Optimize" button** (`interface/fo_optimizer.gui` +
  `common/scripted_guis/fo_optimizer_scripted_gui.txt`): a scripted GUI anchored
  to the production tab (`parent_window_token = production_tab`, an officially
  documented token). Click → runs `fo_run_optimizer`.
- **The optimizer effect** (`common/scripted_effects/fo_optimizer_scripted_effects.txt`):
  **GENERATED** by `python -m hoi4opt.genmod` — computes per-archetype equipment
  deficits and engine-computed truck/train needs, then creates finite
  (`amount = deficit`) production lines from free military factories. Finite
  lines complete and release their factories when the need is filled — that's
  the "switch off when logistics are covered" behavior. Regenerate after
  changing your mod list.
- **Decisions** (`common/decisions/fo_optimizer_decisions.txt`): an
  "Optimize Production Now" fallback (same effect, always reachable), plus
  debug decisions implementing the empirical tests from
  [`../docs/INGAME_BUTTON.md`](../docs/INGAME_BUTTON.md) §7 (toggle them with
  "Toggle Debug Tools").

What remains impossible in-game: removing/editing existing production lines,
reading per-line factory counts, and anything fully automatic (no
"division queued" hook exists). The button only ever uses FREE factories.

## Enabling it
Run [`../scripts/deploy-mod.ps1`](../scripts/deploy-mod.ps1) (or `deploy-mod.sh`)
to drop a pointer descriptor into your Paradox mod folder, then pick
"Factory Optimizer Companion" in the HOI4 launcher's mod list.
