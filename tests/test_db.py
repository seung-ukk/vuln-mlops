from modelgate.db import claim_next_job, enqueue_job, finish_job, get_job, init_db


def test_validation_job_lifecycle(tmp_path):
    db_path = str(tmp_path / "jobs.db")
    init_db(db_path)

    queued = enqueue_job(db_path, "fraud-detection", "1")
    assert queued["status"] == "queued"

    running = claim_next_job(db_path)
    assert running is not None
    assert running["id"] == queued["id"]
    assert running["status"] == "running"

    completed = finish_job(
        db_path,
        queued["id"],
        result={"implementation": "BenignModelWrapper"},
    )
    assert completed["status"] == "succeeded"
    assert completed["result"]["implementation"] == "BenignModelWrapper"
    assert get_job(db_path, queued["id"])["error"] is None


def test_only_one_worker_claims_a_job(tmp_path):
    db_path = str(tmp_path / "jobs.db")
    init_db(db_path)
    enqueue_job(db_path, "forecast", "3")

    assert claim_next_job(db_path) is not None
    assert claim_next_job(db_path) is None
