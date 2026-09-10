# Validation plan — what was exercised, results, and what remains

## Validated in this prototype (all runs reproducible)

| # | Scenario | How to reproduce | Result |
|---|----------|------------------|--------|
| 1 | Discovery (offline policy) | `python3 cli.py discover --goal "..." --member-id 12345` | artifact compiled, balance $4,812.07 |
| 2 | Replay happy path | `python3 cli.py replay --artifact artifacts/<cap>.json --params member_id=12345` | success, balance output |
| 3 | Replay parameterization | same, `member_id=67890` | success, $19,203.55 (proves {{inputs.x}} templating) |
| 4 | Business outcome | same, `member_id=99999` | status=business_outcome member_not_found (not a failure) |
| 5 | Recoverable condition | fault=slow (6s delay), replay 12345 | success via bounded backoff; step_retry events in log |
| 6 | Hard failure | fault=expired, replay 12345 | status=failure, step 1, expected vs observed, screenshot + aria snapshot saved |
| 7 | Escalation & handoff | fault=expired, discover; human acts via :8378 console; resume | intervention request -> human drives SAME live session -> control returned -> run completes, artifact compiled; full evidence trail in run.jsonl |
| 8 | Guardrails | unit checks | off-allowlist host blocked; "Submit Application" flagged risky / "Search" not; SSN/card/password redacted in logs |

Fault injection is deterministic via the demo app's control route:
`curl "http://localhost:8377/_control/fault?mode=slow|dialog|expired|"`.

## Evidence layout
- `artifacts/cap-*.json` — compiled capability artifacts (schema cuas/1.0)
- `evidence/<run_id>/run.jsonl` — structured decision/action/error log
- `evidence/<run_id>/*.png`, `*.aria.yaml` — failure/intervention captures
- `evidence/<run_id>/intervention_request.json` — escalation payload

## Real LLM-run results (2026-09-13, openai/gpt-4o-mini, temp 0)
- Member lookup discovery: the model filled search, clicked Search, and read the
  balance via role=cell + adjacent_cell (its own choice). Artifact cap-9bff61e6
  replays clean across the full matrix above (scenarios 2-6). Evidence:
  evidence/disc-f5bef8bc.
- Sub-account discovery: search -> open-subaccount -> select Savings -> fill deposit
  -> Submit Application, which the policy gate caught as RISKY and routed to the
  operator console for human confirmation; on resume the agent clicked through to the
  confirmation screen. Artifact cap-02cb1fee replays clean (6 steps). Evidence:
  evidence/disc-a99324d1.
- Total OpenAI spend across ALL runs incl. failed early iterations: $0.0078 (57 calls).
- Bugs the real runs exposed and fixed (evidence the runs were genuine): extracted
  values not fed back to the model; resume latch stayed set across interventions;
  role+name needed a role-only fallback for unnamed legacy elements; replay
  checkpoints needed {{inputs.x}} rendering; declared outputs now derive from the
  model's actual extract steps.

## Completed 2026-09-13 (second pass)
9. Stability: both real artifacts replayed 5/5 with identical outputs (lookup:
   $4,812.07 every time; sub-account: 6 steps success every time) - multi-run
   stability stretch goal satisfied.
10. Fresh-environment test PASSED: clean git clone + fresh venv + README cold path;
    .secrets correctly absent from the repo; all three documented replay commands
    succeeded with no API key present.
11. REPORT.md (7 required headings, ~2 pages) and README.md (setup + demo path)
    written and committed.

## Remaining before submission
1. Cross-"tenant" check (optional stretch): same artifact against a rebranded variant.
2. Manyu's review pass + drill on the ADR focal points, then repo creation on
   ManyuRV and the submission email.
