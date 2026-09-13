# Design report: Computer-Use Automation System

## 1. Architecture

Single-process Python system with five boundaries, each a small typed seam:

- **Surface** (`cuas/surface.py`): the only component that touches the UI. Perception is
  the page's **accessibility tree** (aria snapshot), not the raw DOM and not pixels.
  Actions are primitives (click/fill/select/extract/navigate) resolved through locator
  chains. Playwright types never escape this module.
- **Agent loop** (`cuas/agent.py`): observe -> decide -> act with stopping conditions
  (max steps, repeated-action dead-end, consecutive errors, explicit done/fail/stuck).
  It depends on a `Provider` interface, one method, observation in, one JSON action
  out, which is the only model touch-point in the system.
- **Recorder** (`cuas/recorder.py`): compiles a successful discovery trace into a
  versioned capability artifact, rewriting concrete run-time values into typed
  `{{inputs.x}}` parameters.
- **Replay engine** (`cuas/replay.py`): executes an artifact with no model in the loop,
  and owns the error taxonomy.
- **Guardrails** (`cuas/guardrails.py`): a policy object consulted on every navigation
  and action; all evidence writes pass through its redactor.

Why a single process: the brief rewards judgment over infrastructure. The seams are
drawn so each piece could become a service (the operator console already proves the
agent can pause and be driven externally), but building queues and clusters now would
be premature. The demo target is a local, deliberately-legacy Flask app (table layout,
no ids, no test IDs) with deterministic fault injection, chosen so ToS, credentials,
and reproducibility are non-issues, and because the runtime conditions that matter
(validation errors, not-found, dialogs, slowness, expiry) can be exercised exactly.

## 2. Artifact schema

The artifact (schema `cuas/1.0`, JSON, pydantic-validated) is a **capability contract**
rather than a step dump, because its consumer is an AI agent that must decide whether and how
to call it. It carries: the target app and entry point; typed **inputs** (with a
`sensitive` flag that keeps values out of logs); typed **outputs** bound to extract
steps; ordered **steps**, each with a robustness-ordered **locator chain**
(role+name -> visible text -> structural CSS -> XPath), per-step **checkpoints**, and
**risky** markers; a final **success condition**; declared **business outcomes**; and a
**provenance** block (run id, model, timestamp, `llm_driven` flag) so a recording can't
silently masquerade as LLM-discovered.

Parameterization happens at compile time: any step value or URL segment equal to a
declared input's discovery-time value is rewritten to `{{inputs.x}}`. It's simple, it's auditable, and a recording becomes a reusable capability instead of a macro. Known limit: value-matching can
over-match on coincidental strings; called out in Cuts.

## 3. Determinism & error handling

Replay never consults a model. Determinism comes from fixed step order, locator chains
with ordered fallbacks, checkpoint verification after each step, and **bounded backoff**
(1s/2s/4s) that absorbs transient slowness without hiding real failures.

Two robustness decisions I'm happy to defend:

- **Locator chains, not selectors.** Accessible names are unreliable on legacy surfaces
  (our demo's search box has none), so role+name falls back to role-only, then text,
  then structural pins. The chain is recorded once at discovery and tried in order at
  replay.
- **Extraction modes for legacy tables.** For label/value tables the artifact records
  `extract_mode=adjacent_cell`: read the cell after the label, because the value
  moves while the label doesn't. (The LLM chose this itself during the real discovery
  run, unprompted beyond a one-line schema hint.)

The result contract has exactly three statuses: `success` (with outputs),
`business_outcome` (a legitimate answer the caller needs; "no such member" is not a
crash), and `failure` (step, expected, observed, screenshot + aria snapshot). Business
outcomes are matched from the artifact's declared map before each step and after any
error. Validated: unknown member -> `business_outcome`; 6s injected slowness ->
success via backoff; injected session expiry -> structured `failure` with evidence.
Both real artifacts replay 5/5 identical.

## 4. Heterogeneity & multi-tenant

**Surfaces.** The surface contract is `observe_aria() / resolve(chain) / act() /
navigate()`. The accessibility tree exists on desktop (UIA on Windows, AX on macOS),
so a desktop surface implements the same contract with OS-level input; the artifact
schema and replay engine are unchanged. Coordinate-based control would extend `act()`,
not replace it. Only the web surface is built.

**Tenants.** The artifact separates the tenant-specific part (target `base_url`,
branding) from the flow (steps, locators, outcomes). Reuse across tenants running the
same vendor product = point the same artifact at a different `base_url`; per-tenant
specialization = override locator chain links without re-recording the flow. Drift
detection comes free with the design: a tenant whose UI drifted fails
checkpoints at replay, which gives you a signal (per-tenant replay health) instead of a silent
wrong answer. Route canonicalization (`/member/12345` -> `/member/:id`) is the same
`{{inputs.x}}` mechanism applied to URLs. Not built: the override-store and the
health dashboard; the schema leaves room for both.

## 5. Escalation & handoff

Stuck detection: repeated-action dead-end, consecutive action errors, provider
`stuck`/`fail`, policy stop, and risky-action confirmation. On any of these the agent
raises an **intervention request** (goal, step, reason, current URL, screenshot) and
pauses.

Control transfer is a **single-owner lease**: exactly one of agent or human controls
the session at a time. The human operates **the same live browser session** through a
mock operator console (live screenshot stream + action form). Because Playwright's
sync API is thread-bound, human actions are enqueued and executed by the
session-owning thread, recorded as evidence, and the agent resumes from the state the
human left. The lease is re-armed per intervention. This is deliberately the shape a
real co-browsing console would take: the queue becomes a websocket; the executor
stays. Validated end-to-end twice: an injected session-expiry during discovery (human
navigated the live session home; the run completed and compiled its artifact) and the
sub-account flow's risky submit (human confirmed through the console; the agent
clicked through to the confirmation screen).

## 6. Safety

- **Allowlists**: permitted hosts and action types, checked on every navigation and
  action; violations stop the run.
- **Risky actions**: accessible-name pattern matching (Submit/Confirm/Delete/Transfer/
  Post) with configurable handling: block, flag, or confirm via the escalation
  channel. Discovery defaults to confirm; the submitting click in the sub-account flow
  was human-confirmed this way.
- **Data handling**: SSNs, card/account numbers, and credential-like strings are
  redacted at the evidence boundary (one choke point, not per call site); inputs marked
  `sensitive` are masked even in run-start logs.
- **Limits**: the allowlist is host-level, not route-level; redaction is regex-based
  and will miss domain-specific PII shapes; a production deployment needs per-tenant
  policy storage and audit. The risky-name heuristic can false-positive on benign
  buttons named "Confirm". That's acceptable, since confirm only costs a human a click.

## 7. Cuts

- **Operator console is a mock UI** (per the brief's scope note); the control-transfer
  mechanism underneath is real. Next: websocket streaming + role-based operator auth.
- **No desktop surface**: designed (Section 4), not built. Next: a UIA-backed surface
  against a simple desktop app.
- **No multi-tenant store**: the base_url swap and override seam are designed; a
  second branded variant of the demo app would demonstrate it cheaply.
- **No assisted fallback on replay failure** (stretch goal): replay failure today
  routes to a human rather than a bounded LLM recovery, and that's the safer default for
  regulated data. I'd keep it behind a per-capability approval flag.
- **Parameterization by value-matching** can over-match; a typed-token approach
  (marking the param at record time via the model) is the next iteration.
- **No scaling infrastructure**: single process by design; the seams are the scaling
  story.
