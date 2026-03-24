import json
import sqlite3

from src.storage.database import SentinelDB


def _insert_record(db_path, *, day, timestamp, mode, marker):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO daily_records
            (date, timestamp, mode, market_breadth, sentiment_score, ai_summary, raw_data, ai_result)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                day,
                timestamp,
                mode,
                "N/A",
                0.0,
                marker,
                json.dumps({"marker": marker}, ensure_ascii=False),
                json.dumps({"marker": marker, "actions": []}, ensure_ascii=False),
            ),
        )


def test_get_records_range_returns_unique_latest_days(tmp_path):
    db_path = tmp_path / "sentinel.db"
    db = SentinelDB(db_path=str(db_path))

    _insert_record(db_path, day="2026-03-19", timestamp="2026-03-19T11:40:00", mode="midday", marker="old-0319")
    _insert_record(db_path, day="2026-03-19", timestamp="2026-03-19T15:10:00", mode="midday", marker="new-0319")
    _insert_record(db_path, day="2026-03-18", timestamp="2026-03-18T11:40:00", mode="midday", marker="0318")
    _insert_record(db_path, day="2026-03-17", timestamp="2026-03-17T11:40:00", mode="midday", marker="0317")

    records = db.get_records_range(mode="midday", days=2)

    assert [record["date"] for record in records] == ["2026-03-19", "2026-03-18"]
    assert records[0]["ai_result"]["marker"] == "new-0319"
    assert records[1]["ai_result"]["marker"] == "0318"


def test_save_record_persists_rows_for_preclose_and_swing(tmp_path):
    db_path = tmp_path / "sentinel.db"
    db = SentinelDB(db_path=str(db_path))

    db.save_record("preclose", {"market_breadth": "涨: 10 / 跌: 5"}, {"summary": "preclose summary", "actions": []})
    db.save_record("swing", {"market_breadth": "涨: 10 / 跌: 5"}, {"summary": "swing summary", "actions": []})

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT mode, ai_summary FROM daily_records ORDER BY id"
        ).fetchall()

    assert rows == [
        ("preclose", "preclose summary"),
        ("swing", "swing summary"),
    ]
