"""Recorder: compile a successful discovery trace into a capability artifact.

Parameterization: any step value/URL segment equal to a declared input's
concrete discovery-time value is rewritten to {{inputs.name}}, turning the
recording into a reusable, typed capability.
"""
from __future__ import annotations
import uuid, datetime
from .schema import (CapabilityArtifact, Step, Locator, Checkpoint, InputParam,
                     OutputSpec, Target, Provenance, ErrorMatch)


def compile_artifact(goal: str, entry_url: str, trace: list[dict], params: dict,
                     input_specs: list[InputParam], output_specs: list[OutputSpec],
                     business_outcomes: dict[str, str], model_name: str,
                     llm_driven: bool, run_id: str, app_name: str) -> CapabilityArtifact:
    def parametrize(text):
        if text is None:
            return None
        for k, v in params.items():
            text = text.replace(str(v), "{{inputs." + k + "}}")
        return text

    steps: list[Step] = []
    for t in trace:
        chain = [Locator(**l) for l in t.get("chain", [])]
        if t["action"] == "navigate":
            url = parametrize(t["url"])
            steps.append(Step(id=t["step"], action="navigate", url=url,
                              checkpoint=Checkpoint(type="url_contains",
                                                    value=_path_of(parametrize(t["post_url"])))))
            continue
        cp = Checkpoint(type="locator_present", locator=chain[0]) if t["action"] == "extract" \
            else None
        steps.append(Step(id=t["step"], action=t["action"], locators=chain,
                          value=parametrize(t.get("value")),
                          extract_as=t.get("extract_as"), extract_mode=t.get("extract_mode"), checkpoint=cp,
                          risky=t.get("risky", False),
                          note=t.get("note", "")))
    # Renumber sequentially (trace step ids can skip on retries).
    for i, s in enumerate(steps, 1):
        s.id = i

    final_extract = next((s for s in reversed(steps) if s.action == "extract"), None)
    last_url = next((t.get("post_url") for t in reversed(trace) if t.get("post_url")), "/")
    success = (Checkpoint(type="locator_present", locator=final_extract.locators[0])
               if final_extract else Checkpoint(type="url_contains", value=_path_of(parametrize(last_url))))

    return CapabilityArtifact(
        id="cap-" + uuid.uuid4().hex[:8], name=goal[:60], description=goal,
        target=Target(app=app_name, base_url=entry_url, entry_route="/"),
        inputs=input_specs, outputs=output_specs, steps=steps, success=success,
        business_outcomes={k: ErrorMatch(text=v) for k, v in business_outcomes.items()},
        provenance=Provenance(run_id=run_id, model=model_name, llm_driven=llm_driven,
                              recorded_at=datetime.datetime.now().isoformat(timespec="seconds")))


def _path_of(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).path or "/"
