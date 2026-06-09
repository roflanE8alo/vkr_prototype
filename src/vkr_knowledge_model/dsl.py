from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .model import Severity, ValidationIssue


SECTION_NAMES = {"types", "relations", "individuals", "graphs", "contexts", "rules"}
MANDATORY_SECTIONS = {"types", "relations", "individuals", "graphs"}


@dataclass(frozen=True)
class Token:
    kind: str
    value: Any
    line: int = 0
    column: int = 0
    filename: Optional[str] = None


@dataclass
class ParseResult:
    document: Optional["AstDocument"]
    errors: list[ValidationIssue] = field(default_factory=list)


@dataclass
class AstValidationResult:
    document: Optional["AstDocument"]
    issues: list[ValidationIssue] = field(default_factory=list)


@dataclass
class AstNode:
    kind: str


@dataclass
class AstTypeRef(AstNode):
    name: str = ""


@dataclass
class AstConceptRef(AstNode):
    label: str = ""


@dataclass
class AstTypeDecl(AstNode):
    name: str = ""
    parent_names: list[str] = field(default_factory=list)
    is_context_type: bool = False


@dataclass
class AstRelationDecl(AstNode):
    name: str = ""
    signature: list[AstTypeRef] = field(default_factory=list)


@dataclass
class AstIndividualDecl(AstNode):
    name: str = ""
    base_type: AstTypeRef = None  # type: ignore[assignment]


@dataclass
class AstConceptDecl(AstNode):
    label: str = ""
    type_ref: AstTypeRef = None  # type: ignore[assignment]
    individual_ref: Optional[str] = None


@dataclass
class AstRelationStmt(AstNode):
    relation_name: str = ""
    arguments: list[AstConceptRef] = field(default_factory=list)


@dataclass
class AstGraphDecl(AstNode):
    name: str = ""
    concepts: list[AstConceptDecl] = field(default_factory=list)
    relations: list[AstRelationStmt] = field(default_factory=list)


@dataclass
class AstContextDecl(AstNode):
    name: str = ""
    type_name: str = ""
    context_kind: str = ""
    graph_name: str = ""


@dataclass
class AstRuleDecl(AstNode):
    name: str = ""
    if_context_name: Optional[str] = None
    then_context_name: Optional[str] = None
    priority: int | float = 0
    enabled: bool = True


@dataclass
class AstSectionNode(AstNode):
    section_name: str = ""
    items: list[AstNode] = field(default_factory=list)


@dataclass
class AstDocument(AstNode):
    kb_name: str = ""
    sections: list[AstSectionNode] = field(default_factory=list)
    sections_by_type: dict[str, AstSectionNode] = field(default_factory=dict)


def _issue(code: str, message: str, severity: Severity, token: Optional[Token] = None) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        message=message,
        severity=severity,
        path=f"{token.filename}:{token.line}:{token.column}" if token and token.filename else None,
        location=f"{token.line}:{token.column}" if token else None,
        details={"token": token.value} if token else {},
    )


class Lexer:
    def __init__(self, text: str, filename: Optional[str] = None):
        self.text = text
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.column = 1
        self.errors: list[ValidationIssue] = []

    def tokenize(self) -> tuple[list[Token], list[ValidationIssue]]:
        tokens: list[Token] = []
        while not self._at_end():
            ch = self._peek_char()
            if ch in " \t\r":
                self._advance()
                continue
            if ch == "\n":
                self._advance()
                continue
            if ch == "#":
                self._read_comment()
                continue
            if ch.isalpha():
                tokens.append(self._read_identifier())
                continue
            if ch.isdigit():
                token = self._read_number_or_invalid_identifier()
                if token is not None:
                    tokens.append(token)
                continue
            if ch == '"':
                token = self._read_string()
                if token is not None:
                    tokens.append(token)
                continue
            if ch in ":{}(),=[]":
                tokens.append(self._make_token(ch, ch))
                self._advance()
                continue

            token = self._make_token("INVALID", ch)
            self._advance()
            self.errors.append(_issue("LEX_INVALID_CHARACTER", f"Invalid character: {ch}", Severity.CRITICAL_ERROR, token))

        tokens.append(Token("EOF", "", self.line, self.column, self.filename))
        return tokens, self.errors

    def _at_end(self) -> bool:
        return self.pos >= len(self.text)

    def _peek_char(self) -> str:
        return self.text[self.pos]

    def _advance(self) -> str:
        ch = self.text[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _make_token(self, kind: str, value: Any) -> Token:
        return Token(kind, value, self.line, self.column, self.filename)

    def _read_comment(self) -> None:
        self._advance()
        while not self._at_end() and self._peek_char() != "\n":
            self._advance()

    def _read_identifier(self) -> Token:
        line, column = self.line, self.column
        chars = [self._advance()]
        while not self._at_end() and (self._peek_char().isalnum() or self._peek_char() == "_"):
            chars.append(self._advance())
        value = "".join(chars)
        kind = "BOOLEAN" if value in {"true", "false"} else "IDENT"
        parsed_value = value == "true" if value in {"true", "false"} else value
        return Token(kind, parsed_value, line, column, self.filename)

    def _read_number_or_invalid_identifier(self) -> Optional[Token]:
        line, column = self.line, self.column
        chars = [self._advance()]
        has_dot = False
        while not self._at_end() and (self._peek_char().isdigit() or self._peek_char() == "."):
            if self._peek_char() == ".":
                if has_dot:
                    break
                has_dot = True
            chars.append(self._advance())

        if not self._at_end() and (self._peek_char().isalpha() or self._peek_char() == "_"):
            while not self._at_end() and (self._peek_char().isalnum() or self._peek_char() == "_"):
                chars.append(self._advance())
            token = Token("INVALID_IDENTIFIER", "".join(chars), line, column, self.filename)
            self.errors.append(_issue("LEX_INVALID_IDENTIFIER", "Identifier must start with a letter", Severity.CRITICAL_ERROR, token))
            return token

        raw = "".join(chars)
        if raw.endswith("."):
            token = Token("INVALID_NUMBER", raw, line, column, self.filename)
            self.errors.append(_issue("LEX_INVALID_NUMBER", "Invalid numeric literal", Severity.CRITICAL_ERROR, token))
            return token
        value: int | float = float(raw) if has_dot else int(raw)
        return Token("NUMBER", value, line, column, self.filename)

    def _read_string(self) -> Optional[Token]:
        line, column = self.line, self.column
        self._advance()
        chars: list[str] = []
        while not self._at_end() and self._peek_char() != '"':
            ch = self._advance()
            if ch == "\\" and not self._at_end():
                escaped = self._advance()
                chars.append({"n": "\n", "t": "\t", '"': '"'}.get(escaped, escaped))
            else:
                chars.append(ch)
        token = Token("STRING", "".join(chars), line, column, self.filename)
        if self._at_end():
            self.errors.append(_issue("LEX_UNTERMINATED_STRING", "Unterminated string literal", Severity.CRITICAL_ERROR, token))
            return token
        self._advance()
        return token


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0
        self.errors: list[ValidationIssue] = []

    def parse(self) -> ParseResult:
        if not self._match_ident("knowledge_base"):
            self._error("PARSE_EXPECTED_KNOWLEDGE_BASE", "Document must start with knowledge_base")
            return ParseResult(None, self.errors)
        name_token = self._consume("IDENT", "PARSE_EXPECTED_KB_NAME", "Expected knowledge base name")
        kb_name = str(name_token.value) if name_token else ""

        sections: list[AstSectionNode] = []
        sections_by_type: dict[str, AstSectionNode] = {}
        while not self._check("EOF"):
            if not self._check("IDENT"):
                self._error("PARSE_EXPECTED_SECTION", "Expected section name")
                self._advance()
                continue
            section_name = str(self._peek().value)
            section_token = self._advance()
            self._consume(":", "PARSE_EXPECTED_SECTION_COLON", "Expected ':' after section name")
            section = self._parse_section(section_name, section_token)
            sections.append(section)
            if section_name not in sections_by_type:
                sections_by_type[section_name] = section

        return ParseResult(
            AstDocument(
                kind="AstDocument",
                kb_name=kb_name,
                sections=sections,
                sections_by_type=sections_by_type,
            ),
            self.errors,
        )

    def _parse_section(self, name: str, token: Token) -> AstSectionNode:
        items: list[AstNode] = []
        if name not in SECTION_NAMES:
            self._error("PARSE_UNKNOWN_SECTION", f"Unknown section: {name}", token)
            while not self._check("EOF") and not self._is_section_start():
                self._advance()
            return AstSectionNode(kind="AstSectionNode", section_name=name, items=items)

        while not self._check("EOF") and not self._is_section_start():
            before = self.pos
            item: Optional[AstNode]
            if name == "types":
                item = self._parse_type_decl()
            elif name == "relations":
                item = self._parse_relation_decl()
            elif name == "individuals":
                item = self._parse_individual_decl()
            elif name == "graphs":
                item = self._parse_graph_decl()
            elif name == "contexts":
                item = self._parse_context_decl()
            elif name == "rules":
                item = self._parse_rule_decl()
            else:
                item = None
            if item is not None:
                items.append(item)
            if self.pos == before:
                self._advance()
        return AstSectionNode(kind="AstSectionNode", section_name=name, items=items)

    def _parse_type_decl(self) -> Optional[AstTypeDecl]:
        start_token = self._consume_ident_value({"type", "context_type"}, "PARSE_EXPECTED_TYPE_DECL", "Expected type declaration")
        if start_token is None:
            return None
        is_context_type = start_token.value == "context_type"
        name_token = self._consume("IDENT", "PARSE_EXPECTED_TYPE_NAME", "Expected type name")
        parents: list[str] = []
        if self._match(":"):
            parents.append(self._consume_identifier_value("PARSE_EXPECTED_PARENT_TYPE", "Expected parent type name"))
            while self._match(","):
                parents.append(self._consume_identifier_value("PARSE_EXPECTED_PARENT_TYPE", "Expected parent type name"))
        return AstTypeDecl(
            kind="AstTypeDecl",
            name=str(name_token.value) if name_token else "",
            parent_names=[parent for parent in parents if parent],
            is_context_type=is_context_type,
        )

    def _parse_relation_decl(self) -> Optional[AstRelationDecl]:
        start_token = self._consume_ident_value({"relation"}, "PARSE_EXPECTED_RELATION_DECL", "Expected relation declaration")
        if start_token is None:
            return None
        name_token = self._consume("IDENT", "PARSE_EXPECTED_RELATION_NAME", "Expected relation name")
        self._consume("(", "PARSE_EXPECTED_SIGNATURE_OPEN", "Expected '(' in relation signature")
        signature: list[AstTypeRef] = []
        if not self._check(")"):
            signature.append(self._parse_type_ref())
            while self._match(","):
                signature.append(self._parse_type_ref())
        self._consume(")", "PARSE_EXPECTED_SIGNATURE_CLOSE", "Expected ')' after relation signature")
        return AstRelationDecl(
            kind="AstRelationDecl",
            name=str(name_token.value) if name_token else "",
            signature=signature,
        )

    def _parse_individual_decl(self) -> Optional[AstIndividualDecl]:
        start_token = self._consume_ident_value({"individual"}, "PARSE_EXPECTED_INDIVIDUAL_DECL", "Expected individual declaration")
        if start_token is None:
            return None
        name_token = self._consume("IDENT", "PARSE_EXPECTED_INDIVIDUAL_NAME", "Expected individual name")
        self._consume(":", "PARSE_EXPECTED_INDIVIDUAL_COLON", "Expected ':' after individual name")
        return AstIndividualDecl(
            kind="AstIndividualDecl",
            name=str(name_token.value) if name_token else "",
            base_type=self._parse_type_ref(),
        )

    def _parse_graph_decl(self) -> Optional[AstGraphDecl]:
        start_token = self._consume_ident_value({"graph"}, "PARSE_EXPECTED_GRAPH_DECL", "Expected graph declaration")
        if start_token is None:
            return None
        name_token = self._consume("IDENT", "PARSE_EXPECTED_GRAPH_NAME", "Expected graph name")
        self._consume("{", "PARSE_EXPECTED_GRAPH_OPEN", "Expected '{' after graph name")
        concepts: list[AstConceptDecl] = []
        relations: list[AstRelationStmt] = []
        while not self._check("}") and not self._check("EOF"):
            if self._check_ident("concept"):
                concepts.append(self._parse_concept_decl())
            elif self._check_ident("relation"):
                relations.append(self._parse_relation_stmt())
            else:
                self._error("PARSE_EXPECTED_GRAPH_ITEM", "Expected concept or relation inside graph")
                self._advance()
        self._consume("}", "PARSE_EXPECTED_GRAPH_CLOSE", "Expected '}' after graph")
        return AstGraphDecl(
            kind="AstGraphDecl",
            name=str(name_token.value) if name_token else "",
            concepts=concepts,
            relations=relations,
        )

    def _parse_concept_decl(self) -> AstConceptDecl:
        self._consume_ident_value({"concept"}, "PARSE_EXPECTED_CONCEPT_DECL", "Expected concept declaration")
        label_token = self._consume("IDENT", "PARSE_EXPECTED_CONCEPT_LABEL", "Expected concept label")
        self._consume(":", "PARSE_EXPECTED_CONCEPT_COLON", "Expected ':' after concept label")
        type_ref = self._parse_type_ref()
        individual_ref = None
        if self._match("="):
            individual_ref = self._consume_identifier_value("PARSE_EXPECTED_INDIVIDUAL_REF", "Expected individual reference")
        return AstConceptDecl(
            kind="AstConceptDecl",
            label=str(label_token.value) if label_token else "",
            type_ref=type_ref,
            individual_ref=individual_ref,
        )

    def _parse_relation_stmt(self) -> AstRelationStmt:
        self._consume_ident_value({"relation"}, "PARSE_EXPECTED_RELATION_STMT", "Expected relation statement")
        name_token = self._consume("IDENT", "PARSE_EXPECTED_RELATION_STMT_NAME", "Expected relation name")
        self._consume("(", "PARSE_EXPECTED_RELATION_STMT_OPEN", "Expected '(' after relation name")
        arguments: list[AstConceptRef] = []
        if not self._check(")"):
            arguments.append(self._parse_concept_ref())
            while self._match(","):
                arguments.append(self._parse_concept_ref())
        self._consume(")", "PARSE_EXPECTED_RELATION_STMT_CLOSE", "Expected ')' after relation arguments")
        return AstRelationStmt(
            kind="AstRelationStmt",
            relation_name=str(name_token.value) if name_token else "",
            arguments=arguments,
        )

    def _parse_context_decl(self) -> Optional[AstContextDecl]:
        start_token = self._consume_ident_value({"context"}, "PARSE_EXPECTED_CONTEXT_DECL", "Expected context declaration")
        if start_token is None:
            return None
        name_token = self._consume("IDENT", "PARSE_EXPECTED_CONTEXT_NAME", "Expected context name")
        self._consume(":", "PARSE_EXPECTED_CONTEXT_COLON", "Expected ':' after context name")
        type_name = self._consume_identifier_value("PARSE_EXPECTED_CONTEXT_TYPE", "Expected context type")
        self._consume_ident_value({"kind"}, "PARSE_EXPECTED_KIND_KEYWORD", "Expected kind keyword")
        context_kind = self._consume_identifier_value("PARSE_EXPECTED_CONTEXT_KIND", "Expected ContextKind")
        self._consume_ident_value({"uses"}, "PARSE_EXPECTED_USES_KEYWORD", "Expected uses keyword")
        graph_name = self._consume_identifier_value("PARSE_EXPECTED_CONTEXT_GRAPH", "Expected graph name")
        return AstContextDecl(
            kind="AstContextDecl",
            name=str(name_token.value) if name_token else "",
            type_name=type_name,
            context_kind=context_kind,
            graph_name=graph_name,
        )

    def _parse_rule_decl(self) -> Optional[AstRuleDecl]:
        start_token = self._consume_ident_value({"rule"}, "PARSE_EXPECTED_RULE_DECL", "Expected rule declaration")
        if start_token is None:
            return None
        name_token = self._consume("IDENT", "PARSE_EXPECTED_RULE_NAME", "Expected rule name")
        if self._match("{"):
            close_kind = "}"
        else:
            self._consume(":", "PARSE_EXPECTED_RULE_OPEN", "Expected '{' or ':' after rule name")
            close_kind = None
        rule = AstRuleDecl(kind="AstRuleDecl", name=str(name_token.value) if name_token else "")
        while not self._check("EOF") and not (close_kind and self._check(close_kind)) and not (close_kind is None and self._is_rule_boundary()):
            if not self._check("IDENT"):
                self._error("PARSE_EXPECTED_RULE_FIELD", "Expected rule field")
                self._advance()
                continue
            field = str(self._advance().value)
            if field == "if":
                rule.if_context_name = self._consume_identifier_value("PARSE_EXPECTED_RULE_IF", "Expected if-context name")
            elif field == "then":
                rule.then_context_name = self._consume_identifier_value("PARSE_EXPECTED_RULE_THEN", "Expected then-context name")
            elif field == "priority":
                token = self._consume("NUMBER", "PARSE_EXPECTED_RULE_PRIORITY", "Expected numeric rule priority")
                rule.priority = token.value if token else 0
            elif field == "enabled":
                token = self._consume("BOOLEAN", "PARSE_EXPECTED_RULE_ENABLED", "Expected boolean rule enabled flag")
                rule.enabled = bool(token.value) if token else True
            else:
                self._error("PARSE_UNKNOWN_RULE_FIELD", f"Unknown rule field: {field}")
                self._advance()
        if close_kind:
            self._consume("}", "PARSE_EXPECTED_RULE_CLOSE", "Expected '}' after rule")
        return rule

    def _parse_type_ref(self) -> AstTypeRef:
        token = self._consume("IDENT", "PARSE_EXPECTED_TYPE_REF", "Expected type reference") or self._previous()
        return AstTypeRef(kind="AstTypeRef", name=str(token.value))

    def _parse_concept_ref(self) -> AstConceptRef:
        token = self._consume("IDENT", "PARSE_EXPECTED_CONCEPT_REF", "Expected concept reference") or self._previous()
        return AstConceptRef(kind="AstConceptRef", label=str(token.value))

    def _is_section_start(self) -> bool:
        return self._check("IDENT") and self._peek_next().kind == ":"

    def _is_rule_boundary(self) -> bool:
        return self._is_section_start() or self._check_ident("rule")

    def _check_ident(self, value: str) -> bool:
        return self._check("IDENT") and self._peek().value == value

    def _match_ident(self, value: str) -> bool:
        if self._check_ident(value):
            self._advance()
            return True
        return False

    def _consume_ident_value(self, values: set[str], code: str, message: str) -> Optional[Token]:
        if self._check("IDENT") and self._peek().value in values:
            return self._advance()
        self._error(code, message)
        return None

    def _consume_identifier_value(self, code: str, message: str) -> str:
        token = self._consume("IDENT", code, message)
        return str(token.value) if token else ""

    def _consume(self, kind: str, code: str, message: str) -> Optional[Token]:
        if self._check(kind):
            return self._advance()
        self._error(code, message)
        return None

    def _match(self, kind: str) -> bool:
        if self._check(kind):
            self._advance()
            return True
        return False

    def _check(self, kind: str) -> bool:
        return self._peek().kind == kind

    def _advance(self) -> Token:
        if not self._check("EOF"):
            self.pos += 1
        return self._previous()

    def _peek(self) -> Token:
        return self.tokens[self.pos]

    def _peek_next(self) -> Token:
        return self.tokens[min(self.pos + 1, len(self.tokens) - 1)]

    def _previous(self) -> Token:
        return self.tokens[max(0, self.pos - 1)]

    def _error(self, code: str, message: str, token: Optional[Token] = None) -> None:
        self.errors.append(_issue(code, message, Severity.CRITICAL_ERROR, token or self._peek()))


def parse_text(text: str, filename: Optional[str] = None) -> ParseResult:
    tokens, lex_errors = Lexer(text, filename).tokenize()
    parse_result = Parser(tokens).parse()
    parse_result.errors = [*lex_errors, *parse_result.errors]
    return parse_result


def validate_ast(document: Optional[AstDocument]) -> AstValidationResult:
    issues: list[ValidationIssue] = []
    if document is None:
        return AstValidationResult(document, issues)
    present_sections = {section.section_name for section in document.sections}
    for section_name in sorted(MANDATORY_SECTIONS - present_sections):
        issues.append(
            ValidationIssue(
                "AST_MANDATORY_SECTION_MISSING",
                f"Mandatory section is missing: {section_name}",
                Severity.CRITICAL_ERROR,
                details={"section": section_name},
            )
        )
    return AstValidationResult(document, issues)
