from hoi4opt import pdxparse
from hoi4opt.pdxparse import Block


def test_scalar_and_nested():
    b = pdxparse.parse(
        """
        infantry_equipment = {
            is_archetype = yes
            build_cost_ic = 0.43
            resources = { steel = 2 }
        }
        """
    )
    eq = b.get_block("infantry_equipment")
    assert isinstance(eq, Block)
    assert eq.get_str("is_archetype") == "yes"
    assert eq.get_float("build_cost_ic") == 0.43
    assert eq.get_block("resources").get_float("steel") == 2.0


def test_duplicate_keys_preserved():
    b = pdxparse.parse(
        """
        regiments = {
            infantry = { x = 0 y = 0 }
            infantry = { x = 0 y = 1 }
            cavalry = { x = 1 y = 0 }
        }
        """
    )
    reg = b.get_block("regiments")
    names = [k for k, _ in reg.pairs()]
    assert names == ["infantry", "infantry", "cavalry"]
    assert len(reg.get_all("infantry")) == 2


def test_bare_token_list():
    b = pdxparse.parse("categories = { category_army category_front_line }")
    cats = b.get_block("categories").scalars()
    assert cats == ["category_army", "category_front_line"]


def test_comments_and_quotes():
    b = pdxparse.parse(
        """
        name = "Royal Guard"   # a comment
        # whole-line comment
        priority = 2
        """
    )
    assert b.get_str("name") == "Royal Guard"
    assert b.get_float("priority") == 2.0
