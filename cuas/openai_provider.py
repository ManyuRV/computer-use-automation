"""Real LLM provider for the discovery loop (OpenAI).

One action per call, JSON-only responses, temperature 0. Cost is tracked per
call from the response usage fields and the published model price
($0.15/M input, $0.60/M output for gpt-4o-mini per
https://developers.openai.com/api/docs/models/gpt-4o-mini), accumulated in
.secrets/spend.json. Hard stop at $5 cumulative, warning threshold at $2.
"""
from __future__ import annotations
import json, os, time
from .llm import Observation, Action

MODEL = "gpt-4o-mini"
PRICE_IN, PRICE_OUT = 0.15 / 1e6, 0.60 / 1e6   # USD per token, OpenAI published price
SPEND_FILE = os.path.join(os.path.dirname(__file__), "..", ".secrets", "spend.json")
WARN_AT, HARD_STOP = 2.00, 5.00

SYSTEM = """You are a computer-use agent operating a real web application to accomplish a goal.
You receive the page's accessibility tree and reply with ONE action as JSON.

Action schema (reply with JSON only, no markdown, no prose):
{"kind": "navigate"|"click"|"fill"|"select"|"extract"|"done"|"fail"|"stuck",
 "role": <aria role of target, e.g. "button","textbox","link","combobox", or null>,
 "name": <exact accessible name of target, or null if it has none>,
 "text": <visible text target, or null>,
 "value": <text to type / option to select, or null>,
 "url": <absolute url for navigate, or null>,
 "extract_as": <output name for extract, or null>,
 "extract_mode": <null, or "adjacent_cell" to read the cell AFTER a label cell in a label/value table>,
 "reason": <one short sentence>}

Rules:
- Prefer role+name targeting from the accessibility tree. An element with no accessible name
  (e.g. a bare "textbox") may be targeted by role alone.
- To read a value shown next to a label in a table (e.g. a balance next to "Savings Balance"),
  use kind=extract with text=<the label>, extract_mode="adjacent_cell", extract_as=<output name>.
- After an extract action, the extracted value appears in ACTIONS TAKEN SO FAR as
  "extract ... -> {...}". If the value is just the label text, retry with
  extract_mode="adjacent_cell". If the value answers the goal, reply done.
- Use kind=done as soon as the goal is verifiably accomplished.
- For a dropdown (<select>, role "combobox"), use kind=select targeting the combobox
  itself (role="combobox", name=its label or null) with value=<the option's visible text>.
- If the app shows a validation or error message, treat it as information: fix the
  offending field and retry. Do not report stuck for a recoverable form error.
- Use kind=stuck only when you genuinely cannot make progress.
- Never navigate outside the target application's host."""


class SpendTracker:
    def __init__(self):
        self.state = self._load()

    def _load(self):
        try:
            return json.load(open(SPEND_FILE))
        except Exception:
            return {"cumulative_usd": 0.0, "calls": 0}

    def add(self, usage) -> dict:
        cost = usage.prompt_tokens * PRICE_IN + usage.completion_tokens * PRICE_OUT
        self.state["cumulative_usd"] = round(self.state["cumulative_usd"] + cost, 6)
        self.state["calls"] += 1
        os.makedirs(os.path.dirname(SPEND_FILE), exist_ok=True)
        json.dump(self.state, open(SPEND_FILE, "w"))
        return {"cost_usd": round(cost, 6), "cumulative_usd": self.state["cumulative_usd"],
                "warn": self.state["cumulative_usd"] >= WARN_AT,
                "stop": self.state["cumulative_usd"] >= HARD_STOP}


class OpenAIProvider:
    model_name = f"openai/{MODEL}"

    def __init__(self, entry_url: str, key_path: str):
        from openai import OpenAI
        if os.path.exists(key_path):
            os.environ["OPENAI_API_KEY"] = open(key_path).read().strip()
        elif not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("no OpenAI key: .secrets/openai_key missing and OPENAI_API_KEY unset")
        self.client = OpenAI()
        self.entry_url = entry_url
        self.spend = SpendTracker()
        self.last_cost: dict = {}

    def decide(self, obs: Observation) -> Action:
        if self.spend.state["cumulative_usd"] >= HARD_STOP:
            raise RuntimeError(f"spend hard stop reached (${HARD_STOP})")
        user = (f"GOAL: {obs.goal}\n"
                f"ENTRY POINT: {self.entry_url}\n"
                f"CURRENT URL: {obs.url}\n"
                f"ACTIONS TAKEN SO FAR: {json.dumps(obs.history[-8:])}\n"
                f"ACCESSIBILITY TREE:\n{obs.aria[:6000]}\n"
                f"Reply with one action as JSON.")
        r = self.client.chat.completions.create(
            model=MODEL, temperature=0, max_tokens=300,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": user}])
        self.last_cost = self.spend.add(r.usage)
        raw = r.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").removeprefix("json").strip()
        try:
            return Action.model_validate_json(raw)
        except Exception as e:
            return Action(kind="fail", reason=f"unparseable model output: {e}: {raw[:200]}")
