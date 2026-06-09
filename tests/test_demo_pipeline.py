from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vkr_knowledge_model import (  # noqa: E402
    InferenceEngine,
    Severity,
    parse_text,
    process_dsl_file,
    process_dsl_text,
    validate_knowledge_base_for_inference,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "empire_deluxe"
SOURCE_GRAPH = "current_situation"

SCENARIOS = [
    ("capture_neutral_city_success.kb", "CaptureRecommendation", ["CaptureNeutralCityRule"]),
    ("transport_load_success.kb", "LoadTransportRecommendation", ["LoadTransportRule"]),
    ("landlocked_city_produces_army_only.kb", "ProductionRecommendation", ["LandlockedCityProduceArmyRule"]),
]


def blocking(issues):
    return [issue for issue in issues if issue.severity != Severity.WARNING]


def load_kb(test_case, fixture_name):
    result = process_dsl_file(str(FIXTURE_DIR / fixture_name), source_graph_id=SOURCE_GRAPH)
    test_case.assertIsNotNone(result.knowledge_base)
    test_case.assertEqual([], blocking(result.issues))
    return result.knowledge_base


def run_fixture(test_case, fixture_name):
    kb = load_kb(test_case, fixture_name)
    graph_count = len(kb.graphs)
    session = InferenceEngine(kb).run(source_graph_id=SOURCE_GRAPH)
    test_case.assertEqual(graph_count, len(kb.graphs))
    return kb, session


class DemoPipelineTests(unittest.TestCase):
    def test_compact_dsl_rejects_user_hypotheses_section(self):
        text = """
knowledge_base Bad
types:
  type Entity
relations:
individuals:
graphs:
hypotheses:
  hypothesis h1 {
    type Recommendation
  }
"""
        result = parse_text(text)
        self.assertIn("PARSE_UNKNOWN_SECTION", {issue.code for issue in result.errors})
        processing = process_dsl_text(text)
        self.assertIsNone(processing.translation)

    def test_capture_fixture_translates_to_knowledge_base(self):
        kb = load_kb(self, "capture_neutral_city_success.kb")
        self.assertIn("Army", kb.type_hierarchy.types_by_name)
        self.assertIn("can_capture", kb.relation_types)
        self.assertIn("current_situation", kb.graphs)
        self.assertIn("CaptureNeutralCityRule", kb.rules)

    def test_semantic_report_accepts_all_demo_fixtures(self):
        for fixture, _, _ in SCENARIOS:
            with self.subTest(fixture=fixture):
                kb = load_kb(self, fixture)
                report = validate_knowledge_base_for_inference(kb, source_graph_id=SOURCE_GRAPH)
                self.assertTrue(report.is_usable_for_inference)
                self.assertEqual([], blocking(report.issues))

    def test_capture_scenario_creates_capture_recommendation(self):
        _, session = run_fixture(self, "capture_neutral_city_success.kb")
        self.assertEqual("COMPLETED", session.status)
        self.assertEqual(["CaptureNeutralCityRule"], session.fired_rule_ids)
        self.assertEqual({"CaptureRecommendation"}, {hyp.hypothesis_type for hyp in session.created_hypotheses.values()})

    def test_transport_scenario_creates_load_recommendation(self):
        _, session = run_fixture(self, "transport_load_success.kb")
        self.assertEqual("COMPLETED", session.status)
        self.assertEqual(["LoadTransportRule"], session.fired_rule_ids)
        self.assertEqual({"LoadTransportRecommendation"}, {hyp.hypothesis_type for hyp in session.created_hypotheses.values()})

    def test_production_scenario_creates_army_production_only(self):
        _, session = run_fixture(self, "landlocked_city_produces_army_only.kb")
        self.assertEqual("COMPLETED", session.status)
        self.assertEqual(["LandlockedCityProduceArmyRule"], session.fired_rule_ids)
        result_graph = next(iter(session.generated_graphs.values()))
        result_types = {concept.concept_type_id for concept in result_graph.concept_nodes.values()}
        self.assertIn("Army", result_types)
        self.assertNotIn("Transport", result_types)

    def test_inference_results_are_deterministic(self):
        for fixture, _, _ in SCENARIOS:
            with self.subTest(fixture=fixture):
                kb = load_kb(self, fixture)
                first = InferenceEngine(kb).run(source_graph_id=SOURCE_GRAPH)
                second = InferenceEngine(kb).run(source_graph_id=SOURCE_GRAPH)
                self.assertEqual(first.fired_rule_ids, second.fired_rule_ids)
                self.assertEqual(
                    [hyp.hypothesis_type for hyp in first.created_hypotheses.values()],
                    [hyp.hypothesis_type for hyp in second.created_hypotheses.values()],
                )

    def test_generated_graphs_are_session_local(self):
        kb = load_kb(self, "capture_neutral_city_success.kb")
        before = set(kb.graphs)
        session = InferenceEngine(kb).run(source_graph_id=SOURCE_GRAPH)
        self.assertEqual(before, set(kb.graphs))
        self.assertTrue(session.generated_graphs)
        hypothesis = next(iter(session.created_hypotheses.values()))
        self.assertIn(hypothesis.graph_id, session.generated_graphs)

    def test_explanation_contains_rule_source_and_hypothesis(self):
        _, session = run_fixture(self, "capture_neutral_city_success.kb")
        explanation = next(iter(session.explanations.values()))
        self.assertIn("CaptureNeutralCityRule", explanation.used_rule_ids)
        self.assertIn("current_situation", explanation.textual_summary)
        self.assertIn(next(iter(session.created_hypotheses)), explanation.target_hypothesis_id)

    def test_missing_source_graph_fails_inference_startup(self):
        kb = load_kb(self, "capture_neutral_city_success.kb")
        session = InferenceEngine(kb).run(source_graph_id="missing_graph")
        self.assertEqual("FAILED", session.status)
        self.assertTrue(session.errors)
        no_source_session = InferenceEngine(kb).run()
        self.assertEqual("FAILED", no_source_session.status)
        self.assertTrue(any("INFERENCE_READY_SOURCE_GRAPH_REQUIRED" in error for error in no_source_session.errors))

    def test_disabled_rules_fail_inference_startup(self):
        kb = load_kb(self, "capture_neutral_city_success.kb")
        for rule in kb.rules.values():
            rule.is_enabled = False
        session = InferenceEngine(kb).run(source_graph_id=SOURCE_GRAPH)
        self.assertEqual("FAILED", session.status)
        self.assertTrue(any("INFERENCE_READY_NO_ACTIVE_RULES" in error for error in session.errors))

    def test_semantic_validator_reports_relation_type_mismatch(self):
        text = """
knowledge_base BadSignature
types:
  type Entity
  type GameObject : Entity
  type Unit : GameObject
  type Tile : GameObject
  context_type Context : Entity
  context_type Assertion : Context
  context_type Situation : Context
  context_type If : Context
  context_type Then : Context
relations:
  relation located_on(Unit, Tile)
individuals:
graphs:
  graph current_situation {
    concept u : Unit
    relation located_on(u, u)
  }
contexts:
  context current_ctx : Situation kind SITUATION uses current_situation
rules:
"""
        result = process_dsl_text(text, source_graph_id=SOURCE_GRAPH)
        self.assertIn("RELATION_SIGNATURE_TYPE_MISMATCH", {issue.code for issue in result.issues})


if __name__ == "__main__":
    unittest.main()
