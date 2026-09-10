"""Human-in-the-loop escalation and control transfer.

Model: a run has exactly one control owner at a time ('agent' or 'human').
When the agent is stuck (repeated failure, dead-end, guardrail stop), it
raises an InterventionRequest carrying goal, step, reason, and evidence,
pauses, and cedes the lease. A minimal operator surface (mock UI, real
mechanism) exposes the SAME live browser session: the human views a live
screenshot, takes the lease, performs manual actions against the live page,
records them, and releases the lease; the agent loop resumes from the state
the human left behind.
"""
from __future__ import annotations
import json, os, threading, time, queue
from typing import Optional
from flask import Flask, request as freq, Response

LEASE_AGENT, LEASE_HUMAN = "agent", "human"


class InterventionManager:
    def __init__(self, surface, evidence, run_id: str, goal: str, port: int = 8378):
        self.surface = surface
        self.evidence = evidence
        self.run_id = run_id
        self.goal = goal
        self.port = port
        self.lease = LEASE_AGENT
        self.request_record: Optional[dict] = None
        self.human_actions: list[dict] = []
        self.resumed = threading.Event()
        self._server_started = False
        # Playwright's sync API is thread-bound: the operator server runs on its
        # own thread, so human actions are ENQUEUED and executed by the agent
        # thread that owns the live session. Same for screenshots: the agent
        # thread publishes frames; the server only serves the latest bytes.
        self.action_queue: queue.Queue = queue.Queue()
        self.action_results: queue.Queue = queue.Queue()
        self.latest_frame: bytes = b""

    def raise_intervention(self, reason: str, step: int) -> dict:
        self.resumed.clear()   # re-arm: every intervention needs its own release
        shot = self.evidence.screenshot(self.surface.page, f"intervention-step{step}")
        self.request_record = {
            "run_id": self.run_id, "goal": self.goal, "step": step,
            "reason": reason, "url": self.surface.url, "screenshot": shot,
            "raised_at": time.time(),
        }
        path = os.path.join(self.evidence.dir, "intervention_request.json")
        with open(path, "w") as f:
            json.dump(self.request_record, f, indent=2)
        self.evidence.event("intervention_raised", reason=reason, step=str(step))
        self.lease = LEASE_HUMAN
        self._ensure_server()
        return self.request_record

    def wait_for_release(self, timeout_s: float = 300) -> bool:
        """Agent paused: publish live frames and execute queued human actions
        on this (session-owning) thread until the human releases control."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self.resumed.is_set():
                self.lease = LEASE_AGENT
                self.evidence.event("control_returned",
                                    human_actions=json.dumps(self.human_actions))
                return True
            try:
                self.latest_frame = self.surface.page.screenshot()
            except Exception:
                pass
            try:
                while True:
                    a = self.action_queue.get_nowait()
                    self.action_results.put(self._exec_human(a))
            except queue.Empty:
                pass
            time.sleep(0.4)
        return False

    def _exec_human(self, a: dict) -> str:
        try:
            if a["kind"] == "click_text":
                self.surface.page.get_by_text(a["a1"], exact=False).first.click(timeout=5000)
            elif a["kind"] == "goto":
                self.surface.page.goto(a["a1"], timeout=15000)
            elif a["kind"] == "fill_text":
                self.surface.page.get_by_label(a["a1"]).fill(a["a2"], timeout=5000)
            rec = {**a, "ts": time.time()}
            self.human_actions.append(rec)
            self.evidence.event("human_action", action_kind=a["kind"], a1=a["a1"], a2=a["a2"])
            return "ok"
        except Exception as e:
            return f"failed: {e}"

    # ---- mock operator surface (real control-transfer mechanism) ----
    def _ensure_server(self):
        if self._server_started:
            return
        self._server_started = True
        mgr = self
        op = Flask("operator")

        @op.route("/")
        def home():
            return (f"<h3>Operator console (mock UI)</h3><p>Goal: {mgr.goal}</p>"
                    f"<p>Reason: {mgr.request_record['reason']}</p>"
                    f"<p>Control owner: <b>{mgr.lease}</b></p>"
                    f"<img src='/shot.png?{time.time()}' width='700'><br>"
                    "<form method='POST' action='/act'>"
                    "action: <select name='kind'><option>click_text</option>"
                    "<option>goto</option><option>fill_text</option></select>"
                    " arg1: <input name='a1'> arg2: <input name='a2'>"
                    "<button type='submit'>Do it</button></form>"
                    "<form method='POST' action='/resume'><button>Release control & resume automation</button></form>")

        @op.route("/shot.png")
        def shot():
            return Response(mgr.latest_frame, mimetype="image/png")

        @op.route("/act", methods=["POST"])
        def act():
            kind, a1, a2 = freq.form.get("kind"), freq.form.get("a1", ""), freq.form.get("a2", "")
            if mgr.lease != LEASE_HUMAN:
                return "automation holds control", 409
            mgr.action_queue.put({"kind": kind, "a1": a1, "a2": a2})
            try:
                res = mgr.action_results.get(timeout=20)
            except queue.Empty:
                return "timed out waiting for the automation thread", 504
            return (f"done. <a href='/'>back</a>" if res == "ok"
                    else f"action failed: {res}. <a href='/'>back</a>")

        @op.route("/resume", methods=["POST"])
        def resume():
            mgr.resumed.set()
            return "control returned to automation."

        threading.Thread(target=lambda: op.run(port=self.port), daemon=True).start()
        time.sleep(0.8)
