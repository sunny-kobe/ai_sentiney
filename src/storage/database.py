import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Any
from src.utils.logger import logger

class SentinelDB:
    def __init__(self, db_path: str = "data/sentinel.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initialize the single table schema and handle migrations."""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS daily_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,          -- YYYY-MM-DD
            timestamp TEXT NOT NULL,     -- ISO8601
            mode TEXT NOT NULL,          -- 'midday' or 'close'
            market_breadth TEXT,         -- Raw string summary
            sentiment_score REAL,        -- Parsed from AI (future proof)
            ai_summary TEXT,             -- Full text
            raw_data JSON,               -- The entire context dump
            ai_result JSON,              -- Stored AI output (Actionable Advice)
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
        index_sql = "CREATE INDEX IF NOT EXISTS idx_date_mode ON daily_records (date, mode);"
        
        try:
            with self._get_conn() as conn:
                conn.execute(create_table_sql)
                conn.execute(index_sql)
                
                # Auto-Migration: Check if ai_result exists
                cursor = conn.execute("PRAGMA table_info(daily_records);")
                columns = [info[1] for info in cursor.fetchall()]
                if "ai_result" not in columns:
                    conn.execute("ALTER TABLE daily_records ADD COLUMN ai_result JSON;")
                    logger.info("Migrated DB: Added ai_result column.")
                    
        except Exception as e:
            logger.error(f"DB Initialization failed: {e}")

    def save_record(self, mode: str, ai_input: Dict[str, Any], ai_analysis: Dict[str, Any]):
        """
        Saves a run record.
        """
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        ts_str = now.isoformat()
        
        # Serialize huge JSONs
        try:
            raw_json = json.dumps(ai_input, ensure_ascii=False)
            ai_result_json = json.dumps(ai_analysis, ensure_ascii=False)
            summary = ai_analysis.get('summary', '') or ai_analysis.get('market_summary', '')
            
            # TODO: Future enhancement - extract a numerical score 0-100 from AI analysis
            sentiment_score = 0.0 
            
            sql = """
            INSERT INTO daily_records (date, timestamp, mode, market_breadth, sentiment_score, ai_summary, raw_data, ai_result)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            with self._get_conn() as conn:
                conn.execute(sql, (
                    date_str, 
                    ts_str, 
                    mode, 
                    ai_input.get('market_breadth', 'N/A'),
                    sentiment_score,
                    summary,
                    raw_json,
                    ai_result_json
                ))
            logger.info(f"✅ Saved {mode} record to DB for {date_str}.")
            
        except Exception as e:
            logger.error(f"Failed to save record to DB: {e}")

    def get_latest_record(self, mode: str = 'midday') -> Optional[Dict]:
        """Fetch the most recent record for context replay."""
        sql = "SELECT raw_data FROM daily_records WHERE mode = ? ORDER BY id DESC LIMIT 1"
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(sql, (mode,))
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
        except Exception as e:
            logger.error(f"Failed to fetch latest record: {e}")
        return None

    def get_last_close_analysis(self) -> Optional[Dict]:
        """Fetch the analysis result from the last 'close' session."""
        sql = "SELECT ai_result FROM daily_records WHERE mode = 'close' ORDER BY id DESC LIMIT 1"
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(sql)
                row = cursor.fetchone()
                if row and row[0]: # Check if ai_result is not null
                    return json.loads(row[0])
        except Exception as e:
            logger.error(f"Failed to fetch last close analysis: {e}")
        return None

    def get_record_by_date(self, date: str, mode: str = 'midday') -> Optional[Dict]:
        """Fetch raw_data for a specific date and mode."""
        sql = "SELECT raw_data FROM daily_records WHERE date = ? AND mode = ? ORDER BY id DESC LIMIT 1"
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(sql, (date, mode))
                row = cursor.fetchone()
                if row and row[0]:
                    return json.loads(row[0])
        except Exception as e:
            logger.error(f"Failed to fetch record for {date}/{mode}: {e}")
        return None

    def get_analysis_by_date(self, date: str, mode: str = 'midday') -> Optional[Dict]:
        """Fetch ai_result for a specific date and mode."""
        sql = "SELECT ai_result FROM daily_records WHERE date = ? AND mode = ? ORDER BY id DESC LIMIT 1"
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(sql, (date, mode))
                row = cursor.fetchone()
                if row and row[0]:
                    return json.loads(row[0])
        except Exception as e:
            logger.error(f"Failed to fetch analysis for {date}/{mode}: {e}")
        return None

    def get_last_analysis(self, mode: str = 'midday') -> Optional[Dict]:
        """Fetch the most recent ai_result for a given mode."""
        sql = "SELECT ai_result, raw_data FROM daily_records WHERE mode = ? AND ai_result IS NOT NULL ORDER BY id DESC LIMIT 1"
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(sql, (mode,))
                row = cursor.fetchone()
                if row:
                    return {
                        "ai_result": json.loads(row[0]) if row[0] else None,
                        "raw_data": json.loads(row[1]) if row[1] else None
                    }
        except Exception as e:
            logger.error(f"Failed to fetch last analysis for {mode}: {e}")
        return None

    def get_records_range(self, mode: str = 'close', days: int = 7) -> List[Dict]:
        """Fetch the most recent N days of records for trend analysis."""
        sql = """
        SELECT date, raw_data, ai_result FROM daily_records
        WHERE mode = ? AND ai_result IS NOT NULL
        ORDER BY date DESC LIMIT ?
        """
        results = []
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(sql, (mode, days))
                for row in cursor.fetchall():
                    results.append({
                        "date": row[0],
                        "raw_data": json.loads(row[1]) if row[1] else None,
                        "ai_result": json.loads(row[2]) if row[2] else None
                    })
        except Exception as e:
            logger.error(f"Failed to fetch records range: {e}")
        return results
