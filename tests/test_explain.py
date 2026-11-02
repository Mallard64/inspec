from inspec.explain import describe_check, describe_result, learned
from inspec.schema import Check, CheckProgram, Part


def program(**limits) -> CheckProgram:
    return CheckProgram(kit_name="kit", parts=[Part(id="long_screw", concept="screw", **limits),
                                               Part(id="granola", concept="granola")],
                        checks=[Check(id="n", type="count", part="long_screw", min=1, max=1),
                                Check(id="g", type="count", part="granola", min=1)])


def test_checks_read_as_sentences():
    p = program()
    assert [describe_check(c) for c in p.checks] == ["Exactly 1 × long screw", "Granola is present"]
    hole = Check(id="h", type="measure", part="nut", metric="hole", min=0.1, max=0.33)
    assert describe_check(hole) == "Every nut has a hole of 10%–33% of its outline"
    area = Check(id="a", type="measure", part="granola", metric="area", min=375230, max=481162)
    assert describe_result(area, [326007.0], "") == \
        "Granola covers 375,230–481,162 px² (the amount): measured 326,007"


def test_learned_lists_repairs_and_new_limits():
    final = program(min_length=355)
    final.checks.append(Check(id="l", type="measure", part="long_screw", metric="length",
                              min=396, max=441))
    assert learned(program(), final, [{"original": "nectarine", "chosen": "apple"}]) == [
        'SAM didn\'t know "nectarine", so it looks for "apple" instead',
        "A long screw is told apart by length at least 355 px",
        "New check: Every long screw is 396–441 px long"]


def test_damage_answers_read_as_findings():
    from inspec.explain import describe_question
    assert describe_question("tangerines_damaged", False) == "Tangerines: no damage"
    assert describe_question("banana_chips_damaged", True) == "Banana chips: damaged"
    assert describe_question("foreign_object", False) == "Nothing that isn't on the list"
