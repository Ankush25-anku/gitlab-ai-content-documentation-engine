# Evaluation report

Generated 2026-11-02 with `LLM_PROVIDER=mock` by `python -m ai.evaluation.run_eval`.

Each scenario is run twice on the same inputs: a one-shot baseline (one writer call, prompt v1, no review stages) and the full multi-agent workflow. Key-fact recall is graded against `data/eval/golden/`.

| Scenario | Mode | Key-fact recall | Unsupported claims | Claim support | Citation validity | Structure | Overall | Forbidden phrases |
|---|---|---|---|---|---|---|---|---|
| release_note | one-shot (writer v1) | 100% | 1 | 94% | 100% | 100% | 88.6 | dramatically faster |
| release_note | multi-agent workflow | 100% | 0 | 100% | 100% | 100% | 100.0 | none |
| docs_page | one-shot (writer v1) | 100% | 1 | 94% | 100% | 100% | 85.6 | dramatically faster |
| docs_page | multi-agent workflow | 100% | 0 | 100% | 100% | 100% | 97.0 | none |
| blog | one-shot (writer v1) | 100% | 1 | 95% | 100% | 100% | 85.8 | dramatically faster |
| blog | multi-agent workflow | 100% | 0 | 100% | 100% | 100% | 97.0 | none |
| api_reference | one-shot (writer v1) | 100% | 1 | 72% | 100% | 100% | 75.8 | dramatically faster |
| api_reference | multi-agent workflow | 100% | 0 | 76% | 100% | 100% | 86.8 | none |

Note: in mock mode the agents are deterministic stand-ins, so these numbers test the pipeline and the governance checks. Re-run with `LLM_PROVIDER=crewai` and a Gemini key to evaluate real model output.
