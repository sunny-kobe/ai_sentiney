from pathlib import Path


def test_sentinel_daily_report_skill_exists_and_has_required_sections():
    skill_path = Path("skills/sentinel-daily-report/SKILL.md")
    assert skill_path.exists()

    content = skill_path.read_text(encoding="utf-8")
    assert "质量门禁" in content
    assert "degraded" in content
    assert "验证命令" in content
