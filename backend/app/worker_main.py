"""Shadow-mode ingestion worker.

While PERSISTENT_INGESTION_SHADOW is enabled, the worker only leases jobs
and records stage transitions — it never invokes document processors.
"""

from __future__ import annotations

import argparse
import datetime
import os
import uuid


def _worker_id() -> str:
    return f"worker-{uuid.uuid4().hex[:8]}"


def run_once(db_session_factory) -> tuple[int, int]:
    """Lease and record one job (or none). Returns (job_id, exit_code)."""
    from app.application.ingestion.job_repository import MySQLJobRepository

    db = db_session_factory()
    try:
        repo = MySQLJobRepository(db)
        job = repo.lease_next(_worker_id())
        if job is None:
            return 0, 0
        try:
            repo.heartbeat(job.id, job.lease_owner or "", "shadow-processing", 0, job.total, 0)
            repo.succeed(job.id, job.lease_owner or "")
        except Exception:
            repo.fail(job.id, job.lease_owner or "", "worker_error")
        return job.id, 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="LocalRAG ingestion worker (shadow mode)")
    parser.add_argument("--once", action="store_true", help="process at most one job then exit")
    args = parser.parse_args()

    if os.environ.get("PERSISTENT_INGESTION_SHADOW", "false").lower() != "true":
        print("shadow mode disabled; worker exits without processing")
        return 0

    from app.main import SessionLocal

    job_id, code = run_once(SessionLocal)
    print(f"shadow worker processed job {job_id}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
