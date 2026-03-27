from pathlib import Path


WORKFLOW_PATH = Path(".github/workflows/daily_sentinel.yml")


def test_daily_workflow_supports_swing_schedule_and_manual_inputs():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert 'cron: "10 20 * * 0-4"' in content
    assert 'cron: "20 3 * * 1-5"' in content
    assert 'cron: "35 6 * * 1-5"' in content
    assert 'cron: "5 7 * * 1-5"' in content
    assert 'cron: "0 12 * * 1-5"' in content
    assert "TZ: Asia/Shanghai" in content
    assert "workflow_dispatch:" in content
    assert "mode:" in content
    assert "publish_target:" in content
    assert "preclose" in content
    assert "swing" in content


def test_daily_workflow_routes_manual_and_scheduled_swing_runs():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert '"10 20 * * 0-4")' in content
    assert 'TARGET_MODE="preclose"' in content
    assert 'TARGET_MODE="swing"' in content
    assert "github.event.inputs.mode" in content
    assert "github.event.schedule" in content
    assert "--publish-target" in content
    assert "current_hour=$(date +%-H)" in content


def test_daily_workflow_uses_supported_python_runtime():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert 'python-version: "3.11"' in content
