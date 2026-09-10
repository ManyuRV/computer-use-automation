# Requirements checklist — interface.ai take-home (Assignment A)

Status: P = built and exercised in prototype / D = designed, implementation pending /
M = mocked at a real seam (per brief's scope note) / - = not started

## 3.1 Goal-driven agent loop
- [P] Accepts goal + target entry URL as input (`cli.py discover --goal ... --member-id ...`)
- [P] Observe -> decide -> act loop with stopping conditions (max steps, repeated-action
  dead-end, 3 consecutive errors, done/fail/stuck signals) — `cuas/agent.py`
- [P] Real interaction with a real UI: click, fill, select, extract, navigate via Playwright
  against Chrome — `cuas/surface.py`
- [P] Perception = accessibility tree (aria snapshot), the brief's preferred bias for
  no-clean-DOM surfaces; demo target is deliberately legacy (tables, no ids/test IDs)
- [P] GENUINE LLM-DRIVEN RUNS COMPLETE (2026-09-13): OpenAI gpt-4o-mini behind the
  Provider seam (`cuas/openai_provider.py`), JSON action schema, temperature 0. Two
  capabilities discovered for real: member balance lookup (cap-9bff61e6) and sub-account
  opening with human-confirmed risky submit (cap-02cb1fee). Both artifacts carry
  provenance.llm_driven=true and replay clean. Total OpenAI spend: $0.0078.

## 3.2 Structured artifact
- [P] Typed, serializable, versioned schema `cuas/1.0` (pydantic -> JSON) — `cuas/schema.py`
- [P] Ordered steps; robustness-ordered locator chains per step (role+name -> text -> css
  -> xpath), each with rationale in REPORT.md
- [P] Typed inputs (`InputParam`, incl. `sensitive` flag) with `{{inputs.x}}` templating
- [P] Typed outputs (`OutputSpec`, currency/string/number) bound to extract steps
- [P] Checkpoints per step + a final success condition
- [P] Declared business outcomes (e.g. member_not_found) as first-class schema members
- [P] Provenance block: run id, model, timestamp, and an HONEST `llm_driven` flag

## 3.3 Deterministic replay
- [P] No model in the loop — `cuas/replay.py` executes the artifact only
- [P] Stable targeting via recorded locator chain with ordered fallbacks
- [P] Checkpoint verification + bounded backoff (1s/2s/4s) absorbs transient slowness
  (validated: 6-second injected slow load still succeeds)
- [P] Explicit three-way taxonomy in the result contract: `success` / `business_outcome`
  (validated: unknown member) / `failure` with step, expected vs observed, screenshot +
  aria snapshot evidence (validated: session-expired injection)
- [P] Missing-input validation up front

## 3.4 Safety & policy guardrails
- [P] Configurable allowlist: permitted hosts + permitted action types, enforced on every
  navigation and action (validated: off-allowlist host blocked)
- [P] Risky/irreversible action detection by accessible-name pattern (Submit/Confirm/
  Delete/Transfer/Post) with configurable handling: block | confirm (escalate) | flag
  (validated: "Submit Application" flagged risky, "Search" not)
- [P] Redaction of SSNs, card/account numbers, and credential-like strings before
  anything hits logs or artifacts; `sensitive` inputs are never logged in clear
- [P] Risky-action handling wired into the discovery loop: block | confirm | flag.
  Exercised end-to-end: "Submit Application" -> intervention request -> operator
  confirms via console -> agent clicks through -> confirmation screen reached

## 3.5 Evidence / observability
- [P] Structured JSONL event log per run: decisions w/ reasons, actions, retries,
  extracts, errors — `cuas/evidence.py`, `evidence/<run_id>/run.jsonl`
- [P] Richer failure signal: screenshot + full aria snapshot captured on every failure
  and on intervention raise

## 3.6 Human-in-the-loop escalation & handoff
- [P] Stuck detection: repeated-action dead-end, consecutive errors, provider stuck/fail,
  policy violation, max steps
- [P] Intervention request carries goal, step, reason, current URL, screenshot —
  `intervention_request.json`
- [P] Control-transfer model: single-owner lease (agent|human); agent pauses, human
  takes the SAME live browser session (mock operator console on :8378 with live
  screenshot stream + action form), human actions are enqueued and executed by the
  session-owning thread, recorded to evidence, then control returns and the loop
  resumes from the human's end state (validated end-to-end: session-expired fault ->
  escalation -> human navigates home -> resume -> run completes and compiles artifact)
- [M] Operator UI is deliberately the mock the brief allows; the mechanism (lease,
  pause/cede/resume, action recording, live session) is real

## 3.7 Heterogeneity & scale (design only)
- [D] Surface abstraction seam exists in code (`WebSurface` behind a small
  observe/act contract); REPORT.md section 4 covers desktop (UIA/AX) extension and
  multi-tenant reuse (base_url swap + canonicalized routes + per-tenant locator
  overrides + drift detection via replay checkpoint failures)

## Deliverables (Section 6)
- [P] Working code + local demo app + CLI
- [-] README.md with setup + demo path (drafted in IMPLEMENTATION_PLAN.md)
- [-] REPORT.md with the seven required headings (outline + decision content drafted
  in ARCHITECTURE.md; needs final prose in Manyu's voice after the real LLM run)
- [P] /evidence/ with discovery + replay logs (5 replay scenarios + escalation run)
- [-] Public GitHub repo (BLOCKED: Manyu has no GitHub account; needs his signup +
  his push so the repo is under his identity)
- [-] Submission email to assignments@interface.ai (BLOCKED: not before his go/no-go)
