from hoi4opt.gamedata import Battalion, Equipment, GameData, Template
from hoi4opt import needs, optimize


def _toy_gamedata() -> GameData:
    equipment = {
        "infantry_equipment": Equipment(
            "infantry_equipment", True, None, build_cost_ic=1.0, resources={"steel": 2}
        ),
        "artillery_equipment": Equipment(
            "artillery_equipment", True, None, build_cost_ic=4.0, resources={"steel": 4, "tungsten": 2}
        ),
    }
    battalions = {
        "infantry": Battalion("infantry", need={"infantry_equipment": 100}),
        "artillery": Battalion("artillery", need={"artillery_equipment": 12}),
    }
    templates = {
        "Line Inf": Template("Line Inf", battalions={"infantry": 6, "artillery": 1}),
    }
    return GameData(equipment, battalions, templates)


def test_demand_sums_costs():
    gd = _toy_gamedata()
    d = needs.demand_for_order(gd, [("Line Inf", 10)])
    # 6 inf battalions * 100 * 10 divisions = 6000 rifles; 1 arty * 12 * 10 = 120 guns
    assert d.by_equipment["infantry_equipment"].units == 6000
    assert d.by_equipment["artillery_equipment"].units == 120
    assert d.by_equipment["infantry_equipment"].total_ic == 6000.0
    assert d.by_equipment["artillery_equipment"].total_ic == 480.0
    assert d.total_ic == 6480.0


def test_allocation_is_proportional_to_ic():
    gd = _toy_gamedata()
    d = needs.demand_for_order(gd, [("Line Inf", 10)])
    plan = optimize.allocate(d, factories=20, max_per_line=100)
    inf = next(l for l in plan.lines if l.equipment == "infantry_equipment")
    art = next(l for l in plan.lines if l.equipment == "artillery_equipment")
    # 6000 : 480 IC ratio => ~18.5 : 1.5 of 20 factories
    assert inf.factories + art.factories == 20
    assert inf.factories == 19 and art.factories == 1
    # balanced: completion times should be close
    assert abs(inf.days_to_complete - art.days_to_complete) < inf.days_to_complete


def test_per_line_cap_creates_bottleneck():
    gd = _toy_gamedata()
    d = needs.demand_for_order(gd, [("Line Inf", 10)])
    plan = optimize.allocate(d, factories=20, max_per_line=15)
    inf = next(l for l in plan.lines if l.equipment == "infantry_equipment")
    assert inf.factories == 15  # capped
    assert plan.bottleneck == "infantry_equipment"
    assert plan.factories_used == 20  # excess redistributed, none wasted


def test_resource_warning_when_all_lines_share_scarcity():
    gd = _toy_gamedata()
    d = needs.demand_for_order(gd, [("Line Inf", 10)])
    plan = optimize.allocate(d, factories=20, max_per_line=100, resource_budget={"steel": 10})
    assert plan.factories_used == 20  # not wasted when reallocation can't help
    assert any("steel" in w for w in plan.resource_warnings)
