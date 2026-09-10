"""cuas CLI: discover / replay against the local demo target.

  python cli.py discover --goal "look up member 12345 ..." --member-id 12345
  python cli.py replay --artifact artifacts/<file>.json --params member_id=12345
"""
import argparse, json, sys, uuid, os
sys.path.insert(0, os.path.dirname(__file__))
from cuas.surface import WebSurface
from cuas.guardrails import Policy
from cuas.evidence import EvidenceLog
from cuas.escalation import InterventionManager
from cuas.llm import ScriptedProvider
from cuas.openai_provider import OpenAIProvider
from cuas.agent import DiscoveryAgent
from cuas.recorder import compile_artifact
from cuas.schema import CapabilityArtifact, InputParam, OutputSpec
from cuas.replay import ReplayEngine

ENTRY = "http://localhost:8377/"


def cmd_discover(a):
    policy = Policy()
    run_id = "disc-" + uuid.uuid4().hex[:8]
    surface = WebSurface(headless=True)
    ev = EvidenceLog(run_id, "evidence", policy)
    esc = InterventionManager(surface, ev, run_id, a.goal)
    if a.llm == "openai":
        provider = OpenAIProvider(entry_url=ENTRY, key_path=".secrets/openai_key")
    else:
        provider = ScriptedProvider(member_id=a.member_id, entry_url=ENTRY)
    agent = DiscoveryAgent(surface, provider, policy, ev, esc)
    params = {"member_id": a.member_id}
    result = agent.run(a.goal, ENTRY, params)
    ev.close()
    with open(os.path.join("evidence", run_id, "trace.json"), "w") as f:
        json.dump(agent.trace, f, indent=2)
    if result.status != "success":
        print("discovery did not complete:", result.model_dump_json(indent=2))
        surface.close(); sys.exit(1)
    art = compile_artifact(
        goal=a.goal, entry_url=ENTRY, trace=agent.trace, params=params,
        input_specs=[InputParam(name="member_id", description="Member ID")],
        output_specs=[OutputSpec(name=t["extract_as"], type="currency",
                                 description=f"Extracted {t['extract_as']}")
                      for t in agent.trace if t.get("extract_as")],
        business_outcomes={"member_not_found": "No member found"},
        model_name=provider.model_name, llm_driven=(a.llm == "openai"), run_id=run_id,
        app_name="MemberServ-demo")
    os.makedirs("artifacts", exist_ok=True)
    path = f"artifacts/{art.id}.json"
    with open(path, "w") as f:
        f.write(art.model_dump_json(indent=2))
    surface.close()
    if a.llm == "openai":
        print("SPEND:", provider.last_cost)
    print("ARTIFACT:", path)
    print("OUTPUTS:", json.dumps(result.outputs))


def cmd_replay(a):
    params = dict(kv.split("=", 1) for kv in (a.params or []))
    with open(a.artifact) as f:
        art = CapabilityArtifact.model_validate_json(f.read())
    engine = ReplayEngine(WebSurface(headless=True), Policy())
    result = engine.replay(art, params)
    engine.surface.close()
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("discover")
    d.add_argument("--goal", required=True); d.add_argument("--member-id", required=True)
    d.add_argument("--llm", choices=["scripted", "openai"], default="scripted")
    r = sub.add_parser("replay")
    r.add_argument("--artifact", required=True); r.add_argument("--params", nargs="*")
    a = ap.parse_args()
    {"discover": cmd_discover, "replay": cmd_replay}[a.cmd](a)
