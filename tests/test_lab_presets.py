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


def test_resolve_lab_preset_returns_aggressive_reusable_midterm_presets():
    trend = resolve_lab_preset("aggressive_trend_guard")
    concentration = resolve_lab_preset("aggressive_leader_focus")
    rotation = resolve_lab_preset("aggressive_core_rotation")

    assert trend["parameter_overrides"]["drawdown_limit"] == "0.10"
    assert trend["parameter_overrides"]["lookback_window"] == "40"
    assert concentration["portfolio_overrides"]["watchlist_limit"] == "1"
    assert concentration["portfolio_overrides"]["risk_profile"] == "aggressive"
    assert rotation["portfolio_overrides"]["core_only"] == "broad_beta"
