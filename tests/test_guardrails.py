import pytest

from cuas.guardrails import Policy, PolicyViolation


def test_default_policy_allows_demo_host():
    Policy().check_url("http://localhost:8377/member/12345")


def test_policy_blocks_unlisted_host():
    with pytest.raises(PolicyViolation):
        Policy().check_url("https://example.com")


def test_policy_blocks_unknown_action():
    with pytest.raises(PolicyViolation):
        Policy().check_action("download")


def test_risky_action_names_are_detected_case_insensitively():
    policy = Policy()
    assert policy.is_risky("Submit Application")
    assert policy.is_risky("confirm transfer")
    assert not policy.is_risky("Search")


def test_redaction_covers_sensitive_values():
    policy = Policy()
    text = "ssn 123-45-6789 card 4242424242424242 password=hunter2"
    redacted = policy.redact(text)
    assert "123-45-6789" not in redacted
    assert "4242424242424242" not in redacted
    assert "hunter2" not in redacted
    assert redacted.count("[REDACTED]") == 3
