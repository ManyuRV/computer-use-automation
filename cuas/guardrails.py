"""Policy guardrails: what the agent may do, where, and what must never leak."""
from __future__ import annotations
import re
from urllib.parse import urlparse
from pydantic import BaseModel, Field


class Policy(BaseModel):
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost:8377", "127.0.0.1:8377"])
    allowed_actions: list[str] = Field(default_factory=lambda: [
        "navigate", "click", "fill", "select", "extract", "assert_text", "wait"])
    # Committing/irreversible actions are matched by the accessible name of the target.
    risky_name_patterns: list[str] = Field(default_factory=lambda: [
        r"(?i)submit", r"(?i)confirm", r"(?i)delete", r"(?i)transfer", r"(?i)post"])
    on_risky: str = "confirm"          # "block" | "confirm" (escalate) | "flag" (log only)
    redact_patterns: list[str] = Field(default_factory=lambda: [
        r"\b\d{3}-\d{2}-\d{4}\b",                       # SSN
        r"\b\d{12,19}\b",                                # card/account numbers
        r"(?i)(password|passwd|token|secret)\s*[:=]\s*\S+"])

    def check_url(self, url: str) -> None:
        host = urlparse(url).netloc
        if host not in self.allowed_hosts:
            raise PolicyViolation(f"URL host {host!r} not in allowlist {self.allowed_hosts}")

    def check_action(self, action: str) -> None:
        if action not in self.allowed_actions:
            raise PolicyViolation(f"action {action!r} not allowed by policy")

    def is_risky(self, accessible_name: str | None) -> bool:
        if not accessible_name:
            return False
        return any(re.search(p, accessible_name) for p in self.risky_name_patterns)

    def redact(self, text: str) -> str:
        for p in self.redact_patterns:
            text = re.sub(p, "[REDACTED]", text)
        return text


class PolicyViolation(Exception):
    pass
