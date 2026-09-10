"""Deterministic replay: no model in the loop. Executes an artifact against a
live surface with stable targeting, bounded waits, and an explicit error
taxonomy (business outcome / recoverable / hard failure).
"""
from __future__ import annotations
import uuid, time
from .schema import CapabilityArtifact, Step, Checkpoint
from .surface import WebSurface
from .guardrails import Policy, PolicyViolation
from .evidence import EvidenceLog
from .results import RunResult, FailureDetail, BusinessOutcome

WAIT_BACKOFF = [1.0, 2.0, 4.0]   # transient slowness: bounded retries per checkpoint


class ReplayEngine:
    def __init__(self, surface: WebSurface, policy: Policy, out_dir: str = "evidence"):
        self.surface, self.policy = surface, policy
        self.run_id = "replay-" + uuid.uuid4().hex[:8]
        self.evidence = EvidenceLog(self.run_id, out_dir, policy)

    def replay(self, art: CapabilityArtifact, params: dict) -> RunResult:
        ev = self.evidence
        ev.event("replay_start", artifact=art.id, params=str({k: ("[REDACTED]" if p.sensitive else params.get(k))
                                                              for k, p in ((i.name, i) for i in art.inputs)}))
        for inp in art.inputs:
            if inp.required and inp.name not in params:
                return self._fail(0, f"required input {inp.name}", "missing", art)
        outputs: dict = {}

        # Entry point: every replay starts by navigating to the recorded target.
        # (Multi-tenant seam: a tenant override swaps base_url, steps unchanged.)
        try:
            self.policy.check_url(art.target.base_url)
            self._goto_with_retry(art.target.base_url, None)
        except Exception as e:
            return self._fail(0, f"load entry {art.target.base_url}", str(e), art)

        for step in art.steps:
            ev.event("step_start", step=str(step.id), action=step.action)
            # 1. Check for known runtime conditions BEFORE acting (e.g. interstitial).
            early = self._check_conditions(art, step)
            if early is not None:
                return early
            try:
                if step.action == "navigate":
                    url = art.render_template(step.url, params)
                    self.policy.check_url(url)
                    self._goto_with_retry(url, step)
                else:
                    value = art.render_template(step.value, params) if step.value else None
                    self.policy.check_action(step.action)
                    text = self._act_with_retry(step, value)
                    if step.action == "extract":
                        outputs[step.extract_as] = text.strip()
                        ev.event("extract", name=step.extract_as, value=self.policy.redact(text))
            except PolicyViolation as e:
                return self._fail(step.id, "policy-compliant action", f"policy violation: {e}", art)
            except Exception as e:
                handled = self._check_conditions(art, step, error=str(e))
                if handled is not None:
                    return handled
                return self._fail(step.id, _expect(step), str(e), art)
            # 2. Verify checkpoint with bounded backoff (transient slowness).
            if step.checkpoint and not self._verify(self._render_cp(step.checkpoint, art, params), step.id):
                handled = self._check_conditions(art, step, error="checkpoint failed")
                if handled is not None:
                    return handled
                return self._fail(step.id, _expect(step), "checkpoint not satisfied after retries", art)
            ev.event("step_ok", step=str(step.id))

        if not self._verify(self._render_cp(art.success, art, params), 0):
            return self._fail(art.steps[-1].id, "final success condition", "not satisfied", art)
        ev.event("replay_success", outputs=str(outputs))
        ev.close()
        return RunResult(status="success", outputs=outputs,
                         steps_completed=len(art.steps), run_id=self.run_id)

    # ---- internals ----
    def _render_cp(self, cp, art, params):
        if cp.value and "{{inputs." in cp.value:
            cp = cp.model_copy(update={"value": art.render_template(cp.value, params)})
        return cp

    def _check_conditions(self, art, step, error=None) -> RunResult | None:
        body = self.surface.page_text()
        for code, m in art.business_outcomes.items():
            if m.text and m.text in body:
                self.evidence.event("business_outcome", code=code)
                self.evidence.close()
                return RunResult(status="business_outcome",
                                 outcome=BusinessOutcome(code=code, detail=m.text),
                                 run_id=self.run_id)
        for h in step.on_error:
            if h.match.text and h.match.text in body:
                if h.kind == "business_outcome":
                    return RunResult(status="business_outcome",
                                     outcome=BusinessOutcome(code=h.outcome_code or "unknown",
                                                             detail=h.match.text),
                                     run_id=self.run_id)
                if h.kind == "recover" and h.recover_action:
                    self.evidence.event("recover", step=str(step.id), action=h.recover_action)
                    return None  # recovery executed by caller's retry path
        return None

    def _goto_with_retry(self, url, step):
        last = None
        for wait in [0] + WAIT_BACKOFF:
            if wait:
                time.sleep(wait)
            try:
                self.surface.navigate(url)
                return
            except Exception as e:
                last = e
        raise last

    def _act_with_retry(self, step, value):
        last = None
        for wait in [0] + WAIT_BACKOFF:
            if wait:
                time.sleep(wait)
            try:
                return self.surface.act(step.action, step.locators, value, step.extract_mode)
            except Exception as e:
                last = e
                self.evidence.event("step_retry", step=str(step.id), after=str(wait))
        raise last

    def _verify(self, cp: Checkpoint, step_id: int) -> bool:
        for wait in [0] + WAIT_BACKOFF:
            if wait:
                time.sleep(wait)
            try:
                if cp.type == "url_contains" and cp.value in self.surface.url:
                    return True
                if cp.type == "text_present" and cp.value in self.surface.page_text():
                    return True
                if cp.type == "locator_present" and cp.locator and \
                        self.surface.resolve([cp.locator]).count() >= 0:
                    self.surface.resolve([cp.locator])
                    return True
            except Exception:
                pass
        return False

    def _fail(self, step_id, expected, observed, art) -> RunResult:
        shot = self.evidence.screenshot(self.surface.page, f"fail-step{step_id}")
        aria = self.evidence.aria_snapshot(self.surface.page, f"fail-step{step_id}")
        self.evidence.event("replay_failure", step=str(step_id), observed=str(observed))
        self.evidence.close()
        return RunResult(status="failure",
                         failure=FailureDetail(step_id=step_id, expected=expected,
                                               observed=str(observed), evidence=[shot, aria]),
                         run_id=self.run_id)


def _expect(step: Step) -> str:
    if step.action == "navigate":
        return f"load {step.url}"
    tgt = step.locators[0].describe() if step.locators else "<no locator>"
    return f"{step.action} on {tgt}"
