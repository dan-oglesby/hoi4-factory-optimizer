from hoi4opt import genmod, pdxparse
from hoi4opt.gamedata import Battalion, Equipment, GameData


def _toy_gamedata() -> GameData:
    equipment = {
        # normal archetype with a tech-gated better variant + always-active base
        "infantry_equipment": Equipment(
            "infantry_equipment", True, None, build_cost_ic=0.43,
            resources={"steel": 2}, year=1936, is_buildable="no",
        ),
        "infantry_equipment_0": Equipment(
            "infantry_equipment_0", False, "infantry_equipment", build_cost_ic=None,
            year=1918, priority=5, active="yes",
        ),
        "infantry_equipment_1": Equipment(
            "infantry_equipment_1", False, "infantry_equipment", build_cost_ic=0.5,
            year=1936, priority=10,
        ),
        # trucks
        "motorized_equipment": Equipment(
            "motorized_equipment", True, None, build_cost_ic=2.5,
            year=1936, is_buildable="no", supply_truck=True, types=["motorized"],
        ),
        "motorized_equipment_1": Equipment(
            "motorized_equipment_1", False, "motorized_equipment", build_cost_ic=None,
            year=1936, priority=30,
        ),
        # trains (no battalion needs them -> must still be included)
        "train_equipment": Equipment(
            "train_equipment", True, None, build_cost_ic=70,
            year=1910, is_buildable="no", active="no", types=["train"],
        ),
        "train_equipment_1": Equipment(
            "train_equipment_1", False, "train_equipment", build_cost_ic=70,
            year=1910, priority=10,
        ),
        # designer archetype -> must be excluded
        "light_tank_chassis": Equipment(
            "light_tank_chassis", True, None, build_cost_ic=8,
            year=1936, is_buildable="no", has_module_slots=True,
        ),
        "light_tank_chassis_1": Equipment(
            "light_tank_chassis_1", False, "light_tank_chassis", build_cost_ic=8,
            year=1936, has_module_slots=True,
        ),
    }
    battalions = {
        "infantry": Battalion("infantry", need={"infantry_equipment": 100}),
        "motorized": Battalion(
            "motorized", need={"infantry_equipment": 100, "motorized_equipment": 50}
        ),
        "light_armor": Battalion("light_armor", need={"light_tank_chassis": 60}),
    }
    unlock_techs = {
        "infantry_equipment_1": ["infantry_weapons1"],
        "motorized_equipment_1": ["motorised_infantry", "some_mod_truck_tech"],
        "train_equipment_1": ["basic_train"],
    }
    return GameData(equipment, battalions, {}, unlock_techs=unlock_techs)


def test_model_includes_needs_trucks_and_trains():
    model = genmod.build_model(_toy_gamedata())
    names = {p.archetype for p in model.plans}
    assert names == {"infantry_equipment", "motorized_equipment", "train_equipment"}
    truck = next(p for p in model.plans if p.is_truck)
    assert truck.archetype == "motorized_equipment"
    train = next(p for p in model.plans if p.is_train)
    assert train.archetype == "train_equipment"


def test_designer_equipment_excluded_with_reason():
    model = genmod.build_model(_toy_gamedata())
    excluded = dict(model.excluded)
    assert "light_tank_chassis" in excluded
    assert "designer" in excluded["light_tank_chassis"]


def test_variants_sorted_best_first_with_unlocks():
    model = genmod.build_model(_toy_gamedata())
    inf = next(p for p in model.plans if p.archetype == "infantry_equipment")
    assert [v.token for v in inf.variants] == ["infantry_equipment_1", "infantry_equipment_0"]
    assert inf.variants[0].techs == ["infantry_weapons1"]
    assert inf.variants[1].techs is None  # active = yes
    # cost inheritance: _0 has no build_cost_ic -> archetype's 0.43
    assert inf.variants[1].cost == 0.43


def test_generated_script_parses_and_has_key_constructs():
    model = genmod.build_model(_toy_gamedata())
    text = genmod.emit_scripted_effect(model, max_per_line=5, cooldown_days=3)
    root = pdxparse.parse(text)
    fx = root.get_block("fo_run_optimizer")
    assert fx is not None

    # logistics: engine-computed need is queried for both vehicle types
    assert "get_supply_vehicles_temp = { var = fo_truck_need type = truck need = yes }" in text
    assert "get_supply_vehicles_temp = { var = fo_train_need type = train need = yes }" in text
    # trucks take max(army-side, supply-side)
    assert "value = fo_def_motorized_equipment max = fo_truck_def" in text
    # deficit formula reads the three engine variables
    assert "num_target_equipment_in_armies@infantry_equipment" in text
    assert "num_equipment_in_armies@infantry_equipment" in text
    assert "num_equipment@infantry_equipment" in text
    # finite lines: amount is the deficit variable, factories are literals
    assert "amount = fo_amount_infantry_equipment" in text
    assert "requested_factories = 5" in text  # ladder top == max_per_line
    assert "requested_factories = 1" in text  # ladder bottom
    assert "requested_factories = 6" not in text  # never above the cap
    # multi-tech unlock becomes an OR
    assert "OR = { has_tech = motorised_infantry has_tech = some_mod_truck_tech }" in text
    # cooldown flag with configured days
    assert "set_country_flag = { flag = fo_cooldown days = 3 value = 1 }" in text


def test_ladder_count_matches_cap_times_variants():
    model = genmod.build_model(_toy_gamedata())
    text = genmod.emit_scripted_effect(model, max_per_line=5)
    # infantry: 2 variants x 5 rungs; motorized: 1 x 5; train: 1 x 5 = 20 adds
    assert text.count("add_equipment_production") == 20


def test_always_active_variant_terminates_chain_as_else():
    model = genmod.build_model(_toy_gamedata())
    text = genmod.emit_scripted_effect(model, max_per_line=5)
    # order chain: if has_tech -> produce _1, else -> produce _0 (fallback).
    # Search from the ordering section (the cost chain earlier also has an else).
    idx_order = text.index("set_variable = { fo_plan_infantry_equipment = fo_share_infantry_equipment }")
    idx_if = text.index("has_tech = infantry_weapons1", idx_order)
    idx_else = text.index("else = {", idx_if)
    chunk = text[idx_else : idx_else + 1500]
    assert "type = infantry_equipment_0" in chunk
    assert "add_equipment_production" in chunk


def test_generated_loc_lists_plans_and_exclusions():
    model = genmod.build_model(_toy_gamedata())
    loc = genmod.emit_generated_loc(model)
    assert loc.startswith("l_english:")
    assert "[?fo_plan_infantry_equipment|0]" in loc
    assert "$train_equipment$" in loc
    assert "light_tank_chassis" in loc  # excluded list


def test_start_efficiency_flag_optional():
    model = genmod.build_model(_toy_gamedata())
    fair = genmod.emit_scripted_effect(model, max_per_line=3)
    assert "efficiency" not in fair  # default: no head start (not a cheat)
    boosted = genmod.emit_scripted_effect(model, max_per_line=3, start_efficiency=50)
    assert "efficiency = 50" in boosted
