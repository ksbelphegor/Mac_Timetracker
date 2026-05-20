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
    get_today_events, get_app_summary, get_hourly_breakdown,
    get_app_sessions, get_browser_sessions,
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
def api_today(target_date: str = None):
    """오늘(또는 특정일) 앱별 통계 + 마지막 창 제목"""
    events = get_today_events(BUCKET_ID, target_date)
    apps = {}
    app_titles = {}
    total = 0
    for e in events:
        data = json.loads(e["data"]) if isinstance(e["data"], str) else e["data"]
        app = data.get("app", "Unknown")
        title = data.get("title", "")
        dur = e["duration"]
        app_titles[app] = title  # 매번 덮어쓰기 → 마지막 이벤트 제목 유지
        apps[app] = apps.get(app, 0) + dur
        total += dur

    sorted_apps = sorted(apps.items(), key=lambda x: x[1], reverse=True)

    current_app_name = None
    current_title = None
    if events:
        last_data = events[-1]["data"]
        if isinstance(last_data, str):
            last_data = json.loads(last_data)
        current_app_name = last_data.get("app")
        current_title = last_data.get("title", "")

    return {
        "total_seconds": total,
        "apps": [{"name": n, "seconds": s, "last_title": app_titles.get(n, "")} for n, s in sorted_apps],
        "current_app": current_app_name,
        "current_title": current_title,
    }


@app.get("/api/now")
def api_now():
    """현재 실행 중인 앱 (가장 최근 heartbeat)"""
    events = get_today_events(BUCKET_ID)
    if not events:
        return {"app": None, "since": None}
    last = events[-1]
    data = last["data"]
    if isinstance(data, str):
        data = json.loads(data)
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


@app.get("/api/recent")
def api_recent(limit: int = 20):
    """최근 heartbeat 내역 (앱 + 창 제목 + 시간)"""
    today_events = get_today_events(BUCKET_ID)
    recent = []
    for e in today_events[-limit:]:
        data = json.loads(e["data"]) if isinstance(e["data"], str) else e["data"]
        recent.append({
            "time": e["timestamp"],
            "app": data.get("app", "Unknown"),
            "title": data.get("title", ""),
            "duration": e["duration"],
        })
    recent.reverse()
    return {"events": recent}


@app.get("/api/hourly")
def api_hourly(target_date: str = None):
    """시간대별 앱 내역"""
    return get_hourly_breakdown(BUCKET_ID, target_date)


@app.get("/api/sessions/{app_name}")
def api_sessions(app_name: str, target_date: str = None):
    """특정 앱의 창 제목별 세션 목록"""
    sessions = get_app_sessions(BUCKET_ID, app_name, target_date)
    result = []
    for s in sessions:
        result.append({
            "title": s["title"],
            "start": s["start"],
            "end": s["end"],
            "duration": s["duration"],
        })
    result.reverse()  # 최신순
    return {"app": app_name, "sessions": result}


@app.get("/api/browser-sessions")
def api_browser_sessions(target_date: str = None):
    """모든 브라우저의 탭 세션"""
    sessions = get_browser_sessions(BUCKET_ID, target_date)
    for s in sessions:
        s["start"] = s["start"]
        s["end"] = s["end"]
    sessions.reverse()
    return {"sessions": sessions}


# ───── 대시보드 ─────

@app.get("/", response_class=HTMLResponse)
def dashboard():
    """메인 대시보드 페이지"""
    html_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r") as f:
            return f.read()
    return HTMLResponse("<h1>Dashboard not found</h1>")
