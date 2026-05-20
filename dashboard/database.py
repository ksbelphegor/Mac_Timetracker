"""SQLite 데이터베이스 모델 — ActivityWatch heartbeat 수신 및 통계 조회"""
import sqlite3
import os
import json
from datetime import datetime, date
from contextlib import contextmanager
from typing import Optional

DB_PATH = os.environ.get("AW_DB_PATH") or os.path.expanduser("~/.mactimetracker/aw.db")


@contextmanager
def get_db():
    """컨텍스트 매니저로 DB 연결 관리 (자동 close)"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """ActivityWatch 호환 스키마로 초기화"""
    with get_db() as conn:
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


def ensure_bucket(bucket_id: str, bucket_type: str = "app", client: str = "aw-watcher-window"):
    """버킷이 없으면 생성"""
    with get_db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO buckets (id, type, client, hostname)
               VALUES (?, ?, ?, ?)""",
            (bucket_id, bucket_type, client, os.uname().nodename)
        )


def insert_heartbeat(bucket_id: str, timestamp: float, duration: float, data: dict):
    """ActivityWatch heartbeat 저장"""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO events (bucket_id, timestamp, duration, data)
               VALUES (?, ?, ?, ?)""",
            (bucket_id, timestamp, duration, json.dumps(data, ensure_ascii=False))
        )


def _parse_date(target_date: Optional[str]) -> tuple[float, float]:
    """날짜 문자열 → (start_ts, end_ts) 변환, 실패시 오늘 기본값"""
    try:
        day = datetime.fromisoformat(target_date).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) if target_date else datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    except (ValueError, TypeError):
        day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_ts = day.timestamp()
    end_ts = day.replace(hour=23, minute=59, second=59).timestamp()
    return start_ts, end_ts


def get_today_events(bucket_id: str = "aw-watcher-window",
                     target_date: Optional[str] = None) -> list:
    """오늘(또는 특정일)의 모든 이벤트를 시간순으로 반환"""
    start_ts, end_ts = _parse_date(target_date)
    with get_db() as conn:
        rows = conn.execute(
            """SELECT timestamp, duration, data FROM events
               WHERE bucket_id = ? AND timestamp >= ? AND timestamp <= ?
               ORDER BY timestamp ASC""",
            (bucket_id, start_ts, end_ts)
        ).fetchall()
    return [dict(r) for r in rows]


def get_app_summary(bucket_id: str = "aw-watcher-window",
                    start_date: Optional[str] = None,
                    end_date: Optional[str] = None) -> list:
    """앱별 총 사용 시간 (일/앱별 집계)"""
    if not start_date:
        start_date = date.today().isoformat()
    if not end_date:
        end_date = date.today().isoformat()

    start_ts, _ = _parse_date(start_date)
    _, end_ts = _parse_date(end_date)

    with get_db() as conn:
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
    return [dict(r) for r in rows]


def get_hourly_breakdown(bucket_id: str = "aw-watcher-window",
                         target_date: Optional[str] = None) -> dict:
    """시간대별 앱 사용 내역 (히트맵용)"""
    start_ts, end_ts = _parse_date(target_date)
    with get_db() as conn:
        rows = conn.execute(
            """SELECT timestamp, duration, data FROM events
               WHERE bucket_id = ? AND timestamp >= ? AND timestamp <= ?
               ORDER BY timestamp ASC""",
            (bucket_id, start_ts, end_ts)
        ).fetchall()

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


BROWSER_APPS = frozenset({
    "Brave Browser", "Google Chrome", "Safari", "Firefox",
    "Microsoft Edge", "Arc", "Orion",
    "Opera", "Opera GX", "Vivaldi", "Tor Browser",
})


def _build_sessions(rows, app_filter: Optional[str] = None, browser_only: bool = False):
    """heartbeat row → 세션 그룹화 (중복 로직 통합)"""
    sessions = []
    current = None

    for r in rows:
        data = json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]
        app = data.get("app", "Unknown")
        title = data.get("title", app)
        ts = r["timestamp"]
        dur = r["duration"]

        if browser_only and app not in BROWSER_APPS:
            if current:
                sessions.append(current)
                current = None
            continue

        if app_filter and app != app_filter:
            if current:
                sessions.append(current)
                current = None
            continue

        if current is None:
            current = {"title": title, "start": ts, "end": ts + dur, "duration": dur}
            if browser_only:
                current["app"] = app
        elif current["title"] == title and (not browser_only or current["app"] == app):
            current["end"] = ts + dur
            current["duration"] += dur
        else:
            sessions.append(current)
            current = {"title": title, "start": ts, "end": ts + dur, "duration": dur}
            if browser_only:
                current["app"] = app

    if current:
        sessions.append(current)

    return sessions


def get_app_sessions(bucket_id: str, app_name: str,
                     target_date: Optional[str] = None) -> list:
    """특정 앱의 창 제목별 세션 (시작/종료/지속시간)"""
    start_ts, end_ts = _parse_date(target_date)
    with get_db() as conn:
        rows = conn.execute(
            """SELECT timestamp, duration, data FROM events
               WHERE bucket_id = ? AND timestamp >= ? AND timestamp <= ?
               ORDER BY timestamp ASC""",
            (bucket_id, start_ts, end_ts)
        ).fetchall()
    return _build_sessions(list(rows), app_filter=app_name)


def get_browser_sessions(bucket_id: str = "aw-watcher-window",
                         target_date: Optional[str] = None) -> list:
    """모든 브라우저의 탭 세션"""
    start_ts, end_ts = _parse_date(target_date)
    with get_db() as conn:
        rows = conn.execute(
            """SELECT timestamp, duration, data FROM events
               WHERE bucket_id = ? AND timestamp >= ? AND timestamp <= ?
               ORDER BY timestamp ASC""",
            (bucket_id, start_ts, end_ts)
        ).fetchall()
    return _build_sessions(list(rows), browser_only=True)
