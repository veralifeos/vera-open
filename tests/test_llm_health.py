"""Testes do circuit breaker do LLM."""

from vera import llm_health


def test_fresh_state_circuit_closed(tmp_path):
    path = tmp_path / "llm_health.json"
    assert not llm_health.is_circuit_open(path=path)


def test_single_failure_does_not_open_circuit(tmp_path):
    path = tmp_path / "llm_health.json"
    llm_health.record_failure("test error", path=path)
    assert not llm_health.is_circuit_open(threshold=3, path=path)


def test_three_failures_opens_circuit(tmp_path):
    path = tmp_path / "llm_health.json"
    for _ in range(3):
        llm_health.record_failure("boom", path=path)
    assert llm_health.is_circuit_open(threshold=3, path=path)


def test_success_resets_counter(tmp_path):
    path = tmp_path / "llm_health.json"
    llm_health.record_failure("fail 1", path=path)
    llm_health.record_failure("fail 2", path=path)
    llm_health.record_success(path=path)
    assert not llm_health.is_circuit_open(threshold=3, path=path)
    status = llm_health.get_status(path=path)
    assert status["consecutive_failures"] == 0
    assert status["last_success"] is not None


def test_humanized_message_detects_credit_error():
    msg = llm_health.humanized_offline_message(
        "Error code: 400 credit balance is too low"
    )
    assert "saldo da Anthropic" in msg
    assert "stacktrace" not in msg.lower()


def test_humanized_message_detects_rate_limit():
    msg = llm_health.humanized_offline_message("Rate limit exceeded")
    assert "Rate limit" in msg


def test_humanized_message_detects_auth():
    msg = llm_health.humanized_offline_message("401 unauthorized: invalid api key")
    assert "API key" in msg


def test_humanized_message_generic_fallback():
    msg = llm_health.humanized_offline_message("some weird error")
    assert "silencio" in msg.lower()
    assert "Me chama" in msg


def test_humanized_message_handles_none():
    msg = llm_health.humanized_offline_message(None)
    assert "Vera em silencio" in msg


def test_error_truncated_to_200_chars(tmp_path):
    path = tmp_path / "llm_health.json"
    huge = "x" * 500
    llm_health.record_failure(huge, path=path)
    status = llm_health.get_status(path=path)
    assert len(status["last_failure_error"]) == 200


def test_corrupt_file_returns_default(tmp_path):
    path = tmp_path / "llm_health.json"
    path.write_text("not-json{", encoding="utf-8")
    status = llm_health.get_status(path=path)
    assert status["consecutive_failures"] == 0
