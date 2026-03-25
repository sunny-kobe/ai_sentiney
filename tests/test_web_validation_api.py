import io
import json

from src.web.api import init_routes
from src.web.router import get_router
from src.web.templates import DASHBOARD_HTML


class _FakeHandler:
    def __init__(self, method: str, path: str):
        self.command = method
        self.path = path
        self.headers = {}
        self.rfile = io.BytesIO()
        self.wfile = io.BytesIO()
        self.status_code = None
        self.sent_headers = []

    def send_response(self, code: int):
        self.status_code = code

    def send_header(self, name: str, value: str):
        self.sent_headers.append((name, value))

    def end_headers(self):
        return None


def test_validation_api_returns_compact_snapshot():
    snapshot = {
        "mode": "swing",
        "summary_text": "最近这套中期动作整体有效，可以继续进攻，但仍按分批方式执行。",
        "text": "验证摘要文本",
        "compact": {
            "verdict": "最近这套中期动作整体有效，可以继续进攻，但仍按分批方式执行。",
            "live_sample_count": 6,
            "live_primary_window": 20,
            "synthetic_sample_count": 12,
            "synthetic_primary_window": 20,
            "backtest_trade_count": 4,
            "walkforward_segment_count": 5,
            "offensive_allowed": True,
            "offensive_reason": "真实建议近期进攻统计仍有效，正式回测未见明显恶化",
        },
    }

    class FakeService:
        config = {"portfolio": [{"code": "510300"}]}

        def build_validation_snapshot(self, mode: str):
            assert mode == "swing"
            return snapshot

    init_routes(FakeService())
    handler = _FakeHandler("GET", "/api/validation?mode=swing")

    get_router().dispatch(handler)

    assert handler.status_code == 200
    body = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert body == snapshot
    assert "evaluations" not in handler.wfile.getvalue().decode("utf-8")


def test_dashboard_template_contains_validation_panel():
    assert 'id="validationPanel"' in DASHBOARD_HTML
    assert 'id="validationUpdatedAt"' in DASHBOARD_HTML
    assert "fetch('/api/validation?mode=swing')" in DASHBOARD_HTML
    assert "loadValidation()" in DASHBOARD_HTML
