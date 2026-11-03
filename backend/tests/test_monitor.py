from flowmind.monitor import check

DRY = {"trace": [{"id": "extract", "kind": "llm", "status": "ok", "output": {"vendor": "Acme", "amount": 10.0}}]}


def run(status="succeeded", ms=100, vendor="Acme"):
    return {
        "status": status,
        "error": "log: boom" if status == "failed" else None,
        "ms": ms,
        "trace": [{"id": "extract", "kind": "llm", "status": "ok", "output": {"vendor": vendor, "amount": 10.0}}],
    }


def test_failure_slow_and_drift():
    assert check(run("failed"), [], DRY) == [("error", "Run failed at log: boom")]
    history = [run(ms=100) for _ in range(6)]
    assert check(run(ms=100), history, DRY) == []
    assert check(run(ms=5000), history, DRY)[0][0] == "warning"
    assert "drift" in check(run(vendor=""), history, DRY)[0][1]
