from tokenscope.pricing import (cost_of, cost_of_model, has_model_override,
                                rates_for_model, validate_pricing)

DOC = {
    "families": {
        "fable":  {"input": 10.0, "output": 50.0, "cache_write": 12.5, "cache_read": 1.0},
        "opus":   {"input": 5.0, "output": 25.0, "cache_write": 6.25, "cache_read": 0.5},
        "sonnet": {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.3},
        "haiku":  {"input": 1.0, "output": 5.0, "cache_write": 1.25, "cache_read": 0.1},
        "other":  {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.3},
    },
}


def test_model_without_override_uses_its_family_rate():
    assert rates_for_model("claude-opus-5", "opus", DOC) == DOC["families"]["opus"]
    assert cost_of_model("claude-opus-5", "opus", 1_000_000, 0, 0, 0, DOC) == 5.0


def test_model_override_wins_over_the_family():
    doc = {**DOC, "models": {"claude-opus-4-8": {"input": 2.0, "output": 10.0,
                                                 "cache_write": 2.5, "cache_read": 0.2}}}
    assert cost_of_model("claude-opus-4-8", "opus", 1_000_000, 0, 0, 0, doc) == 2.0
    # Siblings in the same family are untouched.
    assert cost_of_model("claude-opus-5", "opus", 1_000_000, 0, 0, 0, doc) == 5.0
    assert has_model_override("claude-opus-4-8", doc)
    assert not has_model_override("claude-opus-5", doc)


def test_partial_override_falls_back_per_rate_key():
    doc = {**DOC, "models": {"claude-opus-4-8": {"output": 10.0}}}
    rates = rates_for_model("claude-opus-4-8", "opus", doc)
    assert rates["output"] == 10.0
    assert rates["input"] == 5.0  # inherited
    assert cost_of_model("claude-opus-4-8", "opus", 1_000_000, 1_000_000, 0, 0, doc) == 15.0


def test_unknown_model_and_family_land_on_other():
    assert cost_of_model("mystery-model", "nope", 1_000_000, 0, 0, 0, DOC) == 3.0


def test_family_level_cost_is_unchanged_by_model_overrides():
    doc = {**DOC, "models": {"claude-opus-4-8": {"input": 2.0}}}
    assert cost_of("opus", 1_000_000, 0, 0, 0, doc) == 5.0


def test_validate_accepts_absent_and_partial_models_block():
    assert validate_pricing(DOC) == []
    assert validate_pricing({**DOC, "models": {}}) == []
    assert validate_pricing({**DOC, "models": {"m": {"input": 1.0}}}) == []


def test_validate_rejects_bad_models_block():
    assert validate_pricing({**DOC, "models": []})
    assert validate_pricing({**DOC, "models": {"m": {"input": -1}}})
    assert validate_pricing({**DOC, "models": {"m": {"bogus_key": 1}}})
