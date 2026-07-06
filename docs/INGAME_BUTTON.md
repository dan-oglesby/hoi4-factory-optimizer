# The in-game "Optimize" button — verified feasibility & design

**Verdict: feasible**, and considerably stronger than the project's original
feasibility analysis assumed. A scripted-GUI button on the production screen can
read equipment deficits *and* engine-computed truck/train needs, then create
**finite, self-terminating production lines** sized to those deficits using free
military factories. "Fully filled logistics → factories come off" is achieved by
construction (finite lines complete and release their factories), not by a
remove-effect (which does not exist).

Everything below is cited to HOI4 **1.19.2's own shipped files** (the
`documentation/*.md` modding docs and actual game script), not wiki memory.

---

## 1. What script can READ (all confirmed)

| Data | Mechanism | Source |
|---|---|---|
| Stockpile per archetype | `num_equipment@<archetype>` | `documentation/dynamic_variables_documentation.md:557` |
| Equipment fielded in armies | `num_equipment_in_armies@<archetype>` (`_k` variant) | `dynamic_variables_documentation.md:560-564` |
| Equipment **required** by armies | `num_target_equipment_in_armies@<archetype>` (`_k`) | `dynamic_variables_documentation.md:687-691` |
| Free military factories | `num_of_available_military_factories` | `dynamic_variables_documentation.md:596-597` |
| **Truck/train stockpile AND engine-computed need** | `get_supply_vehicles_temp = { var = X  type = truck|train  need = yes|no }` (COUNTRY scope; also `get_supply_vehicles` for persistent vars) | `effects_documentation.md:4535-4563`; working shipped usage: `common/ribbons/00_ribbons.txt:412-427` (compares `trucks_in_stockpile` vs `trucks_needed`) |

So per-archetype deficit is computable in-game:
`deficit = max(0, target_in_armies − in_armies − stockpile)`, and logistics
deficit is `max(0, needed − stockpile)` per truck/train — **the engine does the
railway/hub/supply math for us**; no re-derivation needed.

Logistics facts that shape the heuristic (from `common/`):
- **Trucks are `motorized_equipment`** (`supply_truck = yes`,
  `common/units/equipment/motorized.txt:34`; `mechanized_equipment` is explicitly
  `supply_truck = no` and cannot substitute). Truck demand is **dual-source**:
  division `need` blocks (e.g. 35/motorized battalion, 10/logistics company)
  *plus* the supply system (60 trucks per fully-motorized hub,
  `00_defines.lua:4323`, plus supply-draw buffer).
- **Trains are `train_equipment`** (buildable variants `train_equipment_1/2/3`
  at 70/50/105 IC). **No battalion needs trains** — train demand is purely
  supply-side, so `get_supply_vehicles need = yes` is the *only* correct source.
- Train shortfalls are soft: throughput floors at `MIN_TRAIN_SUPPLY_FACTOR = 0.5`
  with 0 trains, and no penalty when need ≤ `MIN_TRAIN_REQUIREMENT = 2`
  (`00_defines.lua:4375-4376`).

## 2. What script can DO (confirmed, with constraints)

`add_equipment_production` (COUNTRY scope) is the **only** effect that touches
production lines (`effects_documentation.md:1207-1231`; exhaustive index scan
found no remove/edit/reassign effect). Facts:

- **Works from player-clicked UI on the player's own country** — vanilla runs it
  inside a Greek player decision (`common/decisions/GRE.txt:3589-3653`) and in
  dozens of focus trees.
- **`amount` accepts a variable** → finite production runs. Vanilla uses
  `amount = 1..3` for named ships/prototypes (`common/national_focus/finland.txt:14035`,
  `common/special_projects/projects/land_projects.txt:289-297`). A line created
  with `amount = <deficit>` completes and **releases its factories** when the
  deficit is produced — this is the "switch off when filled" mechanism.
- **Each call creates a NEW line**, never merges (Germany's focus tree makes two
  simultaneous identical `ship_hull_heavy_2` "Bismarck" lines,
  `common/national_focus/germany.txt:6522-6545`).
- **`requested_factories` is NOT documented to accept variables** — every vanilla
  usage in the entire game is a literal integer (grep verified). Mitigation:
  code-generate an if/else ladder (`if factories_for_this = 7 → requested_factories = 7`, …).
- Efficiency scale in practice is **0–100** (vanilla uses 30–50); the doc
  example's `0.1` is wrong (`history/units/GER_1936.txt:409-462`).

## 3. Button placement (confirmed at binary level; needs one in-game check)

- The engine binary contains scripted-GUI attachment keys `parent_window_token`
  **and** `parent_window_name`, and an anchor-token string **`production_tab`**
  (alongside `construction_tab`, `research_tab`, `deployment_tab`, etc.) —
  verified by string-grepping `hoi4.exe`.
- Base-game `common/scripted_guis/` only demonstrates `context_type =
  decision_category`, so production-tab anchoring rests on the binary evidence +
  community practice. **Empirical test #1** below.
- Fallbacks if the token misbehaves: `parent_window_name =
  "countryproductionlineview"` (window name confirmed in
  `interface/countryproductionlineview.gui:11`, and the string exists in the
  binary), or a `top_bar`-anchored button (token confirmed).

## 4. The design: mod-managed finite lines

Click **Optimize** → one scripted effect (code-generated, see §5):

1. **Deficits.** For every buildable land archetype `e` (enumerated at codegen
   time from game+mods): `deficit_e = max(0, num_target_equipment_in_armies@e −
   num_equipment_in_armies@e − num_equipment@e)`.
2. **Logistics.** `get_supply_vehicles_temp` (need=yes / need omitted) for trucks
   and trains → logistics deficits. Trucks: take
   `max(army-side motorized deficit, supply-side need − stockpile)` — the two
   sources overlap on the stockpile, so max avoids double-ordering. Trains:
   supply-side only. **Filled needs → zero deficit → no line → "off."**
3. **Weight & allocate.** Multiply each deficit by its `build_cost_ic` (embedded
   as codegen constants), allocate `num_of_available_military_factories`
   proportionally to IC (same largest-remainder math as the external tool, in
   script arithmetic).
4. **Order.** For each archetype with a positive share:
   `add_equipment_production = { equipment = { type = <best variant> } amount =
   <deficit var> requested_factories = <ladder literal> efficiency = 50 }`.
   Variant selection: codegen maps archetype → variants → unlocking tech and
   emits `has_tech` if/else chains to pick the best researched variant.
5. **Re-click any time.** Finished finite lines have already released their
   factories; the new computation sees the smaller deficits.

**Double-click protection:** deficits don't shrink until equipment is actually
produced, so two quick clicks would double-order. Track outstanding orders in
country variables (`ordered@e += amount` at order time, decay against
`total_equipment_produced_*` snapshots), and/or a short timed cooldown flag on
the button.

## 5. Division of labor (why the hybrid now earns its name)

The **external tool** (`tool/`) becomes a **mod generator** in addition to an
advisor: a `hoi4opt genmod` command reads the active game+mods with the existing
`gamedata` loader and emits the mod's `scripted_guis`, `scripted_effects`, GUI
and localization files — enumerating every archetype, its IC cost, and its
variant→tech mapping as script constants. Mod-agnosticism is preserved **through
regeneration**: change your mod list, re-run `genmod`, get a matching mod.

## 6. Honest limits

- **Only free factories.** No effect removes factories from existing lines, so
  the button cannot strip lines the *player* created by hand. Mod-created lines
  self-terminate; player-created ones are the player's to manage.
- **Cannot read existing lines.** Script can't see which lines exist or their
  factory counts — another reason all mod-created lines carry finite `amount`s
  and tracked order variables.
- **`requested_factories` semantics unproven.** Whether it can pull assigned
  factories (vs only free ones) is documented nowhere and every vanilla use has
  free factories in context. Assume free-only until tested.

## 7. Empirical tests before building (in-game, ~30 min)

1. Scripted GUI with `parent_window_token = production_tab` renders on the
   production screen (fallbacks: `parent_window_name`, `top_bar`).
2. `add_equipment_production` with `requested_factories` > free factories:
   clamps? steals? queues?
3. `num_target_equipment_in_armies@e` includes divisions **in the training
   queue** (expected yes — training divisions are army units — but verify).
4. A finite (`amount = N`) line releases its factories on completion (expected
   yes; vanilla named-ship lines behave this way).

## Verification provenance

Researched by parallel agents over the shipped 1.19.2 docs + game script with
file:line citations; the pivotal claims (`add_equipment_production` semantics,
readability variables, `get_supply_vehicles`, binary attachment tokens) were
independently re-verified by hand against the primary files. The adversarial
verify pass was cut short by a session limit — the four §7 items are exactly the
claims that only an in-game test can settle anyway.
