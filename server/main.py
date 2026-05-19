"""
Mac Time Tracker — FastAPI 서버

ActivityWatch 호환 heartbeat 수신 API + 통계/대시보드 엔드포인트
"""
import json
import os
from datetime import date, timedelta
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import (
    init_db, ensure_bucket, insert_heartbeat,
    get_today_events, get_app_summary, get_hourly_breakdown
)

app = FastAPI(title="Mac Time Tracker", version="1.0.0")

# 정적 파일 (대시보드)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ActivityWatch 호환 버킷 ID
BUCKET_ID = "aw-watcher-window"


@app.on_event("startup")
def on_startup():
    init_db()
    ensure_bucket(BUCKET_ID)


# ───── ActivityWatch 호환 API ─────

class HeartbeatPayload(BaseModel):
    timestamp: float
    duration: float = 0.0
    data: dict = {}


@app.post("/api/0/buckets/{bucket_id}/heartbeat")
def post_heartbeat(bucket_id: str, payload: HeartbeatPayload):
    """ActivityWatch 호환 heartbeat 엔드포인트"""
    ensure_bucket(bucket_id)
    insert_heartbeat(
        bucket_id=bucket_id,
        timestamp=payload.timestamp,
        duration=payload.duration,
        data=payload.data
    )
    return {"status": "ok"}


@app.post("/api/heartbeat")
def post_simple_heartbeat(payload: HeartbeatPayload):
    """간편 heartbeat (버킷 ID 자동 지정)"""
    return post_heartbeat(BUCKET_ID, payload)


# ───── 통계 API ─────

@app.get("/api/today")
def api_today():
    """오늘 현재 시간까지의 앱별 통계"""
    events = get_today_events(BUCKET_ID)
    apps = {}
    total = 0
    for e in events:
        data = json.loads(e["data"]) if isinstance(e["data"], str) else e["data"]
        app = data.get("app", "Unknown")
        dur = e["duration"]
        apps[app] = apps.get(app, 0) + dur
        total += dur

    sorted_apps = sorted(apps.items(), key=lambda x: x[1], reverse=True)
    return {
        "total_seconds": total,
        "apps": [{"name": n, "seconds": s} for n, s in sorted_apps],
        "current_app": events[-1]["data"].get("app") if events else None
    }


@app.get("/api/now")
def api_now():
    """현재 실행 중인 앱 (가장 최근 heartbeat)"""
    events = get_today_events(BUCKET_ID)
    if not events:
        return {"app": None, "since": None}
    last = events[-1]
    data = json.loads(last["data"]) if isinstance(last["data"], str) else last["data"]
    return {
        "app": data.get("app"),
        "title": data.get("title"),
        "since": last["timestamp"]
    }


@app.get("/api/summary")
def api_summary(start: str = None, end: str = None):
    """앱별 통계 요약"""
    rows = get_app_summary(BUCKET_ID, start, end)
    return {"rows": rows}


@app.get("/api/hourly")
def api_hourly(target_date: str = None):
    """시간대별 앱 내역"""
    return get_hourly_breakdown(BUCKET_ID, target_date)


# ───── 대시보드 ─────

@app.get("/", response_class=HTMLResponse)
def dashboard():
    """메인 대시보드 페이지"""
    html_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r") as f:
            return f.read()
    return HTMLResponse("<h1>Dashboard not found</h1>")
