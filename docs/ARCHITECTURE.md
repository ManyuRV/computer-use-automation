# Architecture decision record (ADR) — Computer-Use Automation System prototype

Each decision lists the why and the trade-off, so every choice is defensible in review.

## ADR-1: Language/runtime — Python 3.10+, Playwright, pydantic, Flask
- Why: the candidate's day-job stack is Python; pydantic gives a typed, serializable,
  self-validating artifact schema for free; Playwright is the most maintained
  browser-automation library and exposes the accessibility tree; Flask is enough for the
  demo target and mock operator surface.
- Trade-off: no static typing discipline of TypeScript; mitigated by pydantic models at
  every boundary (artifact, result, action, observation).

## ADR-2: Perception = accessibility tree, not raw DOM, not pixels
- Why: the brief biases toward surfaces with no clean DOM. The a11y tree gives
  role + accessible name for every actionable element even in table-soup legacy markup,
  it is compact enough for LLM context, and the same abstraction exists on desktop
  (UIA on Windows, AX on macOS) — so the surface abstraction (ADR-6) is not web-only.
  Screenshots are kept as the richer failure signal, not the primary perception.
- Trade-off: some legacy elements have no accessible name (our demo's search textbox
  is a bare `textbox`). Handled by the locator chain (ADR-3) and by extraction modes
  (ADR-5) instead of pretending names always exist.

## ADR-3: Element targeting = robustness-ordered locator chain
- Every recorded step stores an ordered chain: role+name -> visible text -> structural
  CSS -> XPath. Discovery resolves the element once and records all candidates; replay
  tries them in order.
- Why: role+name survives layout restyling; text survives id churn; CSS/XPath are the
  last-resort structural pins. This directly answers "locator choice determines whether
  replay still works next month."
- Trade-off: chains are only as good as the recording; a future improvement is scoring
  chain links by observed stability across replays (ties into the stretch goal on
  replay-confidence scoring).

## ADR-4: The artifact is a typed capability contract, not a step dump
- Schema `cuas/1.0`: target app, typed inputs (with sensitivity flag), typed outputs,
  ordered steps with locator chains + values templated as {{inputs.x}}, per-step
  checkpoints, a final success condition, declared business outcomes, per-step error
  handlers, risky-action markers, provenance (run id, model, llm_driven flag).
- Why: Section 3.2 calls the schema a focal point. A calling AI agent needs the contract
  (what it does, what it needs, what it returns), and a human reviewer needs to read the
  JSON cold. Parameterization is done at compile time by rewriting concrete
  discovery-time values to {{inputs.x}} — simple, auditable, and it makes the recording
  a reusable capability instead of a macro.
- Trade-off: value-matching parameterization can over-match if a param value appears
  coincidentally; acceptable at this scale, documented as a known limit.

## ADR-5: Replay determinism = recorded targets + bounded waits + explicit taxonomy
- Replay never consults a model. Determinism comes from: fixed step order, locator
  chains, checkpoint verification after each step, and bounded backoff (1s/2s/4s) that
  absorbs transient slowness without hiding real failures.
- Result contract has exactly three outcomes: success (with outputs),
  business_outcome (a legitimate answer like member_not_found — never a crash), and
  failure (step, expected, observed, screenshot + aria snapshot). The brief names
  conflating business outcome with failure as "the most common design mistake."
- Extraction modes: for legacy label/value tables the artifact records
  extract_mode=adjacent_cell (read the cell after the label) rather than a brittle
  positional locator to the value cell — the value moves, the label doesn't.

## ADR-6: One surface seam, one concrete implementation
- `WebSurface` implements a small contract: observe_aria(), resolve(chain), act(),
  navigate(). Agent, recorder, and replay never touch Playwright types.
- Why: the brief asks for a credible path to legacy-web and desktop surfaces without
  building them. A desktop surface (UIA/AX tree + OS-level input) implements the same
  contract; artifact schema and replay engine are unchanged.
- Trade-off: the contract is minimal; coordinate-based fallback (screenshot+clicks)
  would extend act(), not replace it.

## ADR-7: Guardrails are a policy object consulted on every action
- Host allowlist, action allowlist, risky-action name patterns (Submit/Confirm/Delete/
  Transfer/Post) with block|confirm|flag handling, and regex redaction of SSNs, card
  numbers, and credential-like strings before any log or artifact write. Sensitive
  inputs are masked even in the replay-start log line.
- Why: regulated financial data; redaction must be at the evidence boundary, not
  per-call-site. Risky actions default toward confirmation, which reuses the escalation
  channel rather than inventing a second one.

## ADR-8: Control transfer = single-owner lease + session-owning executor
- A run has exactly one control owner. On stuck, the agent raises an intervention
  request (goal, step, reason, URL, screenshot), cedes the lease, and pauses. The
  human operates THE SAME live browser session through a mock console; human actions
  are enqueued and executed by the thread that owns the session (Playwright's sync API
  is thread-bound — learned the hard way in testing), recorded as evidence, and the
  agent resumes from the state the human left.
- Why: the brief's scope note wants a real handoff mechanism and control model with a
  mocked UI. The lease + queue design is also the shape a real co-browsing console
  would take (the queue becomes a websocket; the executor stays).
- Validated: session-expired fault -> escalation -> human navigates the live session
  home -> resume -> discovery completes and compiles the artifact; evidence trail shows
  intervention_raised / human_action / control_returned / resumed_after_human.

## ADR-9: Local legacy-style demo app as the target
- Flask, server-rendered, table layout, no ids, no test IDs, no semantic markup, with
  fault injection (slow load, unexpected dialog, session expiry) behind a control route.
- Why: no ToS risk, no credentials, fully offline/reproducible, and it exercises the
  exact runtime conditions the brief says matter (validation errors, not-found,
  dialogs, slowness, expiry) deterministically — which a public site cannot offer.
- Trade-off: it's not a "real" third-party site; justified because the brief explicitly
  allows "a local sample app you build" and the interesting evaluation is error
  handling, not the target's fame.

## ADR-10: LLM behind a Provider seam; real provider wired
- DONE: OpenAIProvider (gpt-4o-mini, temperature 0, JSON-mode one-action responses)
  implements the seam; per-call cost tracked from response usage against OpenAI's
  published price with a $2 warn / $5 hard stop. The scripted policy remains for
  offline testing. Real-run lessons that hardened the loop: feed extracted values back
  into the model's history, re-arm the human resume latch per intervention, and fall
  back from role+name to role-only targeting (accessible names are unreliable on
  legacy surfaces).
### Original note (pre-wiring)
- `Provider.decide(observation) -> Action` is the only model touch-point. A scripted
  offline policy stands in so the whole pipeline is testable with no key; real clients
  (OpenAI/Anthropic) slot behind the same interface with a JSON action schema.
- Why: it keeps the discovery loop honest (observation in, one action out) and makes
  the required real discovery run a config swap, not a rewrite. The artifact's
  provenance.llm_driven flag keeps the distinction honest in any intermediate demo.
