"""
SQLite persistent storage for AeroTriage.
Requires: data/ directory exists. DB path: ./data/aerotriage.db
"""
import sqlite3
import os
from datetime import datetime
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "aerotriage.db")


def _ensure_data_dir():
    data_dir = os.path.dirname(DB_PATH)
    os.makedirs(data_dir, exist_ok=True)


def _get_conn():
    _ensure_data_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they do not exist."""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symptoms TEXT NOT NULL,
                severity INTEGER NOT NULL,
                confidence REAL,
                arrival_time TEXT NOT NULL,
                status TEXT DEFAULT 'queued',
                flag_for_review INTEGER DEFAULT 0,
                mobile TEXT,
                completed_at TEXT,
                reasoning TEXT,
                rag_sources TEXT,
                voice_transcript TEXT
            )
        """)
        # Add columns if table existed without them
        for col, typ in [
            ("mobile", "TEXT"),
            ("name", "TEXT"),
            ("completed_at", "TEXT"),
            ("reasoning", "TEXT"),
            ("rag_sources", "TEXT"),
            ("voice_transcript", "TEXT"),
            ("consultation_duration_minutes", "REAL"),
            ("estimated_treatment_minutes", "REAL"),
        ]:
            try:
                conn.execute(f"ALTER TABLE patients ADD COLUMN {col} {typ}")
                conn.commit()
            except sqlite3.OperationalError:
                conn.rollback()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                patient_id INTEGER NOT NULL,
                priority REAL NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (patient_id),
                FOREIGN KEY (patient_id) REFERENCES patients(id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def insert_patient(
    symptoms: str,
    severity: int,
    confidence: Optional[float],
    arrival_time: Optional[str] = None,
    flag_for_review: bool = False,
    mobile: Optional[str] = None,
    name: Optional[str] = None,
    estimated_treatment_minutes: Optional[float] = None,
) -> int:
    """Insert a patient record. Returns patient id. estimated_treatment_minutes = RAG/symptom-based estimate shown to user (so admin queue uses same number)."""
    arrival_time = arrival_time or datetime.utcnow().isoformat() + "Z"
    conn = _get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO patients (symptoms, severity, confidence, arrival_time, status, flag_for_review, mobile, name, estimated_treatment_minutes)
            VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)
            """,
            (symptoms, severity, confidence, arrival_time, 1 if flag_for_review else 0, (mobile or "").strip() or None, (name or "").strip() or None, estimated_treatment_minutes if estimated_treatment_minutes is not None and estimated_treatment_minutes > 0 else None),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def insert_queue_entry(patient_id: int, priority: float) -> None:
    """Insert or replace queue entry for a patient."""
    created_at = datetime.utcnow().isoformat() + "Z"
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO queue (patient_id, priority, created_at)
            VALUES (?, ?, ?)
            """,
            (patient_id, priority, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_patient(patient_id: int) -> Optional[dict]:
    """Get patient by id. Returns dict or None."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def get_queue_from_sqlite() -> list:
    """Return queue entries with patient fields. Order is applied by caller (queue_api)."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT q.patient_id, q.priority, q.created_at, p.severity, p.arrival_time, p.mobile, p.name, p.reasoning, p.estimated_treatment_minutes
            FROM queue q
            JOIN patients p ON p.id = q.patient_id
            WHERE p.status = 'queued'
            ORDER BY q.priority DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def remove_from_queue(patient_id: int) -> bool:
    """Remove patient from queue table. Returns True if a row was deleted."""
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM queue WHERE patient_id = ?", (patient_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_patient_status(patient_id: int, status: str) -> None:
    """Update patient status (e.g. 'seen', 'completed')."""
    conn = _get_conn()
    try:
        conn.execute("UPDATE patients SET status = ? WHERE id = ?", (status, patient_id))
        conn.commit()
    finally:
        conn.close()


def mark_patient_completed(patient_id: int) -> None:
    """Set status to 'seen', completed_at to now, and store consultation_duration_minutes (arrival to completed)."""
    completed_at = datetime.utcnow().isoformat() + "Z"
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT arrival_time FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()
        duration_minutes = None
        if row and row["arrival_time"]:
            try:
                from datetime import timezone
                at_str = row["arrival_time"].replace("Z", "+00:00")
                arrival = datetime.fromisoformat(at_str)
                completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                if arrival.tzinfo is None:
                    arrival = arrival.replace(tzinfo=timezone.utc)
                if completed.tzinfo is None:
                    completed = completed.replace(tzinfo=timezone.utc)
                duration_minutes = round((completed - arrival).total_seconds() / 60.0, 1)
            except (ValueError, TypeError):
                pass
        if duration_minutes is not None:
            conn.execute(
                "UPDATE patients SET status = 'seen', completed_at = ?, consultation_duration_minutes = ? WHERE id = ?",
                (completed_at, duration_minutes, patient_id),
            )
        else:
            conn.execute(
                "UPDATE patients SET status = 'seen', completed_at = ? WHERE id = ?",
                (completed_at, patient_id),
            )
        conn.commit()
    finally:
        conn.close()


def update_patient_severity(patient_id: int, severity: int) -> None:
    """Update patient severity (for reclassify)."""
    conn = _get_conn()
    try:
        conn.execute("UPDATE patients SET severity = ? WHERE id = ?", (severity, patient_id))
        conn.commit()
    finally:
        conn.close()


def refresh_queue_priority(patient_id: int, severity: int) -> None:
    """Update queue entry priority for patient (e.g. after reclassify)."""
    priority = (6 - severity) + 0.05 * 0
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE queue SET priority = ? WHERE patient_id = ?",
            (priority, patient_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_patient_reasoning(
    patient_id: int,
    reasoning: Optional[str] = None,
    rag_sources: Optional[str] = None,
    voice_transcript: Optional[str] = None,
) -> None:
    """Store AI transparency data for admin (reasoning, RAG chunks, voice transcript)."""
    conn = _get_conn()
    try:
        conn.execute(
            """
            UPDATE patients SET reasoning = ?, rag_sources = ?, voice_transcript = ?
            WHERE id = ?
            """,
            (reasoning or "", rag_sources or "", voice_transcript or "", patient_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_avg_treatment_minutes_by_severity() -> dict:
    """
    From completed patients (status='seen', completed_at set), compute average time in queue
    (arrival to completed_at) in minutes, grouped by severity. Returns { severity: avg_minutes }.
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT severity,
                   AVG((julianday(completed_at) - julianday(arrival_time)) * 24 * 60) AS avg_minutes
            FROM patients
            WHERE status = 'seen' AND completed_at IS NOT NULL AND completed_at != ''
            GROUP BY severity
            """
        ).fetchall()
        return {int(r["severity"]): round(float(r["avg_minutes"]), 1) for r in rows}
    finally:
        conn.close()


def get_stats() -> dict:
    """Counts for admin stats: critical_handled, queue_count."""
    conn = _get_conn()
    try:
        critical = conn.execute(
            "SELECT COUNT(*) AS n FROM patients WHERE status = 'seen' AND severity IN (1, 2)"
        ).fetchone()["n"]
        queue_count = conn.execute(
            "SELECT COUNT(*) AS n FROM patients WHERE status = 'queued'"
        ).fetchone()["n"]
        return {"critical_cases_handled": critical or 0, "queue_count": queue_count or 0}
    finally:
        conn.close()


# Initialize tables on import
init_db()
