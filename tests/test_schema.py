import pytest
from pydantic import ValidationError

from inspec.schema import CheckProgram, validate_concept


def screw_bag(**overrides) -> dict:
    program = {
        "kit_name": "screw bag",
        "parts": [
            {"id": "long_screw", "concept": "screw", "min_length": 300},
            {"id": "short_screw", "concept": "screw", "max_length": 300},
            {"id": "nut", "concept": "nut"},
            {"id": "washer", "concept": "washer"},
        ],
        "checks": [
            {"id": "nut_count", "type": "count", "part": "nut", "min": 2, "max": 2},
            {"id": "long_len", "type": "measure", "part": "long_screw", "metric": "length",
             "min": 350, "max": 420},
        ],
    }
    program.update(overrides)
    return program


def test_valid_program_round_trips_through_json():
    program = CheckProgram.model_validate(screw_bag())
    again = CheckProgram.model_validate_json(program.model_dump_json())
    assert again == program
    assert program.concepts() == ["screw", "nut", "washer"]


@pytest.mark.parametrize("concept", ["", "  ", "nut, washer", "nut; washer", "nut and washer",
                                     "Nut And Washer", "a b c d e"])
def test_rejects_non_noun_phrase_concepts(concept):
    with pytest.raises(ValueError):
        validate_concept(concept)


def test_concept_is_stripped():
    assert validate_concept("  hex nut ") == "hex nut"


def bad_check(**fields) -> dict:
    return screw_bag(checks=[{"id": "c", "type": "count", "part": "nut", "min": 1, **fields}])


@pytest.mark.parametrize("program", [
    screw_bag(parts=screw_bag()["parts"] + [{"id": "nut", "concept": "nut"}]),  # duplicate part id
    screw_bag(checks=screw_bag()["checks"] * 2),                                # duplicate check id
    bad_check(part="bolt"),                                                     # unknown part
    bad_check(min=None),                                                        # no bounds
    bad_check(min=3, max=2),                                                    # min > max
    bad_check(min=-1),                                                          # negative
    bad_check(min=1.5),                                                         # fractional count
    bad_check(metric="area"),                                                   # count with metric
    bad_check(type="measure"),                                                  # measure, no metric
    bad_check(id="Nut-Count"),                                                  # bad id
    bad_check(colour="red"),                                                    # extra field
    screw_bag(merge_overlap=0),                                                 # overlap range
    screw_bag(merge_overlap=1.5),                                               # overlap range
    screw_bag(dedupe=[]),                                                       # removed field
    screw_bag(parts=[{"id": "nut", "concept": "nut", "min_area": 9, "max_area": 1}],
              checks=screw_bag()["checks"][:1]),                                # part range
    screw_bag(checks=[]),                                                       # no checks
])
def test_rejects_invalid_programs(program):
    with pytest.raises(ValidationError):
        CheckProgram.model_validate(program)


def test_json_schema_is_generated():
    schema = CheckProgram.model_json_schema()
    assert {"parts", "checks", "merge_overlap"} <= set(schema["properties"])
