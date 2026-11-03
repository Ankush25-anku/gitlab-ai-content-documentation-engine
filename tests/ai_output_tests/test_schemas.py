"""Agent output schemas must be accepted by the Gemini API: no `additionalProperties` anywhere."""
import importlib
import pkgutil

from pydantic import BaseModel

import ai.agents
import ai.schemas
from ai.agents.base import AgentSpec
from ai.schemas import PublishPackage, SourceRef


def _additional_properties(node, path="$"):
    """Yield the JSON path of every additionalProperties key in a JSON schema."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "additionalProperties":
                yield f"{path}.{key}"
            yield from _additional_properties(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _additional_properties(value, f"{path}[{i}]")


def _agent_specs() -> list[AgentSpec]:
    specs = []
    for mod in pkgutil.iter_modules(ai.agents.__path__):
        if mod.ispkg:
            spec = getattr(importlib.import_module(f"ai.agents.{mod.name}.agent"), "SPEC", None)
            if isinstance(spec, AgentSpec):
                specs.append(spec)
    return specs


def test_every_agent_output_schema_has_no_additional_properties():
    specs = _agent_specs()
    assert len(specs) == 6, [s.name for s in specs]  # all six agents found
    for spec in specs:
        hits = list(_additional_properties(spec.output_model.model_json_schema()))
        assert not hits, f"{spec.name} output schema ({spec.output_model.__name__}) has {hits}"


def test_every_shared_schema_has_no_additional_properties():
    models = [m for m in vars(ai.schemas).values() if isinstance(m, type) and issubclass(m, BaseModel)]
    assert PublishPackage in models
    for model in models:
        hits = list(_additional_properties(model.model_json_schema()))
        assert not hits, f"{model.__name__} has {hits}"


def test_the_check_catches_free_form_dicts():
    class Loose(BaseModel):
        meta: dict

    assert list(_additional_properties(Loose.model_json_schema())) == ["$.properties.meta.additionalProperties"]


def test_front_matter_renders_as_yaml_in_field_order():
    from ai.agents.publishing_coordinator.agent import mock_publish
    from ai.schemas import Draft, Section
    from backend.publishing.exporters import export_cms_json, render_markdown

    draft = Draft(title="Cache stats API", summary="S", sections=[Section(heading="Overview", body_markdown="x [S1].",
                                                                          source_ids=["S1"])])
    sources = [SourceRef(id="S1", chunk_id="input:spec.yaml#0", origin="input", title="Spec", text="x")]
    job = {"content_type": "api_reference", "product_area": "Verify", "target_channel": "api_reference"}
    package = mock_publish(draft, sources, job, "Priya", ["Arjun"])
    front = render_markdown(draft, package, sources).split("---")[1]
    keys = [line.split(":")[0] for line in front.strip().splitlines() if not line.startswith(("-", " "))]
    assert keys == ["title", "content_type", "stage", "group", "owner", "last_reviewed", "info", "sources"]
    assert "- input:spec.yaml#0" in front
    cms = export_cms_json(draft, package)
    assert cms["content_type"] == "api_reference" and cms["metadata"]["sources"] == ["input:spec.yaml#0"]


def test_stored_packages_from_before_the_change_still_load():
    """agent_runs.output_json rows written with the old dict front matter must still validate."""
    old = {"slug": "s", "file_path": "doc/api/s.md", "mr_title": "t", "mr_description": "d", "target_channel": "api_reference",
           "owner": "Priya", "front_matter": {"title": "T", "content_type": "api_reference", "stage": "Verify",
                                              "group": "Technical Writing", "owner": "Priya",
                                              "last_reviewed": "2026-11-01", "info": "i", "sources": []}}
    assert PublishPackage.model_validate(old).front_matter.stage == "Verify"
