"""Content job state machine. docs/workflow_states.md documents the same table."""
from backend.services.errors import AppError

STAGES = ["context", "draft", "tech_review", "tone", "structure"]
STAGE_STATUS = {
    "context": "CONTEXT_PREPARING",
    "draft": "DRAFTING",
    "tech_review": "TECH_REVIEW",
    "tone": "TONE_OPTIMIZING",
    "structure": "STRUCTURE_OPTIMIZING",
}
STAGE_LABEL = {
    "context": "Context Reader", "draft": "Documentation Writer", "tech_review": "Technical Reviewer",
    "tone": "Tone Optimizer", "structure": "Structure Optimizer", "quality": "Quality Scorer",
    "publish_prep": "Publishing Coordinator",
}

TRANSITIONS: dict[str, set[str]] = {
    "INTAKE": {"CONTEXT_PREPARING", "FAILED"},
    "CONTEXT_PREPARING": {"CONTEXT_READY", "NEEDS_INPUT", "FAILED"},
    "CONTEXT_READY": {"CONTEXT_PREPARING", "DRAFTING", "FAILED"},
    "NEEDS_INPUT": {"CONTEXT_PREPARING", "FAILED"},
    # A rerun of selected stages may skip ahead, so a running stage can move to any later stage.
    "DRAFTING": {"TECH_REVIEW", "TONE_OPTIMIZING", "STRUCTURE_OPTIMIZING", "IN_REVIEW", "FAILED"},
    "TECH_REVIEW": {"TONE_OPTIMIZING", "STRUCTURE_OPTIMIZING", "IN_REVIEW", "FAILED"},
    "TONE_OPTIMIZING": {"STRUCTURE_OPTIMIZING", "IN_REVIEW", "FAILED"},
    "STRUCTURE_OPTIMIZING": {"IN_REVIEW", "FAILED"},
    "IN_REVIEW": {"APPROVED", "REVISION_REQUESTED", "REJECTED", "IN_REVIEW"},
    "REVISION_REQUESTED": {"CONTEXT_PREPARING", "DRAFTING", "TECH_REVIEW", "TONE_OPTIMIZING",
                           "STRUCTURE_OPTIMIZING", "IN_REVIEW", "FAILED"},
    "REJECTED": {"REVISION_REQUESTED"},
    "APPROVED": {"PUBLISH_PREPARING", "REVISION_REQUESTED"},
    "PUBLISH_PREPARING": {"PUBLISH_READY", "FAILED", "APPROVED"},
    "PUBLISH_READY": {"EXPORTED", "PUBLISH_READY", "REVISION_REQUESTED"},
    "EXPORTED": {"EXPORTED", "REVISION_REQUESTED"},
    "FAILED": {"CONTEXT_PREPARING", "DRAFTING", "TECH_REVIEW", "TONE_OPTIMIZING", "STRUCTURE_OPTIMIZING",
               "PUBLISH_PREPARING", "IN_REVIEW", "APPROVED"},
}
RUNNING = {"CONTEXT_PREPARING", "DRAFTING", "TECH_REVIEW", "TONE_OPTIMIZING", "STRUCTURE_OPTIMIZING",
           "PUBLISH_PREPARING"}
APPROVED_OR_LATER = {"APPROVED", "PUBLISH_PREPARING", "PUBLISH_READY", "EXPORTED"}


def assert_transition(job_id: str, current: str, new: str) -> None:
    if new not in TRANSITIONS.get(current, set()):
        raise AppError("INVALID_STATE", f"Cannot move job from {current} to {new}.", job_id)
