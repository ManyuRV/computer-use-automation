"""Discovery run: the LLM-driven observe -> decide -> act loop."""
from __future__ import annotations
import uuid, json
from .llm import Provider, Observation, Action
from .surface import WebSurface
from .guardrails import Policy, PolicyViolation
from .evidence import EvidenceLog
from .escalation import InterventionManager
from .results import RunResult, FailureDetail

MAX_SAME_ACTION = 3


class DiscoveryAgent:
    def __init__(self, surface: WebSurface, provider: Provider, policy: Policy,
                 evidence: EvidenceLog, escalation: InterventionManager):
        self.surface, self.provider = surface, provider
        self.policy, self.evidence, self.escalation = policy, evidence, escalation
        self.trace: list[dict] = []   # the raw material the recorder compiles

    def run(self, goal: str, entry_url: str, params: dict, max_steps: int = 25) -> RunResult:
        run_id = self.evidence.run_id
        history: list[str] = []
        last_sig, same_count, stuck = None, 0, 0
        outputs: dict = {}
        self.policy.check_url(entry_url)
        self.surface.navigate(entry_url)
        self.evidence.event("run_start", goal=goal, entry=entry_url)

        for step_i in range(1, max_steps + 1):
            self.policy.check_url(self.surface.url)
            obs = Observation(url=self.surface.url, aria=self.surface.observe_aria(),
                              goal=goal, history=list(history), stuck_count=stuck)
            action = self.provider.decide(obs)
            self.evidence.event("decision", step=str(step_i), action_kind=action.kind,
                                reason=action.reason, name=action.name or "")

            if action.kind == "done":
                self.evidence.event("run_done", outputs=str(outputs))
                return RunResult(status="success", outputs=outputs,
                                 steps_completed=step_i - 1, run_id=run_id)
            if action.kind in ("fail", "stuck"):
                r = self._escalate(action.reason, step_i, run_id)
                if r is None:
                    last_sig, same_count, stuck = None, 0, 0
                    continue
                return r

            try:
                self.policy.check_action(action.kind)
            except PolicyViolation as e:
                return self._escalate(f"policy: {e}", step_i, run_id, allow_resume=False)

            if action.kind in ("click", "select") and self.policy.is_risky(action.name) \
                    and action.reason != "confirmed-by-human":
                mode = self.policy.on_risky
                self.evidence.event("risky_action", step=str(step_i), name=action.name or "",
                                    handling=mode)
                if mode == "block":
                    return self._escalate(f"policy: risky action {action.name!r} blocked",
                                          step_i, run_id, allow_resume=False)
                if mode == "confirm":
                    r = self._escalate(f"risky action {action.name!r} requires human "
                                       f"confirmation", step_i, run_id)
                    if r is not None:
                        return r
                    action.reason = "confirmed-by-human"   # resumed: human approved

            sig = (action.kind, action.role, action.name, action.text, action.value, action.url)
            same_count = same_count + 1 if sig == last_sig else 1
            last_sig = sig
            if same_count >= MAX_SAME_ACTION:
                r = self._escalate("agent repeated the same action 3x without progress",
                                   step_i, run_id)
                if r is None:
                    last_sig, same_count, stuck = None, 0, 0
                    continue
                return r
            try:
                out = self._execute(action, params, step_i)
                outputs.update(out)
                stuck = 0
            except Exception as e:
                stuck += 1
                self.evidence.event("action_error", step=str(step_i), error=str(e))
                self.evidence.screenshot(self.surface.page, f"error-step{step_i}")
                if stuck >= 3:
                    r = self._escalate(f"3 consecutive action errors, last: {e}", step_i, run_id)
                    if r is None:
                        last_sig, same_count, stuck = None, 0, 0
                        continue
                    return r
            entry = f"{action.kind} {action.name or action.text or action.url or ''} {action.value or ''}"
            if out:
                entry += f" -> {json.dumps({k: self.policy.redact(str(v)) for k, v in out.items()})}"
            history.append(entry)

        return self._escalate("max steps reached", max_steps, run_id, allow_resume=False)

    def _execute(self, a: Action, params: dict, step_i: int) -> dict:
        s = self.surface
        if a.kind == "navigate":
            self.policy.check_url(a.url)
            s.navigate(a.url)
            self.trace.append({"step": step_i, "action": "navigate", "url": a.url,
                               "post_url": s.url})
            return {}
        chain = s.build_locator_chain(a.role, a.name, a.text)
        risky = self.policy.is_risky(a.name)
        extracted = s.act(a.kind, chain, a.value, a.extract_mode)
        rec = {"step": step_i, "action": a.kind, "chain": [l.model_dump() for l in chain],
               "value": a.value, "risky": risky, "post_url": s.url}
        if a.kind == "extract":
            rec["extract_as"] = a.extract_as
            rec["extract_mode"] = a.extract_mode
            rec["extracted"] = self.policy.redact(extracted)
            self.trace.append(rec)
            return {a.extract_as: extracted}
        self.trace.append(rec)
        return {}

    def _escalate(self, reason: str, step_i: int, run_id: str, allow_resume: bool = True):
        """Raise intervention and pause. Returns None if a human took control and
        released it (caller resumes the loop); otherwise the escalated result.
        Terminal escalations (allow_resume=False) always end the run."""
        req = self.escalation.raise_intervention(reason, step_i)
        if allow_resume and self.escalation.wait_for_release(timeout_s=300):
            self.evidence.event("resumed_after_human", step=str(step_i))
            return None
        return RunResult(status="escalated", run_id=run_id,
                         failure=FailureDetail(step_id=step_i, expected="autonomous progress",
                                               observed=reason, evidence=[req["screenshot"]]))
