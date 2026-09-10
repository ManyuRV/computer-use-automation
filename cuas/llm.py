"""LLM provider seam for the discovery loop.

The agent loop depends only on `Provider.decide(observation) -> Action`.
Two implementations:
  - ScriptedProvider: a deterministic, hand-written policy for the local demo
    app. Lets the whole pipeline (loop, recording, replay, escalation) run and
    be tested with no model key. Clearly marked provenance.llm_driven=False.
  - OpenAIProvider / AnthropicProvider: thin real clients. The final
    submission's discovery run must use one of these with the user's own key.
"""
from __future__ import annotations
from typing import Optional, Protocol
from pydantic import BaseModel


class Observation(BaseModel):
    url: str
    aria: str                 # accessibility tree (YAML)
    goal: str
    history: list[str]        # prior decisions, compact
    stuck_count: int = 0


class Action(BaseModel):
    kind: str                 # navigate|click|fill|select|extract|done|fail|stuck
    role: Optional[str] = None
    name: Optional[str] = None        # accessible name of target
    text: Optional[str] = None        # visible-text target
    value: Optional[str] = None       # fill/select value
    url: Optional[str] = None
    extract_as: Optional[str] = None
    extract_mode: Optional[str] = None   # e.g. "adjacent_cell" for legacy label/value tables
    reason: str = ""


class Provider(Protocol):
    model_name: str
    def decide(self, obs: Observation) -> Action: ...


class ScriptedProvider:
    """Deterministic policy for the MemberServ demo app. NOT an LLM - it exists
    so the system end-to-end is runnable and testable offline. The real run
    swaps in a genuine model behind the same interface."""
    model_name = "scripted-offline-policy (NOT an LLM)"

    def __init__(self, member_id: str, entry_url: str):
        self.member_id = member_id
        self.entry_url = entry_url

    def decide(self, obs: Observation) -> Action:
        if obs.url.rstrip("/").endswith(":8377") or obs.url.endswith(":8377/"):
            if "Member Lookup" in obs.aria and self.member_id not in str(obs.history):
                return Action(kind="fill", role="textbox", name=None,
                              value=self.member_id, reason="enter member id into search box")
            if self.member_id in str(obs.history) and "Search" in obs.aria:
                return Action(kind="click", role="button", name="Search",
                              reason="submit the search")
        if "Member Detail" in obs.aria and "Savings Balance" in obs.aria:
            if "extract" not in str(obs.history):
                return Action(kind="extract", text="Savings Balance", extract_as="balance", extract_mode="adjacent_cell",
                              reason="read the savings balance from the detail table")
            return Action(kind="done", reason="balance captured")
        if "No member found" in obs.aria:
            return Action(kind="done", reason="member not found is a legitimate answer")
        if "System Notice" in obs.aria and "Dismiss" in obs.aria:
            return Action(kind="click", role="button", name="Dismiss",
                          reason="dismiss unexpected maintenance dialog")
        return Action(kind="navigate", url=self.entry_url, reason="go to entry point")
