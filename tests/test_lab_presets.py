from src.lab.presets import resolve_lab_preset


def test_resolve_lab_preset_returns_candidate_defaults():
    preset = resolve_lab_preset("defensive_exit_fix")

    assert preset["name"] == "defensive_exit_fix"
    assert preset["rule_overrides"]["hold_in_defense"] == "degrade"


def test_resolve_lab_preset_rejects_unknown_name():
    try:
        resolve_lab_preset("missing")
    except ValueError as exc:
        assert "unknown preset" in str(exc)
    else:
        raise AssertionError("expected unknown preset to fail")
