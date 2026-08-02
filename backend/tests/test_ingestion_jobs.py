"""Persistent ingestion job state machine and lease tests."""

import datetime

import pytest

from app.domain.task_progress import TaskProgress, TaskStatus
from app.application.ingestion.job_repository import LeaseLost


def test_task_progress_validates_counters():
    TaskProgress(id=1, kind="ingest", status=TaskStatus.QUEUED, stage="pending",
                 completed=0, total=10, percent=0, attempt=0, message=None, error_code=None)
    with pytest.raises(ValueError):
        TaskProgress(id=1, kind="ingest", status=TaskStatus.QUEUED, stage="pending",
                     completed=11, total=10, percent=0, attempt=0, message=None, error_code=None)
    with pytest.raises(ValueError):
        TaskProgress(id=1, kind="ingest", status=TaskStatus.QUEUED, stage="pending",
                     completed=0, total=10, percent=101, attempt=0, message=None, error_code=None)
    with pytest.raises(ValueError):
        TaskProgress(id=1, kind="ingest", status=TaskStatus.QUEUED, stage="pending",
                     completed=0, total=10, percent=0, attempt=-1, message=None, error_code=None)


def test_status_enum_values_frozen():
    assert TaskStatus.QUEUED.value == "queued"
    assert TaskStatus.RUNNING.value == "running"
    assert TaskStatus.SUCCEEDED.value == "succeeded"
    assert TaskStatus.FAILED.value == "failed"
    assert TaskStatus.CANCELLED.value == "cancelled"


class _FakeRepo:
    """In-memory double for MySQLJobRepository covering the state machine."""

    def __init__(self):
        self.jobs = {}
        self._next_id = 1
        self._now = datetime.datetime(2026, 8, 3, 12, 0, 0, tzinfo=datetime.timezone.utc)

    def enqueue(self, user_id, kb_id, kind, idempotency_key, document_id=None, payload=None):
        for job in self.jobs.values():
            if job["idempotency_key"] == idempotency_key:
                return None
        job = {
            "id": self._next_id, "user_id": user_id, "kb_id": kb_id,
            "document_id": document_id, "kind": kind, "status": "queued",
            "stage": "pending", "completed": 0, "total": None, "percent": None,
            "attempt": 0, "message": None, "error_code": None,
            "lease_owner": None, "idempotency_key": idempotency_key,
        }
        self._next_id += 1
        self.jobs[job["id"]] = job
        return job

    def lease_next(self, worker_id):
        for job in self.jobs.values():
            if job["status"] == "queued":
                job["status"] = "running"
                job["lease_owner"] = worker_id
                job["attempt"] += 1
                return job
        return None

    def heartbeat(self, job_id, lease_owner, stage, completed, total, percent, message=None):
        job = self.jobs.get(job_id)
        if not job or job["lease_owner"] != lease_owner:
            raise LeaseLost(f"lease lost for job {job_id}")
        job["stage"] = stage
        job["completed"] = completed
        job["percent"] = percent

    def succeed(self, job_id, lease_owner):
        job = self.jobs.get(job_id)
        if not job or job["lease_owner"] != lease_owner:
            raise LeaseLost(f"lease lost for job {job_id}")
        job["status"] = "succeeded"
        job["lease_owner"] = None

    def fail(self, job_id, lease_owner, error_code, message=None):
        job = self.jobs.get(job_id)
        if not job or job["lease_owner"] != lease_owner:
            raise LeaseLost(f"lease lost for job {job_id}")
        job["status"] = "failed"
        job["error_code"] = error_code
        job["lease_owner"] = None

    def cancel(self, job_id, user_id):
        job = self.jobs.get(job_id)
        if job and job["user_id"] == user_id and job["status"] in ("queued", "running"):
            job["status"] = "cancelled"
            job["lease_owner"] = None

    def retry(self, job_id, user_id):
        job = self.jobs.get(job_id)
        if job and job["user_id"] == user_id and job["status"] == "failed":
            job["status"] = "queued"
            job["error_code"] = None

    def recover_expired(self):
        count = 0
        for job in self.jobs.values():
            if job["status"] == "running":
                job["status"] = "queued"
                job["lease_owner"] = None
                count += 1
        return count


@pytest.fixture
def repo():
    return _FakeRepo()


def test_enqueue_creates_queued_job(repo):
    job = repo.enqueue(1, 1, "ingest", "ingest:1:1:2026-08-03T00:00:00", document_id=1)
    assert job["status"] == "queued"
    assert job["attempt"] == 0


def test_enqueue_idempotency_key_prevents_duplicates(repo):
    key = "ingest:1:1:2026-08-03T00:00:00"
    repo.enqueue(1, 1, "ingest", key, document_id=1)
    second = repo.enqueue(1, 1, "ingest", key, document_id=1)
    assert second is None


def test_lease_is_atomic_and_increments_attempt(repo):
    repo.enqueue(1, 1, "ingest", "k1", document_id=1)
    job = repo.lease_next("worker-a")
    assert job["status"] == "running"
    assert job["attempt"] == 1
    # Second worker cannot lease the same job
    assert repo.lease_next("worker-b") is None


def test_heartbeat_requires_matching_lease_owner(repo):
    job = repo.enqueue(1, 1, "ingest", "k1", document_id=1)
    leased = repo.lease_next("worker-a")
    repo.heartbeat(leased["id"], "worker-a", "parsing", 5, 10, 50)
    with pytest.raises(LeaseLost):
        repo.heartbeat(leased["id"], "worker-b", "parsing", 5, 10, 50)


def test_terminal_write_requires_matching_lease_owner(repo):
    job = repo.enqueue(1, 1, "ingest", "k1", document_id=1)
    leased = repo.lease_next("worker-a")
    repo.succeed(leased["id"], "worker-a")
    assert repo.jobs[leased["id"]]["status"] == "succeeded"
    # Succeeding again with a stale owner raises
    with pytest.raises(LeaseLost):
        repo.succeed(leased["id"], "worker-a")


def test_failed_can_retry_explicitly(repo):
    job = repo.enqueue(1, 1, "ingest", "k1", document_id=1)
    leased = repo.lease_next("worker-a")
    repo.fail(leased["id"], "worker-a", "parse_error")
    assert repo.jobs[leased["id"]]["status"] == "failed"
    repo.retry(leased["id"], 1)
    assert repo.jobs[leased["id"]]["status"] == "queued"


def test_cancel_from_queued_and_running(repo):
    queued = repo.enqueue(1, 1, "ingest", "k1", document_id=1)
    repo.cancel(queued["id"], 1)
    assert repo.jobs[queued["id"]]["status"] == "cancelled"

    running = repo.enqueue(1, 1, "ingest", "k2", document_id=2)
    repo.lease_next("worker-a")
    repo.cancel(running["id"], 1)
    assert repo.jobs[running["id"]]["status"] == "cancelled"


def test_recover_expired_running_to_queued(repo):
    job = repo.enqueue(1, 1, "ingest", "k1", document_id=1)
    repo.lease_next("worker-a")
    assert repo.recover_expired() == 1
    assert repo.jobs[job["id"]]["status"] == "queued"


def test_cross_user_cancel_is_noop(repo):
    job = repo.enqueue(1, 1, "ingest", "k1", document_id=1)
    repo.cancel(job["id"], 2)
    assert repo.jobs[job["id"]]["status"] == "queued"
