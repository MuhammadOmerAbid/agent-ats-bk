import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Duplicated from agent-jobs's agent_jobs/db/schema.py (not cross-imported —
# agent-jobs and agent-ats are separate processes/repos sharing one SQLite
# file). agent-jobs owns migrations; this is bootstrap-only so the dashboard
# doesn't 500 if it starts before agent-jobs has ever run.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_native_id TEXT,
    title TEXT NOT NULL,
    company TEXT,
    company_url TEXT,
    location TEXT,
    remote_type TEXT,
    salary_min_usd INTEGER,
    salary_max_usd INTEGER,
    tags TEXT,
    jd_text TEXT NOT NULL,
    apply_url TEXT NOT NULL,
    posted_at TEXT,
    fetched_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_posted_at ON jobs(posted_at);

CREATE TABLE IF NOT EXISTS scored (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    fit_score INTEGER NOT NULL,
    reasons TEXT,
    red_flags TEXT,
    llm_powered INTEGER NOT NULL,
    profile_snapshot TEXT,
    scored_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scored_job_id ON scored(job_id, scored_at DESC);

CREATE TABLE IF NOT EXISTS selected (
    job_id TEXT PRIMARY KEY REFERENCES jobs(id),
    status TEXT NOT NULL,
    cover_note TEXT,
    cover_note_generated_at TEXT,
    selected_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applied (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    status TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    notes TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_rate_limits (
    source TEXT PRIMARY KEY,
    window_start TEXT NOT NULL,
    window_seconds INTEGER NOT NULL,
    calls_made INTEGER NOT NULL DEFAULT 0,
    call_budget INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "agent-jobs" / "data" / "jobs.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_connection() -> sqlite3.Connection:
    db_path = os.environ.get("JOBS_DB_PATH", str(DEFAULT_DB_PATH))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def _row_to_summary(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "company": row["company"],
        "location": row["location"],
        "remote_type": row["remote_type"],
        "tags": json.loads(row["tags"]) if row["tags"] else [],
        "salary_min_usd": row["salary_min_usd"],
        "salary_max_usd": row["salary_max_usd"],
        "fit_score": row["fit_score"] if "fit_score" in row.keys() else None,
        "red_flags": json.loads(row["red_flags"]) if row["red_flags"] else [],
        "source": row["source"],
        "posted_at": row["posted_at"],
        "selected_status": row["selected_status"] if "selected_status" in row.keys() else None,
        "applied_status": row["applied_status"] if "applied_status" in row.keys() else None,
    }


def list_jobs(status: Optional[str] = None, min_fit_score: Optional[int] = None,
              source: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[dict]:
    conn = _get_connection()
    try:
        query = """
            SELECT j.*, s.fit_score, s.reasons, s.red_flags,
                   sel.status AS selected_status,
                   (SELECT status FROM applied WHERE job_id = j.id ORDER BY applied_at DESC LIMIT 1) AS applied_status
            FROM jobs j
            LEFT JOIN (
                SELECT job_id, fit_score, reasons, red_flags,
                       ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY scored_at DESC) rn
                FROM scored
            ) s ON s.job_id = j.id AND s.rn = 1
            LEFT JOIN selected sel ON sel.job_id = j.id
            WHERE 1=1
        """
        params: list = []
        if source:
            query += " AND j.source = ?"
            params.append(source)
        if min_fit_score is not None:
            query += " AND s.fit_score >= ?"
            params.append(min_fit_score)
        if status:
            query += " AND sel.status = ?"
            params.append(status)
        query += " ORDER BY j.posted_at DESC LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)

        rows = conn.execute(query, params).fetchall()
        return [_row_to_summary(row) for row in rows]
    finally:
        conn.close()


def get_job(job_id: str) -> Optional[dict]:
    conn = _get_connection()
    try:
        row = conn.execute(
            """
            SELECT j.*, s.fit_score, s.reasons, s.red_flags, s.llm_powered,
                   sel.status AS selected_status,
                   (SELECT status FROM applied WHERE job_id = j.id ORDER BY applied_at DESC LIMIT 1) AS applied_status
            FROM jobs j
            LEFT JOIN (
                SELECT job_id, fit_score, reasons, red_flags, llm_powered,
                       ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY scored_at DESC) rn
                FROM scored
            ) s ON s.job_id = j.id AND s.rn = 1
            LEFT JOIN selected sel ON sel.job_id = j.id
            WHERE j.id = ?
            """,
            (job_id,),
        ).fetchone()
        if not row:
            return None

        detail = _row_to_summary(row)
        detail["jd_text"] = row["jd_text"]
        detail["apply_url"] = row["apply_url"]
        detail["reasons"] = json.loads(row["reasons"]) if row["reasons"] else []
        detail["llm_powered"] = bool(row["llm_powered"]) if row["llm_powered"] is not None else False

        history_rows = conn.execute(
            "SELECT status, applied_at, notes FROM applied WHERE job_id = ? ORDER BY applied_at DESC",
            (job_id,),
        ).fetchall()
        detail["application_history"] = [dict(h) for h in history_rows]
        return detail
    finally:
        conn.close()


def mark_selected(job_id: str, status: str = "selected") -> None:
    conn = _get_connection()
    try:
        now = _now()
        conn.execute(
            """INSERT INTO selected (job_id, status, selected_at, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(job_id) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at""",
            (job_id, status, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def mark_applied(job_id: str, status: str = "applied", notes: str = "") -> None:
    conn = _get_connection()
    try:
        now = _now()
        conn.execute(
            "INSERT INTO applied (job_id, status, applied_at, notes, updated_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, status, now, notes, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_application_history(job_id: str) -> list[dict]:
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT status, applied_at, notes FROM applied WHERE job_id = ? ORDER BY applied_at DESC",
            (job_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
