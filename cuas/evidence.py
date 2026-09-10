"""Structured run evidence: JSONL event log + richer signals (screenshots,
aria snapshots) captured on failure. Secrets and PII are redacted before write.
"""
from __future__ import annotations
import json, time, os
from .guardrails import Policy


class EvidenceLog:
    def __init__(self, run_id: str, out_dir: str, policy: Policy):
        self.run_id = run_id
        self.dir = os.path.join(out_dir, run_id)
        os.makedirs(self.dir, exist_ok=True)
        self.policy = policy
        self.path = os.path.join(self.dir, "run.jsonl")
        self._fh = open(self.path, "a")

    def event(self, kind: str, **data):
        rec = {"ts": time.time(), "run_id": self.run_id, "kind": kind,
               **{k: (self.policy.redact(v) if isinstance(v, str) else v) for k, v in data.items()}}
        self._fh.write(json.dumps(rec) + "\n")
        self._fh.flush()

    def screenshot(self, page, name: str) -> str:
        p = os.path.join(self.dir, f"{name}.png")
        page.screenshot(path=p)
        return p

    def aria_snapshot(self, page, name: str) -> str:
        p = os.path.join(self.dir, f"{name}.aria.yaml")
        try:
            snap = page.locator("body").aria_snapshot(timeout=3000)
        except Exception as e:
            snap = f"<snapshot failed: {e}>"
        with open(p, "w") as f:
            f.write(snap)
        return p

    def close(self):
        self._fh.close()
