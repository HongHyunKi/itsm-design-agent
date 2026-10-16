"""후속 단계의 결정적 계약 검사와 실행 전이 규칙.

현재 동기 ``/design`` 그래프에는 연결하지 않는다. B~F 단계가 이 계약을 사용해
전문 역할과 영속 실행을 붙이며, 기존 API는 전환 전까지 그대로 유지한다.
"""

from collections import Counter
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.design import StrictModel, Text
from app.schemas.design_v1 import (
    AnalysisInput,
    AnalysisOutput,
    AnswerSnapshot,
    DataDesignInput,
    DataDesignOutput,
    FunctionDesignInput,
    FunctionDesignOutput,
    QuestionV1,
    VerificationV1,
)
from app.schemas.document import DocumentBlock, EvidenceReference

RunStatus = Literal[
    "queued",
    "running",
    "awaiting_input",
    "completed",
    "completed_with_warnings",
    "completed_with_errors",
    "failed",
    "superseded",
]
RunPhase = Literal[
    "analysis",
    "function_design",
    "data_design",
    "structure_validation",
    "render",
    "semantic_review",
    "db_validation",
    "delivery",
]
RunEvent = Literal["start", "analysis_completed", "continue", "stage_completed", "technical_failure", "supersede"]
RetryError = Literal["format", "provider_transient", "auth", "input", "other"]


class StageFailure(StrictModel):
    stage: RunPhase
    code: Text
    message: Text
    retryable: bool
    attempts: int = Field(ge=0)


class RunCursor(StrictModel):
    status: RunStatus
    phase: RunPhase
    answers_frozen: bool = False
    has_unresolved: bool = False
    has_review_warnings: bool | None = None
    failure: StageFailure | None = None
    verification: VerificationV1 = Field(
        default_factory=lambda: VerificationV1(
            structure="not_run", semantic_review="not_run", database_execution="not_run"
        )
    )

    @model_validator(mode="after")
    def valid_position(self):
        if (self.status == "failed") != (self.failure is not None):
            raise ValueError("failed status requires a stage failure; other statuses cannot carry one")
        if self.failure is not None and self.failure.stage != self.phase:
            raise ValueError("failure stage must match the active phase")
        if self.phase == "analysis" and self.answers_frozen:
            raise ValueError("analysis cannot use a frozen answer snapshot")
        if not self.answers_frozen and self.has_unresolved:
            raise ValueError("unresolved answers require a frozen snapshot")
        if self.phase != "analysis" and self.status in {"queued", "running"} and not self.answers_frozen:
            raise ValueError("design stages require a frozen answer snapshot")
        if self.status == "queued" and self.phase not in {"analysis", "function_design"}:
            raise ValueError("queued work can start only at analysis or function design")
        if self.status == "awaiting_input" and self.phase != "analysis":
            raise ValueError("only analysis can await user input")
        if self.status == "superseded" and self.phase != "analysis":
            raise ValueError("only an analysis run can be superseded")
        if (
            self.status in {"completed", "completed_with_warnings", "completed_with_errors"}
            and self.phase != "delivery"
        ):
            raise ValueError("completion requires delivery")
        if self.status in {"completed", "completed_with_warnings", "completed_with_errors"}:
            if self.has_review_warnings is None or self.status != completion_status(
                self.verification,
                has_warnings=self.has_review_warnings,
                has_unresolved=self.has_unresolved,
            ):
                raise ValueError("completion status must match verification and warning results")
        if self.status in {
            "queued",
            "running",
            "awaiting_input",
            "completed",
            "completed_with_warnings",
            "completed_with_errors",
        }:
            verification = self.verification
            if self.phase in {"analysis", "function_design", "data_design", "structure_validation"} and (
                verification.structure != "not_run"
            ):
                raise ValueError("structure result cannot precede structure validation")
            if self.phase in {"render", "semantic_review"} and (
                verification.structure != "passed" or verification.semantic_review != "not_run"
            ):
                raise ValueError("render and review require passed structure")
            if self.phase == "db_validation" and (
                verification.structure != "passed"
                or verification.semantic_review != "completed"
                or verification.database_execution != "not_run"
            ):
                raise ValueError("database validation requires completed review")
            if self.phase == "delivery" and not (
                verification.structure == "failed"
                or (verification.structure == "passed" and verification.semantic_review == "completed")
            ):
                raise ValueError("delivery requires a structure failure or completed review")
        return self


def _duplicates(values: list[str]) -> set[str]:
    return {value for value, count in Counter(values).items() if count > 1}


def _evidence_issue(reference: EvidenceReference, blocks: dict[tuple[str, str], DocumentBlock]) -> bool:
    block = blocks.get((reference.document_revision_id, reference.block_id))
    return block is None or not reference.matches(block)


def validate_analysis_output(stage_input: AnalysisInput, output: AnalysisOutput) -> list[str]:
    """블록 ID, 정확한 인용 구간, 고객 요구·질문 참조를 검사한다."""
    issues = []
    block_index = {(stage_input.document_revision_id, block.block_id): block for block in stage_input.blocks}
    requirement_ids = [requirement.id for requirement in output.requirements]
    if _duplicates(requirement_ids):
        issues.append("requirements: duplicate id")
    question_ids = [question.id for question in output.questions]
    if _duplicates(question_ids):
        issues.append("questions: duplicate id")
    for index, requirement in enumerate(output.requirements):
        if requirement.provenance == "user_answer":
            issues.append(f"requirements[{index}]: user_answer cannot originate in analysis")
        if any(_evidence_issue(reference, block_index) for reference in requirement.evidence):
            issues.append(f"requirements[{index}]: invalid evidence reference")
    for index, question in enumerate(output.questions):
        if question.status != "open":
            issues.append(f"questions[{index}]: analysis question must be open")
        if _duplicates(question.requirement_ids) or not set(question.requirement_ids) <= set(requirement_ids):
            issues.append(f"questions[{index}]: invalid requirement reference")
        if any(_evidence_issue(reference, block_index) for reference in question.evidence):
            issues.append(f"questions[{index}]: invalid evidence reference")
    return issues


def validate_answer_snapshot(questions: list[QuestionV1], snapshot: AnswerSnapshot) -> list[str]:
    """진행 시점의 각 질문에 답변 또는 명시적 미해결 표지가 하나씩 있어야 한다."""
    issues = []
    question_ids = [question.id for question in questions]
    answer_ids = [answer.question_id for answer in snapshot.answers]
    if _duplicates(question_ids):
        issues.append("questions: duplicate id")
    if _duplicates(answer_ids):
        issues.append("answers: duplicate question_id")
    if set(question_ids) != set(answer_ids):
        issues.append("answers: question coverage mismatch")
    if any(answer.created_at > snapshot.frozen_at for answer in snapshot.answers):
        issues.append("answers: created after freeze")
    if sum(len(answer.text or "") for answer in snapshot.answers) > 10000:
        issues.append("answers: total text limit exceeded")
    return issues


def _invalid_answer_source(item, snapshot: AnswerSnapshot) -> bool:
    if item.provenance != "user_answer":
        return False
    answer = next((answer for answer in snapshot.answers if answer.question_id == item.answer_question_id), None)
    return answer is None or answer.unresolved or answer.version != item.answer_version


def validate_function_design(stage_input: FunctionDesignInput, output: FunctionDesignOutput) -> list[str]:
    issues = validate_answer_snapshot(stage_input.analysis.questions, stage_input.answers)
    requirement_ids = {requirement.id for requirement in stage_input.analysis.requirements}
    for index, requirement in enumerate(stage_input.analysis.requirements):
        if _invalid_answer_source(requirement, stage_input.answers):
            issues.append(f"requirements[{index}]: invalid answer reference")
    function_ids = [function.id for function in output.functions]
    if _duplicates(function_ids):
        issues.append("functions: duplicate id")
    for index, function in enumerate(output.functions):
        if _duplicates(function.requirement_ids) or not set(function.requirement_ids) <= requirement_ids:
            issues.append(f"functions[{index}]: invalid requirement reference")
        if _invalid_answer_source(function, stage_input.answers):
            issues.append(f"functions[{index}]: invalid answer reference")
    return issues


def validate_data_design(stage_input: DataDesignInput, output: DataDesignOutput) -> list[str]:
    """단계 경계의 ID·참조 검사. 키·타입·FK 의미 검사는 D의 design_model이 소유한다."""
    issues = validate_function_design(
        FunctionDesignInput(analysis=stage_input.analysis, answers=stage_input.answers), stage_input.functions
    )
    requirement_ids = {requirement.id for requirement in stage_input.analysis.requirements}
    function_ids = {function.id for function in stage_input.functions.functions}
    tables = output.data_model.tables
    table_ids = [table.id for table in tables]
    if _duplicates(table_ids) or _duplicates([table.name for table in tables]):
        issues.append("tables: duplicate id or name")
    columns_by_table = {table.id: {column.id for column in table.columns} for table in tables}
    all_column_ids = [column.id for table in tables for column in table.columns]
    if _duplicates(all_column_ids):
        issues.append("columns: duplicate id")
    for index, table in enumerate(tables):
        own_columns = columns_by_table[table.id]
        if _duplicates([column.name for column in table.columns]):
            issues.append(f"tables[{index}]: duplicate column name")
        if (
            _duplicates(table.requirement_ids)
            or _duplicates(table.function_ids)
            or not set(table.requirement_ids) <= requirement_ids
            or not set(table.function_ids) <= function_ids
        ):
            issues.append(f"tables[{index}]: invalid design reference")
        if _invalid_answer_source(table, stage_input.answers):
            issues.append(f"tables[{index}]: invalid answer reference")
        if not set(table.primary_key) <= own_columns or any(not set(group) <= own_columns for group in table.uniques):
            issues.append(f"tables[{index}]: invalid key column reference")
        for fk_index, foreign_key in enumerate(table.foreign_keys):
            if (
                not set(foreign_key.source_column_ids) <= own_columns
                or foreign_key.target_table_id not in columns_by_table
                or not set(foreign_key.target_column_ids) <= columns_by_table.get(foreign_key.target_table_id, set())
            ):
                issues.append(f"tables[{index}].foreign_keys[{fk_index}]: invalid column reference")
    if _duplicates([rule.id for rule in output.data_model.rules]):
        issues.append("rules: duplicate id")
    for index, rule in enumerate(output.data_model.rules):
        if _duplicates(rule.requirement_ids) or not set(rule.requirement_ids) <= requirement_ids:
            issues.append(f"rules[{index}]: invalid requirement reference")
        if _invalid_answer_source(rule, stage_input.answers):
            issues.append(f"rules[{index}]: invalid answer reference")
    return issues


def completion_status(verification: VerificationV1, *, has_warnings: bool, has_unresolved: bool) -> RunStatus:
    """기술 실패는 별도 이벤트로 기록하고, 검사 결과의 우선순위만 판정한다."""
    if verification.semantic_review == "failed":
        return "failed"
    if verification.structure == "failed" or verification.database_execution == "failed":
        return "completed_with_errors"
    if verification.structure != "passed" or verification.semantic_review != "completed":
        return "failed"
    if verification.database_execution == "not_run" or has_warnings or has_unresolved:
        return "completed_with_warnings"
    return "completed"


def advance_cursor(
    cursor: RunCursor,
    event: RunEvent,
    *,
    answer_snapshot: AnswerSnapshot | None = None,
    questions: list[QuestionV1] | None = None,
    verification: VerificationV1 | None = None,
    has_warnings: bool | None = None,
    failure: StageFailure | None = None,
) -> RunCursor:
    """A 단계에서 확정한 순수 전이. E가 영속 상태와 동일 트랜잭션으로 연결한다."""
    if event == "technical_failure" and cursor.status in {"queued", "running", "awaiting_input"}:
        if failure is None or failure.stage != cursor.phase:
            raise ValueError("technical failure requires a matching stage error")
        return cursor.model_copy(update={"status": "failed", "failure": failure})
    if event == "supersede" and cursor.status == "awaiting_input":
        return cursor.model_copy(update={"status": "superseded"})
    if event == "start" and cursor.status == "queued":
        if cursor.phase in {"analysis", "function_design"}:
            return cursor.model_copy(update={"status": "running"})
    if event == "analysis_completed" and cursor.status == "running" and cursor.phase == "analysis":
        return cursor.model_copy(update={"status": "awaiting_input"})
    if event == "continue" and cursor.status == "awaiting_input" and cursor.phase == "analysis":
        if answer_snapshot is None or questions is None or validate_answer_snapshot(questions, answer_snapshot):
            raise ValueError("continue requires a complete frozen answer snapshot")
        return RunCursor(
            status="queued",
            phase="function_design",
            answers_frozen=True,
            has_unresolved=any(answer.unresolved for answer in answer_snapshot.answers),
        )
    if event == "stage_completed" and cursor.status == "running" and cursor.answers_frozen:
        next_phase: dict[RunPhase, RunPhase] = {
            "function_design": "data_design",
            "data_design": "structure_validation",
            "render": "semantic_review",
        }
        if cursor.phase == "structure_validation":
            if (
                verification is None
                or verification.structure == "not_run"
                or (verification.semantic_review != "not_run" or verification.database_execution != "not_run")
            ):
                raise ValueError("structure validation needs a result")
            return cursor.model_copy(
                update={
                    "phase": "render" if verification.structure == "passed" else "delivery",
                    "verification": verification,
                }
            )
        if cursor.phase == "semantic_review":
            if verification is None or verification != VerificationV1(
                structure="passed", semantic_review="completed", database_execution="not_run"
            ):
                raise ValueError("semantic review must complete before continuing")
            return cursor.model_copy(update={"phase": "db_validation", "verification": verification})
        if cursor.phase == "db_validation":
            if (
                verification is None
                or verification.structure != cursor.verification.structure
                or verification.semantic_review != cursor.verification.semantic_review
            ):
                raise ValueError("database validation needs a result with previous checks unchanged")
            return cursor.model_copy(update={"phase": "delivery", "verification": verification})
        if cursor.phase == "delivery":
            if verification is not None and verification != cursor.verification:
                raise ValueError("delivery cannot replace validation results")
            if has_warnings is None:
                raise ValueError("delivery needs an explicit review warning result")
            return cursor.model_copy(
                update={
                    "status": completion_status(
                        cursor.verification, has_warnings=has_warnings, has_unresolved=cursor.has_unresolved
                    ),
                    "has_review_warnings": has_warnings,
                }
            )
        if cursor.phase in next_phase:
            return cursor.model_copy(update={"phase": next_phase[cursor.phase]})
    raise ValueError(f"transition not allowed: {cursor.status}/{cursor.phase} + {event}")


def retry_allowed(attempts: int, error_kind: RetryError) -> bool:
    """최초 시도 뒤 형식 복구·일시 공급자 오류를 합쳐 한 번만 재시도한다."""
    return attempts == 1 and error_kind in {"format", "provider_transient"}
