from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_readme_and_config_promote_swing_mode_as_primary_positioning():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    config = (ROOT / "config.yaml").read_text(encoding="utf-8")

    assert "--mode swing" in readme
    assert "10/20/40" in readme
    assert "平均收益" in readme
    assert "平均回撤" in readme
    assert "平均超额" in readme
    assert "短线命中率作为主KPI" in readme

    assert "default_mode: \"swing\"" in config
    assert "windows: [10, 20, 40]" in config
    assert "action_labels:" in config
    assert "增配" in config
