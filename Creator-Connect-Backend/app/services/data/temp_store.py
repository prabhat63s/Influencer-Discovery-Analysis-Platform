"""
Temporary Session Storage Helper

Manages 12-hour lifecycle JSON storage for dynamic search sessions.
Replaces CSV-based persistence with JSON for temporary session data.

Features:
- Store session data as JSON with timestamp
- Auto-cleanup of expired sessions (>12 hours)
- Centralized path management
- Atomic file operations
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Storage paths
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
STORAGE_DIR = _PROJECT_ROOT / "storage"
SESSIONS_DIR = STORAGE_DIR / "sessions"
REPORTS_DIR = STORAGE_DIR / "reports"

# Ensure directories exist
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def get_session_path(conversation_id: str) -> Path:
    """
    Get the JSON file path for a session.

    Args:
        conversation_id: Unique identifier for the conversation/session

    Returns:
        Path object pointing to the session JSON file
    """
    return SESSIONS_DIR / f"{conversation_id}.json"


def get_report_path(conversation_id: str, influencer_id: str) -> Path:
    """
    Get the PDF report path for a session + influencer.

    Args:
        conversation_id: Unique identifier for the conversation/session
        influencer_id: Unique identifier for the influencer

    Returns:
        Path object pointing to the PDF report file
    """
    return REPORTS_DIR / f"{conversation_id}_{influencer_id}.pdf"


def persist_session(conversation_id: str, payload: Dict[str, Any]) -> bool:
    """
    Write session data to JSON with timestamp.

    Args:
        conversation_id: Unique identifier for the conversation/session
        payload: Session data to persist (list of influencers, metrics, etc.)

    Returns:
        True if successful, False otherwise
    """
    try:
        session_path = get_session_path(conversation_id)

        # Add metadata
        session_data = {
            "conversation_id": conversation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().timestamp(),
            "expires_at": (datetime.utcnow() + timedelta(hours=12)).timestamp(),
            "data": payload
        }

        # Atomic write: write to temp file, then rename
        temp_path = session_path.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)

        temp_path.replace(session_path)

        logger.info(f"✅ Persisted session: {conversation_id}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to persist session {conversation_id}: {e}")
        return False


def load_session(conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Load session data from JSON.

    Args:
        conversation_id: Unique identifier for the conversation/session

    Returns:
        Session data dict if found and valid, None otherwise
    """
    try:
        session_path = get_session_path(conversation_id)

        if not session_path.exists():
            logger.debug(f"Session not found: {conversation_id}")
            return None

        with open(session_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)

        # Check if expired
        expires_at = session_data.get("expires_at")
        if expires_at and datetime.utcnow().timestamp() > expires_at:
            logger.warning(f"Session expired: {conversation_id}")
            delete_session(conversation_id)
            return None

        logger.debug(f"✅ Loaded session: {conversation_id}")
        return session_data.get("data")

    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON in session {conversation_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Failed to load session {conversation_id}: {e}")
        return None


def delete_session(conversation_id: str, delete_reports: bool = True) -> bool:
    """
    Delete session JSON and optionally associated PDF reports.

    Args:
        conversation_id: Unique identifier for the conversation/session
        delete_reports: If True, also delete all PDF reports for this session

    Returns:
        True if successful, False otherwise
    """
    try:
        session_path = get_session_path(conversation_id)
        deleted_count = 0

        # Delete session JSON
        if session_path.exists():
            session_path.unlink()
            deleted_count += 1
            logger.debug(f"🗑️  Deleted session JSON: {conversation_id}")

        # Delete associated reports
        if delete_reports:
            pattern = f"{conversation_id}_*.pdf"
            for report_file in REPORTS_DIR.glob(pattern):
                report_file.unlink()
                deleted_count += 1
                logger.debug(f"🗑️  Deleted report: {report_file.name}")

        if deleted_count > 0:
            logger.info(f"✅ Deleted session {conversation_id}: {deleted_count} files")

        return True

    except Exception as e:
        logger.error(f"❌ Failed to delete session {conversation_id}: {e}")
        return False


def cleanup_expired(threshold_hours: int = 12) -> Dict[str, int]:
    """
    Delete sessions and reports older than threshold.

    Args:
        threshold_hours: Delete files older than this many hours (default: 12)

    Returns:
        Dict with cleanup statistics: {"sessions": count, "reports": count}
    """
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=threshold_hours)
        cutoff_timestamp = cutoff_time.timestamp()

        stats = {"sessions": 0, "reports": 0}

        # Clean up expired sessions
        for session_file in SESSIONS_DIR.glob("*.json"):
            try:
                # Try to read expiration from JSON
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)

                expires_at = session_data.get("expires_at")

                # Check expiration (from JSON or file mtime)
                if expires_at and datetime.utcnow().timestamp() > expires_at:
                    conversation_id = session_data.get("conversation_id") or session_file.stem
                    delete_session(conversation_id, delete_reports=True)
                    stats["sessions"] += 1
                elif not expires_at:
                    # Fallback: check file modification time
                    file_mtime = session_file.stat().st_mtime
                    if file_mtime < cutoff_timestamp:
                        conversation_id = session_file.stem
                        delete_session(conversation_id, delete_reports=True)
                        stats["sessions"] += 1

            except Exception as e:
                logger.warning(f"⚠️  Failed to process session file {session_file.name}: {e}")
                continue

        # Clean up orphaned reports (reports without session JSON)
        session_ids = {f.stem for f in SESSIONS_DIR.glob("*.json")}

        for report_file in REPORTS_DIR.glob("*.pdf"):
            try:
                # Extract conversation_id from filename (format: conversation_id_influencer_id.pdf)
                name_parts = report_file.stem.split("_")
                if len(name_parts) >= 2:
                    conversation_id = "_".join(name_parts[:-1])

                    # Delete if session doesn't exist
                    if conversation_id not in session_ids:
                        report_file.unlink()
                        stats["reports"] += 1
                        logger.debug(f"🗑️  Deleted orphaned report: {report_file.name}")

            except Exception as e:
                logger.warning(f"⚠️  Failed to process report file {report_file.name}: {e}")
                continue

        if stats["sessions"] > 0 or stats["reports"] > 0:
            logger.info(f"🧹 Cleanup complete: {stats['sessions']} sessions, {stats['reports']} reports deleted")
        else:
            logger.debug("✅ No expired sessions to clean up")

        return stats

    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}")
        return {"sessions": 0, "reports": 0}


def list_sessions(include_expired: bool = False) -> List[Dict[str, Any]]:
    """
    List all active sessions.

    Args:
        include_expired: If True, include expired sessions in the list

    Returns:
        List of session metadata dicts
    """
    sessions = []

    try:
        for session_file in SESSIONS_DIR.glob("*.json"):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)

                expires_at = session_data.get("expires_at")
                is_expired = expires_at and datetime.utcnow().timestamp() > expires_at

                if not is_expired or include_expired:
                    sessions.append({
                        "conversation_id": session_data.get("conversation_id") or session_file.stem,
                        "created_at": session_data.get("created_at"),
                        "expires_at": session_data.get("expires_at"),
                        "is_expired": is_expired,
                        "file_path": str(session_file)
                    })

            except Exception as e:
                logger.warning(f"⚠️  Failed to read session {session_file.name}: {e}")
                continue

        logger.debug(f"📋 Found {len(sessions)} sessions")
        return sessions

    except Exception as e:
        logger.error(f"❌ Failed to list sessions: {e}")
        return []


def get_session_stats() -> Dict[str, Any]:
    """
    Get statistics about stored sessions.

    Returns:
        Dict with stats: total_sessions, total_reports, total_size_mb, etc.
    """
    try:
        sessions = list(SESSIONS_DIR.glob("*.json"))
        reports = list(REPORTS_DIR.glob("*.pdf"))

        total_size = sum(f.stat().st_size for f in sessions) + sum(f.stat().st_size for f in reports)

        return {
            "total_sessions": len(sessions),
            "total_reports": len(reports),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "sessions_dir": str(SESSIONS_DIR),
            "reports_dir": str(REPORTS_DIR)
        }

    except Exception as e:
        logger.error(f"❌ Failed to get stats: {e}")
        return {"error": str(e)}
