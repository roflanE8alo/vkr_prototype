from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .dsl import (
    AstContextDecl,
    AstDocument,
    AstGraphDecl,
    AstIndividualDecl,
    AstRelationDecl,
    AstRuleDecl,
    AstTypeDecl,
)
from .model import (
    ConceptNode,
    ConceptType,
    ContextConcept,
    ContextKind,
    Graph,
    Individual,
    KnowledgeBase,
    RelationNode,
    RelationType,
    Rule,
    Severity,
    TypeHierarchy,
    ValidationIssue,
)


@dataclass
class TranslationResult:
    knowledge_base: Optional[KnowledgeBase]
    issues: list[ValidationIssue] = field(default_factory=list)


def _issue(
    code: str,
    message: str,
    severity: Severity = Severity.CRITICAL_ERROR,
    *,
    object_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> ValidationIssue:
    return ValidationIssue(code, message, severity, object_id=object_id, details=details or {})


class AstToKnowledgeBaseTranslator:
    def __init__(self, document: AstDocument):
        self.document = document
        self.issues: list[ValidationIssue] = []
        self.type_registry: dict[str, ConceptType] = {}
        self.relation_registry: dict[str, RelationType] = {}
        self.individual_registry: dict[str, Individual] = {}
        self.graph_registry: dict[str, Graph] = {}
        self.context_registry: dict[str, ContextConcept] = {}
        self.rule_registry: dict[str, Rule] = {}
        self.graph_label_tables: dict[str, dict[str, ConceptNode]] = {}

    def translate(self) -> TranslationResult:
        self._translate_types()
        type_hierarchy = TypeHierarchy.from_types(self.type_registry.values(), self._infer_root_type_id())
        self._translate_relations(type_hierarchy)
        self._translate_individuals(type_hierarchy)
        self._translate_graphs()

        kb = KnowledgeBase(
            id=self.document.kb_name,
            name=self.document.kb_name,
            type_hierarchy=type_hierarchy,
            relation_types=self.relation_registry,
            individuals=self.individual_registry,
            graphs=self.graph_registry,
        )
        self._translate_contexts()
        self._translate_rules(kb)
        return TranslationResult(knowledge_base=kb, issues=self.issues)

    def _section_items(self, section_name: str) -> list[Any]:
        section = self.document.sections_by_type.get(section_name)
        return list(section.items) if section is not None else []

    def _translate_types(self) -> None:
        type_decls = [item for item in self._section_items("types") if isinstance(item, AstTypeDecl)]
        for decl in type_decls:
            if decl.name in self.type_registry:
                self.issues.append(_issue("TRANSLATION_DUPLICATE_TYPE", "Duplicate concept type declaration", object_id=decl.name))
                continue
            self.type_registry[decl.name] = ConceptType(
                id=decl.name,
                name=decl.name,
                parent_ids=list(decl.parent_names),
                is_context_type=decl.is_context_type,
            )

        for decl in type_decls:
            concept_type = self.type_registry.get(decl.name)
            if concept_type is None:
                continue
            resolved_parents: list[str] = []
            for parent_name in decl.parent_names:
                parent = self.type_registry.get(parent_name)
                if parent is None:
                    self.issues.append(
                        _issue(
                            "TRANSLATION_UNKNOWN_PARENT_TYPE",
                            "Unknown parent concept type referenced by type declaration",
                            object_id=decl.name,
                            details={"parent_name": parent_name},
                        )
                    )
                    resolved_parents.append(parent_name)
                else:
                    resolved_parents.append(parent.id or parent_name)
            concept_type.parent_ids = resolved_parents

    def _infer_root_type_id(self) -> Optional[str]:
        if "Entity" in self.type_registry:
            return "Entity"
        roots = [type_.id for type_ in self.type_registry.values() if not type_.parent_ids]
        return roots[0] if roots else None

    def _translate_relations(self, type_hierarchy: TypeHierarchy) -> None:
        for decl in self._section_items("relations"):
            if not isinstance(decl, AstRelationDecl):
                continue
            if decl.name in self.relation_registry:
                self.issues.append(_issue("TRANSLATION_DUPLICATE_RELATION", "Duplicate relation declaration", object_id=decl.name))
                continue
            signature: list[str] = []
            for type_ref in decl.signature:
                type_id = type_hierarchy.resolve_type_id(type_ref.name)
                if type_id is None:
                    self.issues.append(
                        _issue(
                            "TRANSLATION_UNKNOWN_SIGNATURE_TYPE",
                            "Unknown concept type in relation signature",
                            object_id=decl.name,
                            details={"type_name": type_ref.name},
                        )
                    )
                    signature.append(type_ref.name)
                else:
                    signature.append(type_id)
            self.relation_registry[decl.name] = RelationType(
                id=decl.name,
                name=decl.name,
                arity=len(signature),
                signature=signature,
            )

    def _translate_individuals(self, type_hierarchy: TypeHierarchy) -> None:
        for decl in self._section_items("individuals"):
            if not isinstance(decl, AstIndividualDecl):
                continue
            if decl.name in self.individual_registry:
                self.issues.append(_issue("TRANSLATION_DUPLICATE_INDIVIDUAL", "Duplicate individual declaration", object_id=decl.name))
                continue
            base_type_id = type_hierarchy.resolve_type_id(decl.base_type.name)
            if base_type_id is None:
                self.issues.append(
                    _issue(
                        "TRANSLATION_UNKNOWN_INDIVIDUAL_TYPE",
                        "Unknown base type referenced by individual",
                        object_id=decl.name,
                        details={"type_name": decl.base_type.name},
                    )
                )
                base_type_id = decl.base_type.name
            self.individual_registry[decl.name] = Individual(id=decl.name, name=decl.name, base_type_id=base_type_id)

    def _translate_graphs(self) -> None:
        for decl in self._section_items("graphs"):
            if not isinstance(decl, AstGraphDecl):
                continue
            if decl.name in self.graph_registry:
                self.issues.append(_issue("TRANSLATION_DUPLICATE_GRAPH", "Duplicate graph declaration", object_id=decl.name))
                continue
            self.graph_registry[decl.name] = Graph(id=decl.name, name=decl.name)
            self.graph_label_tables[decl.name] = {}

        for decl in self._section_items("graphs"):
            if isinstance(decl, AstGraphDecl) and decl.name in self.graph_registry:
                self._translate_graph_contents(decl, self.graph_registry[decl.name])

    def _translate_graph_contents(self, decl: AstGraphDecl, graph: Graph) -> None:
        labels = self.graph_label_tables[decl.name]
        for concept_decl in decl.concepts:
            if concept_decl.label in labels:
                self.issues.append(
                    _issue(
                        "TRANSLATION_DUPLICATE_CONCEPT_LABEL",
                        "Duplicate concept label inside graph",
                        object_id=concept_decl.label,
                        details={"graph": decl.name},
                    )
                )
                continue
            if concept_decl.type_ref.name not in self.type_registry:
                self.issues.append(
                    _issue(
                        "TRANSLATION_UNKNOWN_CONCEPT_TYPE",
                        "Unknown concept type referenced by graph concept",
                        object_id=concept_decl.label,
                        details={"type_name": concept_decl.type_ref.name, "graph": decl.name},
                    )
                )
            if concept_decl.individual_ref and concept_decl.individual_ref not in self.individual_registry:
                self.issues.append(
                    _issue(
                        "TRANSLATION_UNKNOWN_INDIVIDUAL_REFERENCE",
                        "Unknown individual referenced by graph concept",
                        object_id=concept_decl.label,
                        details={"individual": concept_decl.individual_ref, "graph": decl.name},
                    )
                )
            concept = ConceptNode(
                id=f"{decl.name}__{concept_decl.label}",
                graph_id=decl.name,
                concept_type_id=concept_decl.type_ref.name,
                individual_id=concept_decl.individual_ref,
                label=concept_decl.label,
            )
            graph.add_concept(concept)
            labels[concept_decl.label] = concept

        for index, relation_decl in enumerate(decl.relations, start=1):
            if relation_decl.relation_name not in self.relation_registry:
                self.issues.append(
                    _issue(
                        "TRANSLATION_UNKNOWN_RELATION_REFERENCE",
                        "Unknown relation referenced by graph relation",
                        object_id=relation_decl.relation_name,
                        details={"graph": decl.name},
                    )
                )
            argument_ids: list[str] = []
            for argument in relation_decl.arguments:
                concept = labels.get(argument.label)
                if concept is None:
                    self.issues.append(
                        _issue(
                            "TRANSLATION_UNKNOWN_LOCAL_CONCEPT_LABEL",
                            "Unknown local concept label referenced by graph relation",
                            object_id=argument.label,
                            details={"graph": decl.name, "relation": relation_decl.relation_name},
                        )
                    )
                    argument_ids.append(argument.label)
                else:
                    argument_ids.append(concept.id or argument.label)
            graph.add_relation(
                RelationNode(
                    id=f"{decl.name}__rel_{index}_{relation_decl.relation_name}",
                    graph_id=decl.name,
                    relation_type_id=relation_decl.relation_name,
                    argument_concept_ids=argument_ids,
                )
            )

    def _translate_contexts(self) -> None:
        root_graph = self._ensure_graph("__context_graph", "contexts")
        for decl in self._section_items("contexts"):
            if not isinstance(decl, AstContextDecl):
                continue
            if decl.name in self.context_registry:
                self.issues.append(_issue("TRANSLATION_DUPLICATE_CONTEXT", "Duplicate context declaration", object_id=decl.name))
                continue
            if decl.type_name not in self.type_registry:
                self.issues.append(_issue("TRANSLATION_UNKNOWN_CONTEXT_TYPE", "Unknown context type", object_id=decl.name, details={"type_name": decl.type_name}))
            nested_graph = self.graph_registry.get(decl.graph_name)
            if nested_graph is None:
                self.issues.append(_issue("TRANSLATION_UNKNOWN_CONTEXT_GRAPH", "Unknown graph referenced by context", object_id=decl.name, details={"graph_name": decl.graph_name}))
                nested_graph_id = decl.graph_name
            else:
                nested_graph_id = nested_graph.id
                nested_graph.owner_context_id = decl.name
            try:
                context_kind: ContextKind | str = ContextKind[decl.context_kind]
            except KeyError:
                context_kind = decl.context_kind
                self.issues.append(_issue("TRANSLATION_UNKNOWN_CONTEXT_KIND", "Unknown ContextKind value", object_id=decl.name, details={"context_kind": decl.context_kind}))
            context = ContextConcept(
                id=decl.name,
                graph_id=root_graph.id,
                concept_type_id=decl.type_name,
                label=decl.name,
                nested_graph_id=nested_graph_id,
                context_kind=context_kind,
            )
            root_graph.add_concept(context)
            self.context_registry[decl.name] = context

    def _ensure_graph(self, graph_id: str, name: str) -> Graph:
        graph = self.graph_registry.get(graph_id)
        if graph is None:
            graph = Graph(id=graph_id, name=name)
            self.graph_registry[graph_id] = graph
        return graph

    def _translate_rules(self, kb: KnowledgeBase) -> None:
        for decl in self._section_items("rules"):
            if not isinstance(decl, AstRuleDecl):
                continue
            if decl.name in self.rule_registry:
                self.issues.append(_issue("TRANSLATION_DUPLICATE_RULE", "Duplicate rule declaration", object_id=decl.name))
                continue
            if decl.if_context_name and decl.if_context_name not in self.context_registry:
                self.issues.append(_issue("TRANSLATION_UNKNOWN_RULE_IF_CONTEXT", "Unknown if-context referenced by rule", object_id=decl.name))
            if decl.then_context_name and decl.then_context_name not in self.context_registry:
                self.issues.append(_issue("TRANSLATION_UNKNOWN_RULE_THEN_CONTEXT", "Unknown then-context referenced by rule", object_id=decl.name))
            rule = Rule(
                id=decl.name,
                name=decl.name,
                if_context_id=decl.if_context_name,
                then_context_id=decl.then_context_name,
                priority=decl.priority,
                is_enabled=decl.enabled,
            )
            self.rule_registry[decl.name] = rule
            kb.rules[rule.id or decl.name] = rule


def translate_ast(document: AstDocument) -> TranslationResult:
    return AstToKnowledgeBaseTranslator(document).translate()
