# Implementation plan — prototype -> submission

## Already built and validated (this workspace, private)
- cuas/ package: schema, surface, guardrails, evidence, escalation, agent, recorder,
  replay, results; local legacy demo app with fault injection; discover/replay CLI
- Evidence: 1 discovery run, 5 replay scenarios, 1 full escalation/handoff run
  (see docs/VALIDATION_PLAN.md)

## Remaining, in order
1. (BLOCKER, needs Manyu) GitHub account signup — ~2 min, must be his account since the
   repo ships under his identity. Then: private repo first, flip public at submission.
2. (BLOCKER, needs Manyu) Model API key — his key (OpenAI or Anthropic), kept out of the
   repo via env var. Cost of 1-3 discovery runs: well under $1.
3. Real LLM provider: OpenAIProvider/AnthropicProvider implementing Provider.decide()
   - Prompt: goal + policy summary + compact history + aria YAML; response constrained
     to the Action JSON schema (navigate/click/fill/select/extract/done/fail/stuck).
   - Run 1-3 genuine discovery runs against the demo app (and optionally a public
     sandbox like a demo shopping site for variety), keep run.jsonl + artifact as
     /evidence/.
4. Second capability (proves generality + risky-action path): "open a sub-account and
   reach the confirmation screen" — exercises select, the risky Submit Application
   action (confirm via escalation), validation-error business outcome, and a
   confirmation checkpoint.
5. REPORT.md in the seven required headings — content already decided in
   docs/ARCHITECTURE.md; write final prose after the real runs so it cites real
   evidence. ~1-3 pages.
6. README.md — setup (pip install, start demo app), demo path (one discover command,
   one replay command), config (env var for the model key).
7. Agent-facing capability catalog (stretch goal, if time): list artifacts as callable
   capabilities with typed args — cheap now that the artifact is a real contract.
8. Manyu review pass: he walks every file, we drill him on ADR-2/3/4/5/8 (the focal
   points) until he can defend them cold. Brief: "you own everything you submit."
9. Push to his public repo, email link to assignments@interface.ai from the address he
   applied with. (Never before his explicit go.)

## Deliberate cuts to declare in REPORT.md (Section 7)
- Operator console is a mock UI (real lease/queue mechanism) — per brief's scope note.
- Desktop surface: designed (ADR-6), not built.
- Multi-tenant: designed (base_url swap + canonical routes + per-tenant overrides),
  not built; optionally demonstrated via a second branded variant of the demo app
  (stretch: canonicalization).
- No queues/services/multi-process infra — single process, justified by the brief's
  "we do not reward scaling infrastructure."
