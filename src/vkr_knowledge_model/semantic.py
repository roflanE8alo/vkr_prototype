from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .model import (
    ConceptNode,
    ContextConcept,
    ContextKind,
    Graph,
    KnowledgeBase,
    RelationNode,
    Rule,
    Severity,
    TypeHierarchy,
    ValidationIssue,
    _coerce_context_kind,
)


@dataclass
class ValidationReport:
    knowledge_base_id: Optional[str]
    issues: list[ValidationIssue] = field(default_factory=list)
    is_valid: bool = False
    is_usable_for_inference: bool = False


def _issue(code: str, message: str, severity: Severity, *, object_id: Optional[str] = None) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, severity=severity, object_id=object_id)


def validate_knowledge_base_for_inference(
    knowledge_base: KnowledgeBase,
    *,
    source_graph_id: Optional[str] = None,
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    issues.extend(_validate_knowledge_base_shape(knowledge_base))
    issues.extend(_validate_graphs(knowledge_base))
    issues.extend(_validate_contexts_and_rules(knowledge_base))
    issues.extend(_validate_inference_readiness(knowledge_base, source_graph_id))
    has_blocking = any(issue.severity != Severity.WARNING for issue in issues)
    return ValidationReport(
        knowledge_base_id=knowledge_base.id,
        issues=issues,
        is_valid=not has_blocking,
        is_usable_for_inference=not has_blocking,
    )


def _validate_knowledge_base_shape(knowledge_base: KnowledgeBase) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if knowledge_base.type_hierarchy is None:
        issues.append(_issue("KNOWLEDGE_BASE_TYPE_HIERARCHY_REQUIRED", "KnowledgeBase must define TypeHierarchy", Severity.CRITICAL_ERROR))
    if not isinstance(knowledge_base.relation_types, dict):
        issues.append(_issue("KNOWLEDGE_BASE_RELATIONS_REQUIRED", "KnowledgeBase must define relation_types", Severity.CRITICAL_ERROR))
    if not isinstance(knowledge_base.individuals, dict):
        issues.append(_issue("KNOWLEDGE_BASE_INDIVIDUALS_REQUIRED", "KnowledgeBase must define individuals", Severity.CRITICAL_ERROR))
    if not isinstance(knowledge_base.graphs, dict):
        issues.append(_issue("KNOWLEDGE_BASE_GRAPHS_REQUIRED", "KnowledgeBase must define graphs", Severity.CRITICAL_ERROR))
    return issues


def _validate_graphs(knowledge_base: KnowledgeBase) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    type_hierarchy = knowledge_base.type_hierarchy
    if type_hierarchy is None:
        return issues

    for graph_id, graph in knowledge_base.graphs.items():
        if not isinstance(graph, Graph):
            issues.append(_issue("GRAPH_ENTRY_INVALID", "Graph registry must contain Graph objects", Severity.CRITICAL_ERROR, object_id=str(graph_id)))
            continue
        if graph.id != graph_id:
            issues.append(_issue("GRAPH_ID_MISMATCH", "Graph key must match Graph.id", Severity.CRITICAL_ERROR, object_id=str(graph.id)))
        for concept in graph.concept_nodes.values():
            issues.extend(_validate_concept(concept, graph, knowledge_base, type_hierarchy))
        for relation in graph.relation_nodes.values():
            issues.extend(_validate_relation(relation, graph, knowledge_base, type_hierarchy))
    return issues


def _validate_concept(
    concept: ConceptNode,
    graph: Graph,
    knowledge_base: KnowledgeBase,
    type_hierarchy: TypeHierarchy,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if concept.graph_id != graph.id:
        issues.append(_issue("CONCEPT_NODE_GRAPH_MISMATCH", "Concept graph_id must match owning graph", Severity.CRITICAL_ERROR, object_id=concept.id))
    concept_type_id = type_hierarchy.resolve_type_id(concept.concept_type_id)
    if concept_type_id is None:
        issues.append(_issue("UNKNOWN_CONCEPT_TYPE_IN_CONCEPT_NODE", "Unknown concept type", Severity.CRITICAL_ERROR, object_id=concept.id))
        return issues

    concept_type = type_hierarchy.types_by_id.get(concept_type_id)
    if concept_type is not None and concept_type.is_context_type and not isinstance(concept, ContextConcept):
        issues.append(_issue("CONTEXT_TYPE_USED_BY_NON_CONTEXT_CONCEPT", "Context type must use ContextConcept", Severity.MODEL_ERROR, object_id=concept.id))

    if concept.individual_id:
        individual = knowledge_base.individuals.get(concept.individual_id)
        if individual is None:
            issues.append(_issue("UNKNOWN_INDIVIDUAL_IN_CONCEPT_NODE", "Unknown individual referenced by concept", Severity.CRITICAL_ERROR, object_id=concept.id))
        elif not type_hierarchy.is_subtype(individual.base_type_id, concept.concept_type_id):
            issues.append(_issue("CONCEPT_NODE_INDIVIDUAL_TYPE_INCOMPATIBLE", "Concept type is incompatible with individual type", Severity.MODEL_ERROR, object_id=concept.id))

    if isinstance(concept, ContextConcept):
        kind = _coerce_context_kind(concept.context_kind)
        if kind is None:
            issues.append(_issue("CONTEXT_CONCEPT_KIND_INVALID", "ContextConcept must define valid ContextKind", Severity.CRITICAL_ERROR, object_id=concept.id))
        elif not type_hierarchy.is_context_kind_compatible(concept_type_id, kind):
            issues.append(_issue("CONTEXT_KIND_TYPE_INCOMPATIBLE", "Context kind does not match context type", Severity.MODEL_ERROR, object_id=concept.id))
        if not concept.nested_graph_id or concept.nested_graph_id not in knowledge_base.graphs:
            issues.append(_issue("UNKNOWN_NESTED_GRAPH_IN_CONTEXT_CONCEPT", "ContextConcept must reference existing nested graph", Severity.CRITICAL_ERROR, object_id=concept.id))
    return issues


def _validate_relation(
    relation: RelationNode,
    graph: Graph,
    knowledge_base: KnowledgeBase,
    type_hierarchy: TypeHierarchy,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if relation.graph_id != graph.id:
        issues.append(_issue("RELATION_NODE_GRAPH_MISMATCH", "Relation graph_id must match owning graph", Severity.CRITICAL_ERROR, object_id=relation.id))
    relation_type = knowledge_base.relation_types.get(relation.relation_type_id or "")
    if relation_type is None:
        issues.append(_issue("UNKNOWN_RELATION_TYPE_IN_RELATION_NODE", "Unknown relation type", Severity.CRITICAL_ERROR, object_id=relation.id))
        return issues

    arguments = relation.argument_concept_ids or []
    signature = relation_type.signature or []
    if relation_type.arity != len(arguments) or len(signature) != len(arguments):
        issues.append(_issue("RELATION_NODE_ARITY_MISMATCH", "Relation argument count does not match arity", Severity.CRITICAL_ERROR, object_id=relation.id))
        return issues

    actual_types: list[str] = []
    for argument_id in arguments:
        argument = graph.concept_nodes.get(argument_id)
        if argument is None:
            issues.append(_issue("UNKNOWN_CONCEPT_IN_RELATION_NODE_ARGUMENTS", "Relation references unknown concept", Severity.CRITICAL_ERROR, object_id=relation.id))
        else:
            actual_types.append(argument.concept_type_id or "")

    if len(actual_types) == len(signature):
        for index, (actual, expected) in enumerate(zip(actual_types, signature)):
            if not type_hierarchy.is_subtype(actual, expected):
                issues.append(
                    ValidationIssue(
                        "RELATION_SIGNATURE_TYPE_MISMATCH",
                        "Relation argument type does not match signature",
                        Severity.MODEL_ERROR,
                        object_id=relation.id,
                        details={"index": index, "expected": expected, "actual": actual},
                    )
                )
    return issues


def _validate_contexts_and_rules(knowledge_base: KnowledgeBase) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for rule in knowledge_base.rules.values():
        if not isinstance(rule, Rule):
            continue
        if_context = knowledge_base.get_context(rule.if_context_id)
        then_context = knowledge_base.get_context(rule.then_context_id)
        if if_context is None:
            issues.append(_issue("RULE_UNKNOWN_IF_CONTEXT", "Rule references unknown IF context", Severity.CRITICAL_ERROR, object_id=rule.id))
        elif _coerce_context_kind(if_context.context_kind) != ContextKind.IF:
            issues.append(_issue("RULE_IF_CONTEXT_INVALID_KIND", "Rule IF context has invalid kind", Severity.MODEL_ERROR, object_id=rule.id))
        if then_context is None:
            issues.append(_issue("RULE_UNKNOWN_THEN_CONTEXT", "Rule references unknown THEN context", Severity.CRITICAL_ERROR, object_id=rule.id))
        elif _coerce_context_kind(then_context.context_kind) != ContextKind.THEN:
            issues.append(_issue("RULE_THEN_CONTEXT_INVALID_KIND", "Rule THEN context has invalid kind", Severity.MODEL_ERROR, object_id=rule.id))
        if rule.is_enabled and if_context is not None and then_context is not None:
            issues.extend(_validate_rule_graphs(rule, if_context, then_context, knowledge_base))
    return issues


def _validate_rule_graphs(
    rule: Rule,
    if_context: ContextConcept,
    then_context: ContextConcept,
    knowledge_base: KnowledgeBase,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if_graph = knowledge_base.graphs.get(if_context.nested_graph_id or "")
    then_graph = knowledge_base.graphs.get(then_context.nested_graph_id or "")
    if if_graph is None:
        issues.append(_issue("ACTIVE_RULE_IF_GRAPH_MISSING", "Active rule IF graph is missing", Severity.CRITICAL_ERROR, object_id=rule.id))
    elif not if_graph.concept_nodes and not if_graph.relation_nodes:
        issues.append(_issue("ACTIVE_RULE_IF_GRAPH_EMPTY", "Active rule IF graph is empty", Severity.MODEL_ERROR, object_id=rule.id))
    if then_graph is None:
        issues.append(_issue("ACTIVE_RULE_THEN_GRAPH_MISSING", "Active rule THEN graph is missing", Severity.CRITICAL_ERROR, object_id=rule.id))
    elif not then_graph.concept_nodes and not then_graph.relation_nodes:
        issues.append(_issue("ACTIVE_RULE_THEN_GRAPH_EMPTY", "Active rule THEN graph is empty", Severity.MODEL_ERROR, object_id=rule.id))
    return issues


def _validate_inference_readiness(
    knowledge_base: KnowledgeBase,
    source_graph_id: Optional[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if source_graph_id is None:
        issues.append(_issue("INFERENCE_READY_SOURCE_GRAPH_REQUIRED", "Compact inference requires an explicit source_graph_id", Severity.CRITICAL_ERROR, object_id=knowledge_base.id))
    elif source_graph_id not in knowledge_base.graphs:
        issues.append(_issue("INFERENCE_READY_SOURCE_GRAPH_NOT_FOUND", "Source graph for inference was not found", Severity.CRITICAL_ERROR, object_id=source_graph_id))

    active_rules = [rule for rule in knowledge_base.rules.values() if isinstance(rule, Rule) and rule.is_enabled]
    if not active_rules:
        issues.append(_issue("INFERENCE_READY_NO_ACTIVE_RULES", "Inference requires at least one active rule", Severity.CRITICAL_ERROR, object_id=knowledge_base.id))
    return issues
