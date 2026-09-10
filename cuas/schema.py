"""Capability artifact schema (cuas/1.0).

The artifact is the contract between an AI agent (caller) and the replay
engine: typed inputs, typed outputs, ordered steps with robust locator
chains, per-step checkpoints, declared business outcomes, and error handling.
Versioned and human-reviewable (plain JSON).
"""
from __future__ import annotations
from typing import Literal, Optional, Any
from pydantic import BaseModel, Field

SCHEMA_VERSION = "cuas/1.0"

ActionType = Literal["navigate", "click", "fill", "select", "extract", "assert_text", "wait"]
LocatorStrategy = Literal["role", "text", "css", "xpath"]


class Locator(BaseModel):
    strategy: LocatorStrategy
    value: str                       # css path / xpath / visible text
    role: Optional[str] = None       # for strategy=role
    name: Optional[str] = None       # accessible name for strategy=role

    def describe(self) -> str:
        if self.strategy == "role":
            return f"role={self.role} name={self.name!r}"
        return f"{self.strategy}={self.value!r}"


class Checkpoint(BaseModel):
    """Asserted after a step (and as the final success condition)."""
    type: Literal["url_contains", "text_present", "locator_present"]
    value: str = ""                  # url fragment / expected text
    locator: Optional[Locator] = None


class ErrorMatch(BaseModel):
    text: Optional[str] = None       # page contains this text
    status: Optional[int] = None     # HTTP status of last response


class ErrorHandler(BaseModel):
    """What a matched runtime condition means."""
    match: ErrorMatch
    kind: Literal["business_outcome", "recover", "fail"]
    outcome_code: Optional[str] = None       # for business_outcome
    recover_action: Optional[ActionType] = None  # e.g. dismiss_dialog, wait+retry
    message: str = ""


class InputParam(BaseModel):
    name: str
    type: Literal["string", "number"] = "string"
    required: bool = True
    description: str = ""
    sensitive: bool = False          # never logged / persisted in clear


class OutputSpec(BaseModel):
    name: str
    type: Literal["string", "number", "currency"] = "string"
    description: str = ""


class Step(BaseModel):
    id: int
    action: ActionType
    locators: list[Locator] = Field(default_factory=list)   # ordered fallback chain
    value: Optional[str] = None        # fill/select text; may contain {{inputs.x}}
    url: Optional[str] = None          # navigate target; may contain {{inputs.x}}
    extract_as: Optional[str] = None   # output name for extract steps
    extract_mode: Optional[str] = None  # how to read the value (default: element text)
    checkpoint: Optional[Checkpoint] = None
    on_error: list[ErrorHandler] = Field(default_factory=list)
    risky: bool = False                # irreversible/committing action
    note: str = ""


class Target(BaseModel):
    app: str
    base_url: str
    entry_route: str = "/"


class Provenance(BaseModel):
    run_id: str
    recorded_at: str
    model: str
    llm_driven: bool                   # True only for a genuine LLM discovery run


class CapabilityArtifact(BaseModel):
    schema_version: str = SCHEMA_VERSION
    id: str
    name: str
    description: str = ""
    target: Target
    inputs: list[InputParam] = Field(default_factory=list)
    outputs: list[OutputSpec] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    success: Checkpoint
    business_outcomes: dict[str, ErrorMatch] = Field(default_factory=dict)
    provenance: Optional[Provenance] = None

    def render_template(self, s: str, params: dict[str, Any]) -> str:
        for k, v in params.items():
            s = s.replace("{{inputs." + k + "}}", str(v))
        return s
