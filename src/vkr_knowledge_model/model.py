from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Optional


class Severity(str, Enum):
    CRITICAL_ERROR = "CRITICAL_ERROR"
    MODEL_ERROR = "MODEL_ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: Severity
    object_id: Optional[str] = None
    path: Optional[str] = None
    location: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)


class ContextKind(str, Enum):
    ASSERTION = "ASSERTION"
    SITUATION = "SITUATION"
    IF = "IF"
    THEN = "THEN"


CONTEXT_KIND_TO_TYPE_NAME = {
    ContextKind.ASSERTION: "Assertion",
    ContextKind.SITUATION: "Situation",
    ContextKind.IF: "If",
    ContextKind.THEN: "Then",
}


def _coerce_context_kind(value: Any) -> Optional[ContextKind]:
    if value is None:
        return None
    if isinstance(value, ContextKind):
        return value
    if isinstance(value, str):
        try:
            return ContextKind(value.upper())
        except ValueError:
            return None
    return None


@dataclass
class ConceptType:
    id: Optional[str]
    name: Optional[str]
    parent_ids: list[str] = field(default_factory=list)
    is_context_type: bool = False


@dataclass
class RelationType:
    id: Optional[str]
    name: Optional[str]
    arity: Optional[int]
    signature: Optional[list[str]]


@dataclass
class TypeHierarchy:
    types_by_id: dict[str, ConceptType] = field(default_factory=dict)
    types_by_name: dict[str, ConceptType] = field(default_factory=dict)
    root_type_id: Optional[str] = None

    @classmethod
    def from_types(cls, concept_types: Iterable[ConceptType], root_type_id: Optional[str] = None) -> TypeHierarchy:
        by_id: dict[str, ConceptType] = {}
        by_name: dict[str, ConceptType] = {}
        for concept_type in concept_types:
            if concept_type.id is not None:
                by_id[concept_type.id] = concept_type
            if concept_type.name is not None:
                by_name[concept_type.name] = concept_type
        return cls(by_id, by_name, root_type_id)

    def resolve_type_id(self, type_ref: Any) -> Optional[str]:
        if isinstance(type_ref, ConceptType):
            return type_ref.id
        if type_ref in self.types_by_id:
            return type_ref
        if type_ref in self.types_by_name:
            return self.types_by_name[type_ref].id
        return None

    def is_subtype(self, a: Any, b: Any) -> bool:
        a_id = self.resolve_type_id(a)
        b_id = self.resolve_type_id(b)
        if a_id is None or b_id is None:
            return False
        if a_id == b_id:
            return True
        visited: set[str] = set()
        stack = [a_id]
        while stack:
            current_id = stack.pop()
            if current_id in visited:
                continue
            visited.add(current_id)
            current = self.types_by_id.get(current_id)
            if current is None:
                continue
            for parent_id in current.parent_ids:
                resolved_parent_id = self.resolve_type_id(parent_id)
                if resolved_parent_id == b_id:
                    return True
                if resolved_parent_id is not None:
                    stack.append(resolved_parent_id)
        return False

    def is_context_kind_compatible(self, type_ref: Any, context_kind: Any) -> bool:
        resolved_type_id = self.resolve_type_id(type_ref)
        kind = _coerce_context_kind(context_kind)
        if resolved_type_id is None or kind is None:
            return False
        concept_type = self.types_by_id.get(resolved_type_id)
        if concept_type is None:
            return False
        expected_type_name = CONTEXT_KIND_TO_TYPE_NAME[kind]
        if concept_type.name == expected_type_name:
            return True
        expected_type = self.types_by_name.get(expected_type_name)
        return expected_type is not None and self.is_subtype(resolved_type_id, expected_type.id)


@dataclass
class Individual:
    id: Optional[str]
    name: Optional[str]
    base_type_id: Optional[str]


@dataclass
class ConceptNode:
    id: Optional[str]
    graph_id: Optional[str]
    concept_type_id: Optional[str]
    individual_id: Optional[str] = None
    label: Optional[str] = None


@dataclass
class ContextConcept(ConceptNode):
    nested_graph_id: Optional[str] = None
    context_kind: Optional[ContextKind | str] = None


@dataclass
class RelationNode:
    id: Optional[str]
    graph_id: Optional[str]
    relation_type_id: Optional[str]
    argument_concept_ids: Optional[list[str]]


@dataclass
class Graph:
    id: Optional[str]
    name: Optional[str] = None
    concept_nodes: dict[str, ConceptNode] = field(default_factory=dict)
    relation_nodes: dict[str, RelationNode] = field(default_factory=dict)
    owner_context_id: Optional[str] = None

    def add_concept(self, concept_node: ConceptNode) -> None:
        self.concept_nodes[concept_node.id] = concept_node  # type: ignore[index]

    def add_relation(self, relation_node: RelationNode) -> None:
        self.relation_nodes[relation_node.id] = relation_node  # type: ignore[index]


@dataclass
class Rule:
    id: Optional[str]
    name: Optional[str]
    if_context_id: Optional[str]
    then_context_id: Optional[str]
    priority: int | float = 0
    is_enabled: bool = True


@dataclass
class Hypothesis:
    id: Optional[str]
    name: Optional[str]
    hypothesis_type: Optional[str] = "general"
    graph_id: Optional[str] = None
    status: str = "generated"
    priority: int | float = 0


@dataclass
class DerivationRecord:
    id: Optional[str]
    rule_id: Optional[str]
    source_graph_id: Optional[str]
    matched_subgraph_description: Optional[str]
    produced_hypothesis_id: Optional[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Explanation:
    id: Optional[str]
    target_hypothesis_id: Optional[str]
    derivation_record_ids: list[str] = field(default_factory=list)
    used_rule_ids: list[str] = field(default_factory=list)
    used_concept_ids: list[str] = field(default_factory=list)
    used_relation_ids: list[str] = field(default_factory=list)
    textual_summary: str = ""


@dataclass
class InferenceSession:
    id: Optional[str]
    knowledge_base_id: Optional[str]
    source_graph_id: Optional[str] = None
    created_hypotheses: dict[str, Hypothesis] = field(default_factory=dict)
    derivation_records: dict[str, DerivationRecord] = field(default_factory=dict)
    explanations: dict[str, Explanation] = field(default_factory=dict)
    generated_graphs: dict[str, Graph] = field(default_factory=dict)
    status: str = "created"
    warnings: list[str] = field(default_factory=list)
    rule_application_results: dict[str, Any] = field(default_factory=dict)
    fired_rule_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class KnowledgeBase:
    id: Optional[str]
    name: Optional[str]
    type_hierarchy: Optional[TypeHierarchy]
    relation_types: dict[str, RelationType]
    individuals: dict[str, Individual]
    graphs: dict[str, Graph]
    rules: dict[str, Rule] = field(default_factory=dict)

    def all_concept_nodes(self) -> dict[str, ConceptNode]:
        concepts: dict[str, ConceptNode] = {}
        for graph in self.graphs.values():
            concepts.update(graph.concept_nodes)
        return concepts

    def get_context(self, context_id: Optional[str]) -> Optional[ContextConcept]:
        if context_id is None:
            return None
        concept = self.all_concept_nodes().get(context_id)
        return concept if isinstance(concept, ContextConcept) else None
