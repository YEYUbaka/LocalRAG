"""Worker recovery and shadow-mode tests."""

import pytest


def test_worker_once_exits_zero_with_no_jobs(monkeypatch):
    from app import worker_main

    class _EmptyRepo:
        def lease_next(self, worker_id):
            return None

    def _fake_factory(db):
        return _EmptyRepo()

    import app.application.ingestion.job_repository as jr
    monkeypatch.setattr(jr, "MySQLJobRepository", _fake_factory)
    monkeypatch.setenv("PERSISTENT_INGESTION_SHADOW", "true")

    class _Db:
        def close(self):
            pass

    class _Factory:
        def __call__(self):
            return _Db()

    job_id, code = worker_main.run_once(_Factory())
    assert job_id == 0
    assert code == 0


def test_worker_once_leases_and_succeeds(monkeypatch):
    from app import worker_main

    class _FakeRepo:
        def __init__(self):
            self.job = {"id": 7, "lease_owner": "worker-x", "status": "running"}
            self.succeeded = False

        def lease_next(self, worker_id):
            return type("Job", (), {"id": 7, "lease_owner": "worker-x", "total": 5})()

        def heartbeat(self, job_id, owner, stage, completed, total, percent, message=None):
            assert job_id == 7
            assert stage == "shadow-processing"

        def succeed(self, job_id, owner):
            self.succeeded = True

    repo = _FakeRepo()
    monkeypatch.setenv("PERSISTENT_INGESTION_SHADOW", "true")

    # run_once does `from ... import MySQLJobRepository` per call,
    # so patching the source module works
    import app.application.ingestion.job_repository as jr
    monkeypatch.setattr(jr, "MySQLJobRepository", lambda db: repo)

    class _Db:
        def close(self):
            pass

    class _Factory:
        def __call__(self):
            return _Db()

    job_id, code = worker_main.run_once(_Factory())
    assert job_id == 7
    assert code == 0
    assert repo.succeeded is True
