from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .dsl import AstDocument, AstValidationResult, ParseResult, parse_text, validate_ast
from .model import KnowledgeBase, ValidationIssue
from .semantic import ValidationReport, validate_knowledge_base_for_inference
from .translator import TranslationResult, translate_ast


@dataclass
class ProcessingResult:
    parse_result: ParseResult
    ast_validation: AstValidationResult
    translation: Optional[TranslationResult]
    semantic_report: Optional[ValidationReport]

    @property
    def document(self) -> Optional[AstDocument]:
        return self.parse_result.document

    @property
    def knowledge_base(self) -> Optional[KnowledgeBase]:
        return self.translation.knowledge_base if self.translation else None

    @property
    def issues(self) -> list[ValidationIssue]:
        result: list[ValidationIssue] = []
        result.extend(self.parse_result.errors)
        result.extend(self.ast_validation.issues)
        if self.translation is not None:
            result.extend(self.translation.issues)
        if self.semantic_report is not None:
            result.extend(self.semantic_report.issues)
        return result


def process_dsl_text(
    text: str,
    *,
    filename: Optional[str] = None,
    source_graph_id: Optional[str] = None,
) -> ProcessingResult:
    parse_result = parse_text(text, filename)
    ast_validation = validate_ast(parse_result.document)
    translation: Optional[TranslationResult] = None
    semantic_report: Optional[ValidationReport] = None
    if parse_result.document is not None and not parse_result.errors and not ast_validation.issues:
        translation = translate_ast(parse_result.document)
        if translation.knowledge_base is not None:
            semantic_report = validate_knowledge_base_for_inference(
                translation.knowledge_base,
                source_graph_id=source_graph_id,
            )
    return ProcessingResult(
        parse_result=parse_result,
        ast_validation=ast_validation,
        translation=translation,
        semantic_report=semantic_report,
    )


def process_dsl_file(
    path: str,
    *,
    source_graph_id: Optional[str] = None,
) -> ProcessingResult:
    with open(path, "r", encoding="utf-8") as file:
        text = file.read()
    return process_dsl_text(
        text,
        filename=path,
        source_graph_id=source_graph_id,
    )
