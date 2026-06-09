from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vkr_knowledge_model import InferenceEngine, Severity, process_dsl_file  # noqa: E402


EXECUTABLE_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "EXP-EMPIRE-CAPTURE-01",
        "family": "capture",
        "fixture": "tests/fixtures/empire_deluxe/capture_neutral_city_success.kb",
        "expected_recommendation": "CaptureRecommendation",
        "expected_rules": ["CaptureNeutralCityRule"],
        "expected_warning": False,
    },
    {
        "id": "EXP-EMPIRE-TRANSPORT-02",
        "family": "transport",
        "fixture": "tests/fixtures/empire_deluxe/transport_load_success.kb",
        "expected_recommendation": "LoadTransportRecommendation",
        "expected_rules": ["LoadTransportRule"],
        "expected_warning": False,
    },
    {
        "id": "EXP-EMPIRE-PRODUCTION-01",
        "family": "production",
        "fixture": "tests/fixtures/empire_deluxe/landlocked_city_produces_army_only.kb",
        "expected_recommendation": "ProductionRecommendation",
        "expected_rules": ["LandlockedCityProduceArmyRule"],
        "expected_warning": False,
    },
]


def _blocking(issues: list[Any]) -> list[Any]:
    return [issue for issue in issues if issue.severity != Severity.WARNING]


def run_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    fixture_path = ROOT / scenario["fixture"]
    processing = process_dsl_file(str(fixture_path), source_graph_id="current_situation")
    pipeline_errors = [
        f"{issue.code}: {issue.message}"
        for issue in processing.issues
        if issue.severity != Severity.WARNING
    ]
    if processing.knowledge_base is None or pipeline_errors:
        return {
            **scenario,
            "status": "failed",
            "actual_recommendation": None,
            "fired_rules": [],
            "created_hypotheses": [],
            "has_derivation_record": False,
            "has_explanation": False,
            "warnings": [],
            "errors": pipeline_errors,
            "deterministic": False,
            "kb_graphs_unchanged": False,
            "generated_graphs_count": 0,
        }

    kb = processing.knowledge_base
    graph_count_before = len(kb.graphs)
    session = InferenceEngine(kb).run(source_graph_id="current_situation")
    graph_count_after = len(kb.graphs)
    repeat = InferenceEngine(kb).run(source_graph_id="current_situation")

    created_types = [hyp.hypothesis_type for hyp in session.created_hypotheses.values()]
    repeat_types = [hyp.hypothesis_type for hyp in repeat.created_hypotheses.values()]
    actual_recommendation = created_types[0] if created_types else None
    unexpected_errors = list(session.errors)
    unexpected_warnings = [] if scenario["expected_warning"] else list(session.warnings)

    recommendation_ok = scenario["expected_recommendation"] in created_types if scenario["expected_recommendation"] else not created_types
    rules_ok = list(session.fired_rule_ids) == list(scenario["expected_rules"])
    deterministic = session.fired_rule_ids == repeat.fired_rule_ids and created_types == repeat_types
    kb_graphs_unchanged = graph_count_before == graph_count_after
    generated_graphs_ok = bool(session.generated_graphs) == bool(created_types)

    status = "passed"
    if (
        not recommendation_ok
        or not rules_ok
        or not deterministic
        or not kb_graphs_unchanged
        or not generated_graphs_ok
        or unexpected_errors
        or unexpected_warnings
    ):
        status = "failed"

    return {
        **scenario,
        "status": status,
        "source_graph": "current_situation",
        "inference_parameters": {
            "mode": "one_step",
            "collect_explanations": True,
            "duplicate_suppression": False,
        },
        "actual_recommendation": actual_recommendation,
        "fired_rules": list(session.fired_rule_ids),
        "created_hypotheses": created_types,
        "has_match_result": bool(session.rule_application_results),
        "has_rule_application_result": bool(session.rule_application_results),
        "has_derivation_record": bool(session.derivation_records),
        "has_explanation": bool(session.explanations),
        "warnings": list(session.warnings),
        "expected_warnings": list(session.warnings) if scenario["expected_warning"] else [],
        "unexpected_warnings": unexpected_warnings,
        "errors": unexpected_errors,
        "deterministic": deterministic,
        "kb_graphs_unchanged": kb_graphs_unchanged,
        "generated_graphs_count": len(session.generated_graphs),
    }


def build_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    executable = [result for result in results if result["status"] != "deferred"]
    passed = [result for result in results if result["status"] == "passed"]
    partial = [result for result in results if result["status"] == "partial"]
    failed = [result for result in results if result["status"] == "failed"]
    deferred = [result for result in results if result["status"] == "deferred"]
    with_hypothesis = [result for result in executable if result.get("created_hypotheses")]
    with_derivation = [result for result in executable if result.get("has_derivation_record")]
    with_explanation = [result for result in executable if result.get("has_explanation")]
    reproducible = [result for result in executable if result.get("deterministic")]
    unchanged = [result for result in executable if result.get("kb_graphs_unchanged")]
    with_generated = [result for result in executable if result.get("generated_graphs_count", 0) > 0]
    expected_warning_messages = sum(len(result.get("expected_warnings", [])) for result in executable)
    unexpected_warning_messages = sum(len(result.get("unexpected_warnings", [])) for result in executable)
    unexpected_errors = sum(len(result.get("errors", [])) for result in executable)

    executable_count = len(executable)
    return {
        "total_scenarios": len(results),
        "executable_scenarios": executable_count,
        "passed": len(passed),
        "partial": len(partial),
        "failed": len(failed),
        "deferred": len(deferred),
        "pass_rate_executable": len(passed) / executable_count if executable_count else 0.0,
        "scenarios_with_hypothesis": len(with_hypothesis),
        "hypothesis_rate_executable": len(with_hypothesis) / executable_count if executable_count else 0.0,
        "scenarios_with_derivation_record": len(with_derivation),
        "derivation_record_rate_executable": len(with_derivation) / executable_count if executable_count else 0.0,
        "scenarios_with_explanation": len(with_explanation),
        "explanation_rate_executable": len(with_explanation) / executable_count if executable_count else 0.0,
        "reproducible_scenarios": len(reproducible),
        "reproducibility_rate_executable": len(reproducible) / executable_count if executable_count else 0.0,
        "expected_warning_messages": expected_warning_messages,
        "unexpected_warning_messages": unexpected_warning_messages,
        "unexpected_errors": unexpected_errors,
        "scenarios_with_unchanged_kb_graphs": len(unchanged),
        "unchanged_kb_graphs_rate_executable": len(unchanged) / executable_count if executable_count else 0.0,
        "scenarios_with_generated_graphs": len(with_generated),
    }


def main() -> int:
    executable_results = [run_scenario(scenario) for scenario in EXECUTABLE_SCENARIOS]
    results = executable_results
    payload = {
        "runner": "scripts/run_experiments.py",
        "test_command": "python -m unittest discover -s tests -v",
        "source_graph": "current_situation",
        "results": results,
        "metrics": build_metrics(results),
    }
    artifact_path = ROOT / "artifacts" / "experiment_results.json"
    artifact_path.parent.mkdir(exist_ok=True)
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    metrics = payload["metrics"]
    print(f"Wrote {artifact_path}")
    print(f"total_scenarios={metrics['total_scenarios']}")
    print(f"executable_scenarios={metrics['executable_scenarios']}")
    print(f"passed={metrics['passed']}")
    print(f"failed={metrics['failed']}")
    print(f"deferred={metrics['deferred']}")
    return 1 if metrics["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
