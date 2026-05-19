"""SQLite 데이터베이스 모델 — ActivityWatch heartbeat 수신 및 통계 조회"""
import sqlite3
import os
import json
import time
from datetime import datetime, date, timedelta
from typing import Optional

DB_PATH = os.environ.get("AW_DB_PATH", "/app/data/aw.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    """ActivityWatch 호환 스키마로 초기화"""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS buckets (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            client TEXT NOT NULL,
            hostname TEXT NOT NULL,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bucket_id TEXT NOT NULL REFERENCES buckets(id),
            timestamp REAL NOT NULL,
            duration REAL NOT NULL DEFAULT 0,
            data TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (bucket_id) REFERENCES buckets(id)
        );

        CREATE INDEX IF NOT EXISTS idx_events_bucket
            ON events(bucket_id, timestamp);

        CREATE INDEX IF NOT EXISTS idx_events_timestamp
            ON events(timestamp);
    """)
    conn.commit()
    conn.close()


def ensure_bucket(bucket_id: str, bucket_type: str = "app", client: str = "aw-watcher-window"):
    """버킷이 없으면 생성"""
    conn = get_db()
    conn.execute(
        """INSERT OR IGNORE INTO buckets (id, type, client, hostname)
           VALUES (?, ?, ?, ?)""",
        (bucket_id, bucket_type, client, os.uname().nodename)
    )
    conn.commit()
    conn.close()


def insert_heartbeat(bucket_id: str, timestamp: float, duration: float, data: dict):
    """ActivityWatch heartbeat 저장"""
    conn = get_db()
    conn.execute(
        """INSERT INTO events (bucket_id, timestamp, duration, data)
           VALUES (?, ?, ?, ?)""",
        (bucket_id, timestamp, duration, json.dumps(data, ensure_ascii=False))
    )
    conn.commit()
    conn.close()


def get_today_events(bucket_id: str = "aw-watcher-window") -> list:
    """오늘의 모든 이벤트를 시간순으로 반환"""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    conn = get_db()
    rows = conn.execute(
        """SELECT timestamp, duration, data FROM events
           WHERE bucket_id = ? AND timestamp >= ?
           ORDER BY timestamp ASC""",
        (bucket_id, today_start)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_app_summary(bucket_id: str = "aw-watcher-window",
                    start_date: Optional[str] = None,
                    end_date: Optional[str] = None) -> list:
    """앱별 총 사용 시간 (일/앱별 집계)"""
    if not start_date:
        start_date = date.today().isoformat()
    if not end_date:
        end_date = date.today().isoformat()

    start_ts = datetime.fromisoformat(start_date).timestamp()
    end_ts = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59).timestamp()

    conn = get_db()
    rows = conn.execute(
        """SELECT date(timestamp, 'unixepoch') as day,
                  json_extract(data, '$.app') as app,
                  SUM(duration) as total_seconds
           FROM events
           WHERE bucket_id = ? AND timestamp >= ? AND timestamp <= ?
           GROUP BY day, app
           ORDER BY day DESC, total_seconds DESC""",
        (bucket_id, start_ts, end_ts)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_hourly_breakdown(bucket_id: str = "aw-watcher-window",
                         target_date: Optional[str] = None) -> dict:
    """시간대별 앱 사용 내역 (히트맵용)"""
    if not target_date:
        target_date = date.today().isoformat()
    day_start = datetime.fromisoformat(target_date)
    day_end = day_start.replace(hour=23, minute=59, second=59)
    start_ts = day_start.timestamp()
    end_ts = day_end.timestamp()

    conn = get_db()
    rows = conn.execute(
        """SELECT timestamp, duration, data FROM events
           WHERE bucket_id = ? AND timestamp >= ? AND timestamp <= ?
           ORDER BY timestamp ASC""",
        (bucket_id, start_ts, end_ts)
    ).fetchall()
    conn.close()

    # 시간별로 그룹핑
    hourly = {}
    for r in rows:
        data = json.loads(r["data"])
        app = data.get("app", "Unknown")
        ts = r["timestamp"]
        hour = datetime.fromtimestamp(ts).hour
        key = f"{hour:02d}:00"
        if key not in hourly:
            hourly[key] = {}
        hourly[key][app] = hourly[key].get(app, 0) + r["duration"]

    return hourly


def get_app_sessions(bucket_id: str, app_name: str,
                     target_date: Optional[str] = None) -> list:
    """특정 앱의 창 제목별 세션 (시작/종료/지속시간)"""
    if not target_date:
        target_date = date.today().isoformat()
    day_start = datetime.fromisoformat(target_date)
    day_end = day_start.replace(hour=23, minute=59, second=59)
    start_ts = day_start.timestamp()
    end_ts = day_end.timestamp()

    conn = get_db()
    rows = conn.execute(
        """SELECT timestamp, duration, data FROM events
           WHERE bucket_id = ? AND timestamp >= ? AND timestamp <= ?
           ORDER BY timestamp ASC""",
        (bucket_id, start_ts, end_ts)
    ).fetchall()
    conn.close()

    # 연속된 동일 (app + title) heartbeat를 세션으로 그룹핑
    sessions = []
    current = None  # {title, start, end, total_dur}

    for r in rows:
        data = json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]
        app = data.get("app", "Unknown")
        if app != app_name:
            if current:
                sessions.append(current)
                current = None
            continue

        title = data.get("title", app)
        ts = r["timestamp"]
        dur = r["duration"]

        if current is None:
            # 새 세션
            current = {
                "title": title,
                "start": ts,
                "end": ts + dur,
                "duration": dur,
            }
        elif current["title"] == title:
            # 같은 제목 → 연장
            current["end"] = ts + dur
            current["duration"] += dur
        else:
            # 제목 변경 → 이전 세션 종료, 새 세션 시작
            sessions.append(current)
            current = {
                "title": title,
                "start": ts,
                "end": ts + dur,
                "duration": dur,
            }

    if current:
        sessions.append(current)

    return sessions
