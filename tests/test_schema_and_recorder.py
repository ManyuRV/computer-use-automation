from cuas.recorder import compile_artifact
from cuas.schema import (
    CapabilityArtifact,
    Checkpoint,
    InputParam,
    Locator,
    OutputSpec,
    SCHEMA_VERSION,
    Target,
)


def test_artifact_templates_declared_inputs():
    artifact = CapabilityArtifact(
        id="cap-test",
        name="lookup",
        target=Target(app="demo", base_url="http://localhost:8377/"),
        success=Checkpoint(type="url_contains", value="/"),
    )
    assert artifact.render_template("/member/{{inputs.member_id}}", {"member_id": 42}) == "/member/42"


def test_artifact_rejects_unknown_action():
    payload = {
        "schema_version": SCHEMA_VERSION,
        "id": "cap-test",
        "name": "bad action",
        "target": {"app": "demo", "base_url": "http://localhost:8377/"},
        "steps": [{"id": 1, "action": "shell"}],
        "success": {"type": "url_contains", "value": "/"},
    }
    try:
        CapabilityArtifact.model_validate(payload)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown actions must fail validation")


def test_role_locator_description_is_human_readable():
    locator = Locator(strategy="role", value="", role="button", name="Search")
    assert locator.describe() == "role=button name='Search'"


def test_recorder_parameterizes_inputs_and_renumbers_steps():
    trace = [
        {
            "step": 2,
            "action": "fill",
            "chain": [{"strategy": "role", "value": "", "role": "textbox"}],
            "value": "12345",
        },
        {
            "step": 5,
            "action": "extract",
            "chain": [{"strategy": "text", "value": "Savings Balance"}],
            "extract_as": "balance",
            "extract_mode": "adjacent_cell",
            "post_url": "http://localhost:8377/member/12345",
        },
    ]
    artifact = compile_artifact(
        goal="look up a member",
        entry_url="http://localhost:8377/",
        trace=trace,
        params={"member_id": "12345"},
        input_specs=[InputParam(name="member_id")],
        output_specs=[OutputSpec(name="balance", type="currency")],
        business_outcomes={"member_not_found": "No member found"},
        model_name="test-provider",
        llm_driven=False,
        run_id="run-test",
        app_name="demo",
    )
    assert [step.id for step in artifact.steps] == [1, 2]
    assert artifact.steps[0].value == "{{inputs.member_id}}"
    assert artifact.steps[1].extract_as == "balance"
    assert artifact.business_outcomes["member_not_found"].text == "No member found"
    assert artifact.provenance.llm_driven is False
