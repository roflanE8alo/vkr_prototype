from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .model import (
    ConceptNode,
    DerivationRecord,
    Explanation,
    Graph,
    Hypothesis,
    InferenceSession,
    KnowledgeBase,
    RelationNode,
    Rule,
    Severity,
    ValidationIssue,
)
from .semantic import validate_knowledge_base_for_inference


@dataclass
class MatchResult:
    rule_id: str
    source_graph_id: str
    pattern_graph_id: str
    success: bool
    concept_mapping: dict[str, str] = field(default_factory=dict)
    relation_mapping: dict[str, str] = field(default_factory=dict)
    failure_reason: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.success

    @property
    def used_concept_ids(self) -> list[str]:
        return sorted(set(self.concept_mapping.values()))

    @property
    def used_relation_ids(self) -> list[str]:
        return sorted(set(self.relation_mapping.values()))


@dataclass
class RuleApplicationResult:
    id: str
    rule_id: str
    source_graph_id: str
    match_result: MatchResult
    produced_hypothesis_id: Optional[str] = None
    status: str = "not_applicable"
    failure_reason: Optional[str] = None


def _issue(code: str, message: str, severity: Severity, *, object_id: Optional[str] = None) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, severity=severity, object_id=object_id)


class GraphMatcher:
    def __init__(self, knowledge_base: KnowledgeBase):
        self.knowledge_base = knowledge_base

    def match(self, rule_id: str, pattern_graph: Graph, source_graph: Graph) -> MatchResult:
        pattern_concepts = sorted((pattern_graph.concept_nodes or {}).values(), key=lambda concept: concept.id or "")
        source_concepts = sorted((source_graph.concept_nodes or {}).values(), key=lambda concept: concept.id or "")
        candidates: dict[str, list[ConceptNode]] = {}

        for pattern_concept in pattern_concepts:
            concept_candidates = [
                source_concept
                for source_concept in source_concepts
                if self._concept_matches(pattern_concept, source_concept)
            ]
            concept_candidates.sort(key=lambda concept: concept.id or "")
            candidates[pattern_concept.id] = concept_candidates  # type: ignore[index]
            if not concept_candidates:
                return MatchResult(
                    rule_id=rule_id,
                    source_graph_id=source_graph.id or "",
                    pattern_graph_id=pattern_graph.id or "",
                    success=False,
                    failure_reason="NO_CANDIDATE_FOR_CONCEPT",
                )

        ordered_patterns = sorted(
            pattern_concepts,
            key=lambda concept: (
                0 if concept.individual_id else 1,
                len(candidates.get(concept.id, [])),
                concept.id or "",
            ),
        )
        mapping = self._backtrack(ordered_patterns, candidates, {}, set())
        if mapping is None:
            return MatchResult(
                rule_id=rule_id,
                source_graph_id=source_graph.id or "",
                pattern_graph_id=pattern_graph.id or "",
                success=False,
                failure_reason="MAPPING_INCONSISTENCY",
            )

        relation_mapping = self._match_relations(pattern_graph, source_graph, mapping)
        if relation_mapping is None:
            return MatchResult(
                rule_id=rule_id,
                source_graph_id=source_graph.id or "",
                pattern_graph_id=pattern_graph.id or "",
                success=False,
                concept_mapping=mapping,
                failure_reason="RELATION_MISMATCH",
            )

        return MatchResult(
            rule_id=rule_id,
            source_graph_id=source_graph.id or "",
            pattern_graph_id=pattern_graph.id or "",
            success=True,
            concept_mapping=mapping,
            relation_mapping=relation_mapping,
        )

    def _concept_matches(self, pattern_concept: ConceptNode, source_concept: ConceptNode) -> bool:
        type_hierarchy = self.knowledge_base.type_hierarchy
        if type_hierarchy is None:
            return pattern_concept.concept_type_id == source_concept.concept_type_id
        if not type_hierarchy.is_subtype(source_concept.concept_type_id, pattern_concept.concept_type_id):
            return False
        if pattern_concept.individual_id is not None:
            return source_concept.individual_id == pattern_concept.individual_id
        return True

    def _backtrack(
        self,
        ordered_patterns: list[ConceptNode],
        candidates: dict[str, list[ConceptNode]],
        mapping: dict[str, str],
        used_sources: set[str],
    ) -> Optional[dict[str, str]]:
        if len(mapping) == len(ordered_patterns):
            return dict(mapping)
        pattern_concept = ordered_patterns[len(mapping)]
        pattern_id = pattern_concept.id
        if pattern_id is None:
            return None
        for source_candidate in candidates.get(pattern_id, []):
            source_id = source_candidate.id
            if source_id is None or source_id in used_sources:
                continue
            mapping[pattern_id] = source_id
            used_sources.add(source_id)
            result = self._backtrack(ordered_patterns, candidates, mapping, used_sources)
            if result is not None:
                return result
            used_sources.remove(source_id)
            del mapping[pattern_id]
        return None

    def _match_relations(
        self,
        pattern_graph: Graph,
        source_graph: Graph,
        concept_mapping: dict[str, str],
    ) -> Optional[dict[str, str]]:
        pattern_relations = sorted((pattern_graph.relation_nodes or {}).values(), key=lambda relation: relation.id or "")
        source_relations = sorted((source_graph.relation_nodes or {}).values(), key=lambda relation: relation.id or "")
        used_sources: set[str] = set()
        relation_mapping: dict[str, str] = {}

        for pattern_relation in pattern_relations:
            found_source: Optional[RelationNode] = None
            for source_relation in source_relations:
                if source_relation.id in used_sources:
                    continue
                if pattern_relation.relation_type_id != source_relation.relation_type_id:
                    continue
                if len(pattern_relation.argument_concept_ids or []) != len(source_relation.argument_concept_ids or []):
                    continue
                expected_arguments = [
                    concept_mapping.get(pattern_arg)
                    for pattern_arg in (pattern_relation.argument_concept_ids or [])
                ]
                if expected_arguments == (source_relation.argument_concept_ids or []):
                    found_source = source_relation
                    break
            if found_source is None or pattern_relation.id is None or found_source.id is None:
                return None
            relation_mapping[pattern_relation.id] = found_source.id
            used_sources.add(found_source.id)
        return relation_mapping

class RuleApplier:
    def __init__(self, knowledge_base: KnowledgeBase):
        self.knowledge_base = knowledge_base
        self.matcher = GraphMatcher(knowledge_base)

    def apply_rule(self, rule: Rule, source_graph: Graph, sequence: int = 1) -> tuple[RuleApplicationResult, Optional[Graph], Optional[Hypothesis], Optional[DerivationRecord]]:
        result_id = f"app_{rule.id}_{source_graph.id}_{sequence}"
        if_context = self.knowledge_base.get_context(rule.if_context_id)
        then_context = self.knowledge_base.get_context(rule.then_context_id)
        if if_context is None or then_context is None:
            match = MatchResult(rule.id or "", source_graph.id or "", "", False, failure_reason="RULE_CONTEXT_MISSING")
            return (
                RuleApplicationResult(result_id, rule.id or "", source_graph.id or "", match, status="failed", failure_reason="RULE_CONTEXT_MISSING"),
                None,
                None,
                None,
            )

        if_graph = self._resolve_nested_graph(if_context.nested_graph_id)
        then_graph = self._resolve_nested_graph(then_context.nested_graph_id)
        if if_graph is None:
            match = MatchResult(rule.id or "", source_graph.id or "", "", False, failure_reason="IF_GRAPH_MISSING")
            return (
                RuleApplicationResult(result_id, rule.id or "", source_graph.id or "", match, status="failed", failure_reason="IF_GRAPH_MISSING"),
                None,
                None,
                None,
            )
        if then_graph is None:
            match = MatchResult(rule.id or "", source_graph.id or "", if_graph.id or "", False, failure_reason="THEN_GRAPH_MISSING")
            return (
                RuleApplicationResult(result_id, rule.id or "", source_graph.id or "", match, status="failed", failure_reason="THEN_GRAPH_MISSING"),
                None,
                None,
                None,
            )

        match = self.matcher.match(rule.id or "", if_graph, source_graph)
        if not match.success:
            return (
                RuleApplicationResult(result_id, rule.id or "", source_graph.id or "", match, status="not_applicable", failure_reason=match.failure_reason),
                None,
                None,
                None,
            )

        result_graph = Graph(id=f"derived_graph_{rule.id}_{source_graph.id}_{sequence}", name=f"derived_{rule.name}_{sequence}")
        instantiated = self._instantiate_then_graph(rule, if_graph, then_graph, source_graph, result_graph, match)
        if isinstance(instantiated, ValidationIssue):
            return (
                RuleApplicationResult(
                    result_id,
                    rule.id or "",
                    source_graph.id or "",
                    match,
                    status="failed",
                    failure_reason=instantiated.code,
                ),
                result_graph,
                None,
                None,
            )

        hypothesis_type = self._determine_hypothesis_type(rule, then_graph, instantiated["new_concept_ids"])
        hypothesis = Hypothesis(
            id=f"hyp_{rule.id}_{source_graph.id}_{sequence}",
            name=f"{rule.name}_hypothesis_{sequence}",
            hypothesis_type=hypothesis_type,
            graph_id=result_graph.id,
            status="generated",
            priority=rule.priority,
        )
        description = {
            "concept_mapping": match.concept_mapping,
            "relation_mapping": match.relation_mapping,
            "pattern_graph_id": if_graph.id,
            "source_graph_id": source_graph.id,
        }
        derivation = DerivationRecord(
            id=f"dr_{rule.id}_{source_graph.id}_{sequence}",
            rule_id=rule.id,
            source_graph_id=source_graph.id,
            matched_subgraph_description=str(description),
            produced_hypothesis_id=hypothesis.id,
            timestamp=datetime.now(timezone.utc),
        )
        application = RuleApplicationResult(
            id=result_id,
            rule_id=rule.id or "",
            source_graph_id=source_graph.id or "",
            match_result=match,
            produced_hypothesis_id=hypothesis.id,
            status="applied",
        )
        return application, result_graph, hypothesis, derivation

    def _resolve_nested_graph(self, graph_id: Optional[str]) -> Optional[Graph]:
        if graph_id is None or not isinstance(self.knowledge_base.graphs, dict):
            return None
        return self.knowledge_base.graphs.get(graph_id)

    def _instantiate_then_graph(
        self,
        rule: Rule,
        if_graph: Graph,
        then_graph: Graph,
        source_graph: Graph,
        result_graph: Graph,
        match: MatchResult,
    ) -> dict[str, Any] | ValidationIssue:
        if_label_to_pattern = {
            concept.label: concept
            for concept in (if_graph.concept_nodes or {}).values()
            if concept.label
        }
        then_to_result: dict[str, str] = {}
        new_concept_ids: list[str] = []

        for index, then_concept in enumerate(sorted((then_graph.concept_nodes or {}).values(), key=lambda concept: concept.id or ""), start=1):
            label = then_concept.label or f"then_{index}"
            result_concept_id = f"{result_graph.id}__{label}"
            individual_id = then_concept.individual_id
            if label in if_label_to_pattern:
                pattern_concept = if_label_to_pattern[label]
                source_concept_id = match.concept_mapping.get(pattern_concept.id)
                source_concept = (source_graph.concept_nodes or {}).get(source_concept_id) if source_concept_id else None
                if source_concept is not None and individual_id is None:
                    individual_id = source_concept.individual_id
            else:
                new_concept_ids.append(then_concept.id or "")
            result_concept = ConceptNode(
                id=result_concept_id,
                graph_id=result_graph.id,
                concept_type_id=then_concept.concept_type_id,
                individual_id=individual_id,
                label=then_concept.label,
            )
            result_graph.add_concept(result_concept)
            then_to_result[then_concept.id] = result_concept.id  # type: ignore[index]

        for index, then_relation in enumerate(sorted((then_graph.relation_nodes or {}).values(), key=lambda relation: relation.id or ""), start=1):
            argument_ids: list[str] = []
            for then_argument_id in then_relation.argument_concept_ids or []:
                result_argument_id = then_to_result.get(then_argument_id)
                if result_argument_id is None:
                    return _issue(
                        "THEN_RELATION_ARGUMENT_UNRESOLVED",
                        "Then relation argument could not be resolved during instantiation",
                        Severity.CRITICAL_ERROR,
                        object_id=then_relation.id,
                    )
                argument_ids.append(result_argument_id)
            relation = RelationNode(
                id=f"{result_graph.id}__rel_{index}_{then_relation.relation_type_id}",
                graph_id=result_graph.id,
                relation_type_id=then_relation.relation_type_id,
                argument_concept_ids=argument_ids,
            )
            result_graph.add_relation(relation)
        return {"then_to_result": then_to_result, "new_concept_ids": new_concept_ids}

    def _determine_hypothesis_type(self, rule: Rule, then_graph: Graph, new_concept_ids: list[str]) -> str:
        if len(new_concept_ids) == 1 and then_graph.concept_nodes:
            concept = then_graph.concept_nodes.get(new_concept_ids[0])
            if concept is not None:
                type_id = concept.concept_type_id
                if self.knowledge_base.type_hierarchy is not None:
                    resolved = self.knowledge_base.type_hierarchy.resolve_type_id(type_id)
                    if resolved is not None:
                        return self.knowledge_base.type_hierarchy.types_by_id[resolved].name  # type: ignore[index]
                return str(type_id)
        return "DerivedHypothesis"


class InferenceEngine:
    def __init__(self, knowledge_base: KnowledgeBase):
        self.knowledge_base = knowledge_base
        self.applier = RuleApplier(knowledge_base)
        self._sequence = 0

    def run(
        self,
        *,
        source_graph_id: Optional[str] = None,
    ) -> InferenceSession:
        session = InferenceSession(
            id=f"session_{self.knowledge_base.id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            knowledge_base_id=self.knowledge_base.id,
            source_graph_id=source_graph_id,
            status="CREATED",
        )

        report = validate_knowledge_base_for_inference(
            self.knowledge_base,
            source_graph_id=source_graph_id,
        )
        blocking = [issue for issue in report.issues if issue.severity != Severity.WARNING]
        if blocking:
            session.status = "FAILED"
            session.errors = [f"{issue.code}: {issue.message}" for issue in blocking]
            return session

        source_graph = self._resolve_source_graph(source_graph_id)
        if source_graph is None:
            session.status = "FAILED"
            session.errors.append("SOURCE_GRAPH_NOT_FOUND")
            return session
        session.source_graph_id = source_graph.id

        rules = self._select_rules()
        if not rules:
            session.status = "FAILED"
            session.errors.append("NO_ACTIVE_RULES")
            return session

        session.status = "RUNNING"
        for rule in rules:
            self._sequence += 1
            application, result_graph, hypothesis, derivation = self.applier.apply_rule(rule, source_graph, self._sequence)
            session.rule_application_results[application.id] = application
            if application.status == "applied" and result_graph is not None and hypothesis is not None and derivation is not None:
                session.generated_graphs[result_graph.id] = result_graph
                session.created_hypotheses[hypothesis.id] = hypothesis
                session.derivation_records[derivation.id] = derivation
                session.fired_rule_ids.append(rule.id)
                explanation = build_explanation(hypothesis, derivation, application.match_result, rule)
                session.explanations[explanation.id] = explanation

        applied_rule_ids = set(session.fired_rule_ids)
        for rule in rules:
            if rule.id not in applied_rule_ids:
                session.warnings.append(f"Active rule did not fire: {rule.id}")
        if not session.created_hypotheses:
            session.warnings.append("Situation did not satisfy any active rule")

        session.status = "COMPLETED_WITH_WARNINGS" if session.warnings else "COMPLETED"
        return session

    def _resolve_source_graph(self, source_graph_id: Optional[str]) -> Optional[Graph]:
        if source_graph_id is not None and isinstance(self.knowledge_base.graphs, dict):
            return self.knowledge_base.graphs.get(source_graph_id)
        return None

    def _select_rules(self) -> list[Rule]:
        rules = [rule for rule in self.knowledge_base.rules.values() if isinstance(rule, Rule) and rule.is_enabled]
        return sorted(rules, key=lambda rule: (-float(rule.priority), rule.name or "", rule.id or ""))

def build_explanation(
    hypothesis: Hypothesis,
    derivation: DerivationRecord,
    match_result: MatchResult,
    rule: Rule,
) -> Explanation:
    summary = (
        f"Rule {rule.name} fired on graph {match_result.source_graph_id}; "
        f"concepts {match_result.concept_mapping}; "
        f"produced hypothesis {hypothesis.id}."
    )
    return Explanation(
        id=f"ex_{hypothesis.id}",
        target_hypothesis_id=hypothesis.id,
        derivation_record_ids=[derivation.id],
        used_rule_ids=[rule.id],
        used_concept_ids=match_result.used_concept_ids,
        used_relation_ids=match_result.used_relation_ids,
        textual_summary=summary,
    )
