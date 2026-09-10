"""Result contract for discovery and replay runs.

Three top-level statuses, deliberately distinct:
  success           - goal/capability completed; outputs attached
  business_outcome  - a legitimate answer the caller needs (e.g. 'no such member')
  failure           - the automation itself could not proceed; debuggable detail
"""
from __future__ import annotations
from typing import Optional, Literal, Any
from pydantic import BaseModel, Field


class FailureDetail(BaseModel):
    step_id: int
    expected: str
    observed: str
    evidence: list[str] = Field(default_factory=list)   # screenshot/snapshot paths


class BusinessOutcome(BaseModel):
    code: str
    detail: str = ""


class RunResult(BaseModel):
    status: Literal["success", "business_outcome", "failure", "escalated"]
    outputs: dict[str, Any] = Field(default_factory=dict)
    outcome: Optional[BusinessOutcome] = None
    failure: Optional[FailureDetail] = None
    steps_completed: int = 0
    run_id: str = ""
