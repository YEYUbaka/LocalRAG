"""Persistent ingestion job repository.

Atomic lease acquisition via SELECT ... FOR UPDATE SKIP LOCKED; terminal
writes require a matching lease owner. All operations are tenant-scoped.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.task_progress import TaskStatus

LEASE_SECONDS = 60


@dataclass(frozen=True)
class JobRow:
    id: int
    user_id: int
    kb_id: int
    document_id: int | None
    kind: str
    status: TaskStatus
    stage: str
    completed: int
    total: int | None
    percent: int | None
    attempt: int
    message: str | None
    error_code: str | None
    lease_owner: str | None
    idempotency_key: str


class LeaseLost(Exception):
    """Raised when a worker's lease no longer matches the row."""


class MySQLJobRepository:
    def __init__(self, db: Session):
        self._db = db

    def enqueue(
        self,
        user_id: int,
        kb_id: int,
        kind: str,
        idempotency_key: str,
        document_id: int | None = None,
        payload: dict | None = None,
    ) -> JobRow | None:
        """Insert a job unless the idempotency key already exists."""
        existing = self._db.execute(
            text("SELECT id FROM ingestion_jobs WHERE idempotency_key = :key"),
            {"key": idempotency_key},
        ).first()
        if existing:
            return None
        result = self._db.execute(
            text(
                """
                INSERT INTO ingestion_jobs
                    (user_id, kb_id, document_id, kind, status, stage, completed,
                     total, percent, attempt, message, idempotency_key, payload,
                     created_at, updated_at)
                VALUES
                    (:user_id, :kb_id, :document_id, :kind, 'queued', 'pending', 0,
                     NULL, NULL, 0, NULL, :key, :payload, NOW(), NOW())
                """
            ),
            {
                "user_id": user_id,
                "kb_id": kb_id,
                "document_id": document_id,
                "kind": kind,
                "key": idempotency_key,
                "payload": payload,
            },
        )
        self._db.commit()
        return self.get(result.lastrowid)

    def get(self, job_id: int) -> JobRow | None:
        row = self._db.execute(
            text(
                """
                SELECT id, user_id, kb_id, document_id, kind, status, stage,
                       completed, total, percent, attempt, message, error_code,
                       lease_owner, idempotency_key
                FROM ingestion_jobs WHERE id = :id
                """
            ),
            {"id": job_id},
        ).first()
        if row is None:
            return None
        return self._to_row(row)

    def lease_next(self, worker_id: str, now: datetime.datetime | None = None) -> JobRow | None:
        """Atomically lease the oldest queued job; returns None if none."""
        now = now or datetime.datetime.now(datetime.timezone.utc)
        lease_until = now + datetime.timedelta(seconds=LEASE_SECONDS)
        row = self._db.execute(
            text(
                """
                SELECT id FROM ingestion_jobs
                WHERE status = 'queued'
                ORDER BY id ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            ),
        ).first()
        if row is None:
            return None
        self._db.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET status = 'running', lease_owner = :owner, lease_until = :until,
                    attempt = attempt + 1, updated_at = NOW()
                WHERE id = :id
                """
            ),
            {"owner": worker_id, "until": lease_until, "id": row.id},
        )
        self._db.commit()
        return self.get(row.id)

    def heartbeat(self, job_id: int, lease_owner: str, stage: str, completed: int, total: int | None, percent: int | None, message: str | None = None) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        lease_until = now + datetime.timedelta(seconds=LEASE_SECONDS)
        result = self._db.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET stage = :stage, completed = :completed, total = :total,
                    percent = :percent, message = :message,
                    lease_until = :until, updated_at = NOW()
                WHERE id = :id AND lease_owner = :owner
                """
            ),
            {
                "id": job_id,
                "owner": lease_owner,
                "stage": stage,
                "completed": completed,
                "total": total,
                "percent": percent,
                "message": message,
                "until": lease_until,
            },
        )
        self._db.commit()
        if result.rowcount == 0:
            raise LeaseLost(f"lease lost for job {job_id}")

    def succeed(self, job_id: int, lease_owner: str) -> None:
        self._terminal(job_id, lease_owner, TaskStatus.SUCCEEDED)

    def fail(self, job_id: int, lease_owner: str, error_code: str, message: str | None = None) -> None:
        result = self._db.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET status = :status, error_code = :error_code, message = :message,
                    lease_owner = NULL, lease_until = NULL, updated_at = NOW()
                WHERE id = :id AND lease_owner = :owner
                """
            ),
            {
                "status": TaskStatus.FAILED.value,
                "error_code": error_code,
                "message": message,
                "id": job_id,
                "owner": lease_owner,
            },
        )
        self._db.commit()
        if result.rowcount == 0:
            raise LeaseLost(f"lease lost for job {job_id}")

    def cancel(self, job_id: int, user_id: int) -> None:
        self._db.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET status = 'cancelled', lease_owner = NULL, lease_until = NULL,
                    updated_at = NOW()
                WHERE id = :id AND user_id = :user_id AND status IN ('queued', 'running')
                """
            ),
            {"id": job_id, "user_id": user_id},
        )
        self._db.commit()

    def retry(self, job_id: int, user_id: int) -> None:
        """Explicit retry from failed back to queued."""
        self._db.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET status = 'queued', error_code = NULL, message = NULL,
                    lease_owner = NULL, lease_until = NULL, updated_at = NOW()
                WHERE id = :id AND user_id = :user_id AND status = 'failed'
                """
            ),
            {"id": job_id, "user_id": user_id},
        )
        self._db.commit()

    def recover_expired(self, now: datetime.datetime | None = None) -> int:
        """Move expired running jobs back to queued; returns count recovered."""
        now = now or datetime.datetime.now(datetime.timezone.utc)
        result = self._db.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET status = 'queued', lease_owner = NULL, lease_until = NULL,
                    updated_at = NOW()
                WHERE status = 'running' AND lease_until < :now
                """
            ),
            {"now": now},
        )
        self._db.commit()
        return result.rowcount

    def list_for_user(self, user_id: int, limit: int = 50) -> list[JobRow]:
        rows = self._db.execute(
            text(
                """
                SELECT id, user_id, kb_id, document_id, kind, status, stage,
                       completed, total, percent, attempt, message, error_code,
                       lease_owner, idempotency_key
                FROM ingestion_jobs
                WHERE user_id = :user_id
                ORDER BY id DESC
                LIMIT :limit
                """
            ),
            {"user_id": user_id, "limit": limit},
        ).all()
        return [self._to_row(r) for r in rows]

    @staticmethod
    def _to_row(row) -> JobRow:
        return JobRow(
            id=row.id,
            user_id=row.user_id,
            kb_id=row.kb_id,
            document_id=row.document_id,
            kind=row.kind,
            status=TaskStatus(row.status),
            stage=row.stage,
            completed=row.completed,
            total=row.total,
            percent=row.percent,
            attempt=row.attempt,
            message=row.message,
            error_code=row.error_code,
            lease_owner=row.lease_owner,
            idempotency_key=row.idempotency_key,
        )

    def _terminal(self, job_id: int, lease_owner: str, status: TaskStatus) -> None:
        result = self._db.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET status = :status, lease_owner = NULL, lease_until = NULL,
                    updated_at = NOW()
                WHERE id = :id AND lease_owner = :owner
                """
            ),
            {"status": status.value, "id": job_id, "owner": lease_owner},
        )
        self._db.commit()
        if result.rowcount == 0:
            raise LeaseLost(f"lease lost for job {job_id}")
