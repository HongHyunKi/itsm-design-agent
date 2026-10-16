"""A 단계의 문서 근거·전문 역할·실행 전이 계약을 외부 호출 없이 검사한다."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.design_v1 import (
    AnalysisInput,
    AnalysisOutput,
    AnswerSnapshot,
    AnswerV1,
    ColumnV1,
    DataDesignInput,
    DataDesignOutput,
    DataModelV1,
    FunctionDesignInput,
    FunctionDesignOutput,
    FunctionV1,
    RequirementV1,
    RuleV1,
    TableV1,
    VerificationV1,
)
from app.schemas.document import DocumentBlock, EvidenceReference
from app.services.design_pipeline.contract import (
    RunCursor,
    StageFailure,
    advance_cursor,
    completion_status,
    retry_allowed,
    validate_analysis_output,
    validate_answer_snapshot,
    validate_data_design,
    validate_function_design,
)


def block(*, revision_id: str = "revision-1") -> DocumentBlock:
    return DocumentBlock(
        document_revision_id=revision_id,
        block_id="block-1",
        locator={"kind": "txt", "start_line": 1, "end_line": 1},
        raw_text="요청은 1.5초 안에 처리한다.",
        normalized_text="요청은 1.5초 안에 처리한다.",
        normalization_version="1",
    )


def analysis_input() -> AnalysisInput:
    return AnalysisInput(document_revision_id="revision-1", blocks=[block()])


def evidence(**changes) -> EvidenceReference:
    values = {
        "document_revision_id": "revision-1",
        "block_id": "block-1",
        "start": 4,
        "end": 8,
        "quote": "1.5초",
    }
    values.update(changes)
    return EvidenceReference.model_validate(values)


def analysis_payload(*, questions=True):
    return {
        "schema_version": "1",
        "requirements": [
            {
                "id": "C-REQ-1",
                "text": "요청은 1.5초 안에 처리한다.",
                "kind": "nonfunctional",
                "provenance": "source",
                "evidence": [evidence()],
                "needs_confirmation": False,
                "priority": "undecided",
                "priority_reason": "원문에 우선순위 없음",
            }
        ],
        "questions": (
            [
                {
                    "id": "C-Q-1",
                    "requirement_ids": ["C-REQ-1"],
                    "type": "information_gap",
                    "question": "처리 시간 측정 기준은 무엇인가요?",
                    "evidence": [evidence()],
                    "status": "open",
                }
            ]
            if questions
            else []
        ),
    }


def function_payload():
    return {
        "schema_version": "1",
        "functions": [
            {
                "id": "C-FUN-1",
                "name": "요청 처리",
                "actor": "담당자",
                "description": "서비스 요청을 처리한다.",
                "inputs": ["요청 내용"],
                "outputs": ["처리 결과"],
                "preconditions": [],
                "rules": ["처리 시간 측정"],
                "exceptions": [],
                "priority": "undecided",
                "requirement_ids": ["C-REQ-1"],
                "provenance": "source",
            }
        ],
    }


def answer_snapshot(*, unresolved=False):
    now = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
    return AnswerSnapshot(
        answers=[
            AnswerV1(
                question_id="C-Q-1",
                version=1,
                text=None if unresolved else "요청 접수부터 완료까지",
                unresolved=unresolved,
                created_at=now,
            )
        ],
        frozen_at=now,
    )


def data_model_payload():
    return {
        "tables": [
            {
                "id": "C-TBL-1",
                "name": "service_request",
                "description": "서비스 요청",
                "columns": [
                    {
                        "id": "C-COL-1",
                        "name": "id",
                        "type": "bigint",
                        "nullable": False,
                        "default_kind": "none",
                        "description": "요청 식별자",
                    }
                ],
                "primary_key": ["C-COL-1"],
                "uniques": [],
                "foreign_keys": [],
                "requirement_ids": ["C-REQ-1"],
                "function_ids": ["C-FUN-1"],
                "provenance": "source",
            }
        ],
        "rules": [],
    }


def test_evidence_matches_exact_revision_block_and_offsets():
    source = block()
    assert source.normalized_text[4:8] == "1.5초"
    assert evidence().matches(source)
    assert not evidence(quote="15초").matches(source)
    assert not evidence(document_revision_id="revision-2").matches(source)
    assert not evidence(block_id="block-2").matches(source)
    assert not evidence(start=5, end=8, quote="1.5초").matches(source)
    assert not evidence(start=4, end=100).matches(source)
    assert not EvidenceReference(
        document_revision_id="revision-1",
        block_id="block-1",
        start=8,
        end=100,
        quote=source.normalized_text[8:],
    ).matches(source)


def test_document_block_rejects_whitespace_only_normalized_text():
    with pytest.raises(ValidationError):
        DocumentBlock.model_validate({**block().model_dump(), "normalized_text": "  "})


def test_analysis_input_requires_nonempty_blocks_from_one_revision():
    assert AnalysisInput(document_revision_id="revision-1", blocks=[block()]).blocks[0].block_id == "block-1"
    with pytest.raises(ValidationError):
        AnalysisInput(document_revision_id="revision-1", blocks=[])
    with pytest.raises(ValidationError):
        AnalysisInput(document_revision_id="revision-1", blocks=[block(revision_id="revision-2")])


@pytest.mark.parametrize("start,end", [(-1, 4), (4, 4), (5, 4)])
def test_evidence_rejects_invalid_offset_order(start, end):
    with pytest.raises(ValidationError):
        evidence(start=start, end=end)


def test_analysis_contract_checks_exact_quote_and_revision():
    analysis = AnalysisOutput.model_validate(analysis_payload())
    assert validate_analysis_output(analysis_input(), analysis) == []

    forged = analysis.model_copy(deep=True)
    forged.requirements[0].evidence[0].quote = "15초"
    assert validate_analysis_output(analysis_input(), forged)

    wrong_revision = analysis.model_copy(deep=True)
    wrong_revision.requirements[0].evidence[0].document_revision_id = "revision-2"
    assert validate_analysis_output(analysis_input(), wrong_revision)


@pytest.mark.parametrize("bad_id", ["REQ-1", "C-REQ-X", "C-REQ-1 extra"])
def test_requirement_id_has_customer_namespace(bad_id):
    item = analysis_payload()["requirements"][0]
    with pytest.raises(ValidationError):
        RequirementV1.model_validate({**item, "id": bad_id})


@pytest.mark.parametrize("bad_id", ["FUN-1", "C-FUN-X", "C-FUN-1 extra"])
def test_function_id_has_customer_namespace(bad_id):
    item = function_payload()["functions"][0]
    with pytest.raises(ValidationError):
        FunctionV1.model_validate({**item, "id": bad_id})


def test_analysis_rejects_duplicate_requirements_and_unknown_question_reference():
    payload = analysis_payload()
    payload["requirements"].append(deepcopy(payload["requirements"][0]))
    assert validate_analysis_output(analysis_input(), AnalysisOutput.model_validate(payload))

    payload = analysis_payload()
    payload["questions"][0]["evidence"] = []
    with pytest.raises(ValidationError):
        AnalysisOutput.model_validate(payload)

    payload = analysis_payload()
    payload["questions"][0]["requirement_ids"] = ["C-REQ-999"]
    assert validate_analysis_output(analysis_input(), AnalysisOutput.model_validate(payload))


@pytest.mark.parametrize(
    "changes",
    [
        {"text": None, "unresolved": False},
        {"text": "", "unresolved": False},
        {"text": "답변", "unresolved": True},
        {"version": 0},
        {"created_at": datetime(2026, 10, 16)},
    ],
)
def test_answer_requires_one_valid_choice_and_version(changes):
    payload = {
        "question_id": "C-Q-1",
        "version": 1,
        "text": "요청 접수부터 완료까지",
        "unresolved": False,
        "created_at": datetime(2026, 10, 16, 9, 0, tzinfo=UTC),
    }
    with pytest.raises(ValidationError):
        AnswerV1.model_validate({**payload, **changes})


def test_answer_snapshot_matches_all_questions_once():
    questions = AnalysisOutput.model_validate(analysis_payload()).questions
    snapshot = answer_snapshot()
    assert validate_answer_snapshot(questions, snapshot) == []
    assert validate_answer_snapshot(questions, answer_snapshot(unresolved=True)) == []

    missing = snapshot.model_copy(update={"answers": []})
    assert validate_answer_snapshot(questions, missing)
    duplicate = snapshot.model_copy(update={"answers": [*snapshot.answers, snapshot.answers[0]]})
    assert validate_answer_snapshot(questions, duplicate)
    unknown = snapshot.model_copy(deep=True)
    unknown.answers[0].question_id = "C-Q-999"
    assert validate_answer_snapshot(questions, unknown)


def test_function_contract_rejects_duplicate_and_unknown_requirement_link():
    design_input = FunctionDesignInput(
        analysis=AnalysisOutput.model_validate(analysis_payload()), answers=answer_snapshot()
    )
    output = FunctionDesignOutput.model_validate(function_payload())
    assert validate_function_design(design_input, output) == []

    duplicate = output.model_copy(deep=True)
    duplicate.functions.append(duplicate.functions[0])
    assert validate_function_design(design_input, duplicate)
    unknown = output.model_copy(deep=True)
    unknown.functions[0].requirement_ids = ["C-REQ-999"]
    assert validate_function_design(design_input, unknown)


def test_proposed_function_and_table_require_an_explicit_reason():
    function = function_payload()["functions"][0]
    with pytest.raises(ValidationError):
        FunctionV1.model_validate({**function, "provenance": "proposal"})

    table = data_model_payload()["tables"][0]
    with pytest.raises(ValidationError):
        TableV1.model_validate({**table, "provenance": "proposal"})

    with pytest.raises(ValidationError):
        RuleV1(
            id="C-RULE-1",
            description="요청 보관 기간",
            requirement_ids=[],
            enforcement="application",
            representation="미정",
            provenance="source",
        )


def test_user_answer_provenance_requires_the_frozen_answer_version():
    stage_input = FunctionDesignInput(
        analysis=AnalysisOutput.model_validate(analysis_payload()), answers=answer_snapshot()
    )
    payload = function_payload()
    payload["functions"][0].update(provenance="user_answer", answer_question_id="C-Q-1", answer_version=2)
    output = FunctionDesignOutput.model_validate(payload)
    assert "functions[0]: invalid answer reference" in validate_function_design(stage_input, output)

    output.functions[0].answer_version = 1
    assert validate_function_design(stage_input, output) == []

    stage_input.answers.answers[0].unresolved = True
    stage_input.answers.answers[0].text = None
    assert "functions[0]: invalid answer reference" in validate_function_design(stage_input, output)


def test_shared_data_model_schema_supports_customer_ids_and_restricted_types():
    model_payload = data_model_payload()
    table = TableV1.model_validate(model_payload["tables"][0])
    column = model_payload["tables"][0]["columns"][0]
    assert DataModelV1(tables=[table], rules=[]).tables[0].columns[0].id == "C-COL-1"
    with pytest.raises(ValidationError):
        ColumnV1.model_validate({**column, "type": "DROP TABLE"})
    with pytest.raises(ValidationError):
        ColumnV1.model_validate({**column, "type": "varchar"})
    with pytest.raises(ValidationError):
        ColumnV1.model_validate({**column, "type": "numeric", "precision": 2, "scale": 3})


def test_verification_does_not_collapse_not_run_into_passed():
    value = VerificationV1(structure="passed", semantic_review="completed", database_execution="not_run")
    assert value.database_execution == "not_run"
    with pytest.raises(ValidationError):
        VerificationV1.model_validate(
            {"structure": "passed", "semantic_review": "completed", "database_execution": "success"}
        )


def test_data_stage_rejects_missing_key_column_and_unknown_design_reference():
    stage_input = DataDesignInput(
        analysis=AnalysisOutput.model_validate(analysis_payload()),
        answers=answer_snapshot(),
        functions=FunctionDesignOutput.model_validate(function_payload()),
    )
    output = DataDesignOutput(data_model=DataModelV1.model_validate(data_model_payload()), rationale=[])
    assert validate_data_design(stage_input, output) == []

    bad_key = output.model_copy(deep=True)
    bad_key.data_model.tables[0].primary_key = ["C-COL-999"]
    assert validate_data_design(stage_input, bad_key)
    bad_link = output.model_copy(deep=True)
    bad_link.data_model.tables[0].function_ids = ["C-FUN-999"]
    assert validate_data_design(stage_input, bad_link)

    answer_source = output.model_copy(deep=True)
    answer_source.data_model.tables[0].provenance = "user_answer"
    answer_source.data_model.tables[0].answer_question_id = "C-Q-1"
    answer_source.data_model.tables[0].answer_version = 2
    assert "tables[0]: invalid answer reference" in validate_data_design(stage_input, answer_source)


def test_analysis_always_pauses_for_user_decision_even_without_questions():
    cursor = advance_cursor(RunCursor(status="queued", phase="analysis"), "start")
    assert cursor == RunCursor(status="running", phase="analysis")
    cursor = advance_cursor(cursor, "analysis_completed")
    assert cursor == RunCursor(status="awaiting_input", phase="analysis")
    with pytest.raises(ValueError):
        advance_cursor(cursor, "continue", questions=[])
    with pytest.raises(ValueError):
        advance_cursor(cursor, "continue", answer_snapshot=answer_snapshot(), questions=[])

    empty_snapshot = AnswerSnapshot(answers=[], frozen_at=datetime(2026, 10, 16, 9, 0, tzinfo=UTC))
    queued = advance_cursor(cursor, "continue", answer_snapshot=empty_snapshot, questions=[])
    assert queued == RunCursor(status="queued", phase="function_design", answers_frozen=True)
    assert advance_cursor(queued, "start") == RunCursor(status="running", phase="function_design", answers_frozen=True)


def test_unresolved_answer_is_carried_into_completion_without_a_caller_flag():
    questions = AnalysisOutput.model_validate(analysis_payload()).questions
    waiting = RunCursor(status="awaiting_input", phase="analysis")
    resumed = advance_cursor(waiting, "continue", answer_snapshot=answer_snapshot(unresolved=True), questions=questions)
    assert resumed.has_unresolved

    delivered = RunCursor(
        status="running",
        phase="delivery",
        answers_frozen=True,
        has_unresolved=resumed.has_unresolved,
        verification=VerificationV1(structure="passed", semantic_review="completed", database_execution="passed"),
    )
    with pytest.raises(ValueError):
        advance_cursor(delivered, "stage_completed")
    assert advance_cursor(delivered, "stage_completed", has_warnings=False).status == "completed_with_warnings"


def test_execution_stage_order_and_validation_failure_route():
    current = RunCursor(status="running", phase="function_design", answers_frozen=True)
    for phase in ("data_design", "structure_validation"):
        current = advance_cursor(current, "stage_completed")
        assert current.phase == phase

    structure_passed = VerificationV1(structure="passed", semantic_review="not_run", database_execution="not_run")
    current = advance_cursor(current, "stage_completed", verification=structure_passed)
    assert current.phase == "render"
    current = advance_cursor(current, "stage_completed")
    assert current.phase == "semantic_review"
    review_completed = VerificationV1(structure="passed", semantic_review="completed", database_execution="not_run")
    current = advance_cursor(current, "stage_completed", verification=review_completed)
    assert current.phase == "db_validation"
    passed = VerificationV1(structure="passed", semantic_review="completed", database_execution="passed")
    current = advance_cursor(current, "stage_completed", verification=passed)
    assert current.phase == "delivery"
    assert advance_cursor(current, "stage_completed", has_warnings=False).status == "completed"

    failed = VerificationV1(structure="failed", semantic_review="not_run", database_execution="not_run")
    diagnostic = advance_cursor(
        RunCursor(status="running", phase="structure_validation", answers_frozen=True),
        "stage_completed",
        verification=failed,
    )
    assert diagnostic.phase == "delivery"
    assert advance_cursor(diagnostic, "stage_completed", has_warnings=False).status == "completed_with_errors"


@pytest.mark.parametrize(
    "verification,warnings,unresolved,expected",
    [
        (("passed", "completed", "passed"), False, False, "completed"),
        (("passed", "completed", "not_run"), False, False, "completed_with_warnings"),
        (("passed", "completed", "passed"), True, False, "completed_with_warnings"),
        (("passed", "completed", "passed"), False, True, "completed_with_warnings"),
        (("passed", "completed", "failed"), False, False, "completed_with_errors"),
        (("failed", "not_run", "not_run"), False, False, "completed_with_errors"),
        (("not_run", "not_run", "not_run"), False, False, "failed"),
        (("passed", "failed", "not_run"), False, False, "failed"),
    ],
)
def test_completion_status_preserves_verification_priority(verification, warnings, unresolved, expected):
    result = VerificationV1(
        structure=verification[0], semantic_review=verification[1], database_execution=verification[2]
    )
    assert completion_status(result, has_warnings=warnings, has_unresolved=unresolved) == expected


def test_failed_review_and_technical_failure_cannot_continue():
    incomplete = VerificationV1(structure="passed", semantic_review="failed", database_execution="not_run")
    cursor = RunCursor(
        status="running",
        phase="semantic_review",
        answers_frozen=True,
        verification=VerificationV1(structure="passed", semantic_review="not_run", database_execution="not_run"),
    )
    with pytest.raises(ValueError):
        advance_cursor(cursor, "stage_completed", verification=incomplete)

    with pytest.raises(ValueError):
        advance_cursor(cursor, "technical_failure")
    failed = advance_cursor(
        cursor,
        "technical_failure",
        failure=StageFailure(
            stage="semantic_review",
            code="OUTPUT_INVALID",
            message="의미 검토 결과가 유효하지 않습니다.",
            retryable=False,
            attempts=2,
        ),
    )
    assert failed.status == "failed"
    assert failed.failure.code == "OUTPUT_INVALID"
    with pytest.raises(ValueError):
        advance_cursor(failed, "stage_completed", verification=incomplete)


def test_validation_results_cannot_be_replaced_at_delivery():
    delivered = RunCursor(
        status="running",
        phase="delivery",
        answers_frozen=True,
        verification=VerificationV1(structure="passed", semantic_review="completed", database_execution="not_run"),
    )
    forged = VerificationV1(structure="passed", semantic_review="completed", database_execution="passed")
    with pytest.raises(ValueError):
        advance_cursor(delivered, "stage_completed", verification=forged, has_warnings=False)

    completed = advance_cursor(delivered, "stage_completed", has_warnings=False)
    assert RunCursor.model_validate(completed.model_dump()) == completed
    with pytest.raises(ValidationError):
        RunCursor.model_validate({**completed.model_dump(), "status": "completed"})


def test_verification_rejects_impossible_stage_order():
    with pytest.raises(ValidationError):
        VerificationV1(structure="failed", semantic_review="completed", database_execution="passed")
    with pytest.raises(ValidationError):
        VerificationV1(structure="passed", semantic_review="failed", database_execution="passed")


def test_only_awaiting_input_can_be_superseded():
    waiting = RunCursor(status="awaiting_input", phase="analysis")
    assert advance_cursor(waiting, "supersede").status == "superseded"
    with pytest.raises(ValueError):
        advance_cursor(RunCursor(status="running", phase="analysis"), "supersede")


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "queued", "phase": "function_design"},
        {"status": "awaiting_input", "phase": "function_design", "answers_frozen": True},
        {"status": "running", "phase": "analysis", "answers_frozen": True},
        {"status": "completed", "phase": "analysis"},
    ],
)
def test_run_cursor_rejects_impossible_positions(payload):
    with pytest.raises(ValidationError):
        RunCursor.model_validate(payload)


@pytest.mark.parametrize("error_kind", ["format", "provider_transient"])
def test_recovery_and_transient_error_share_one_retry(error_kind):
    assert retry_allowed(1, error_kind)
    assert not retry_allowed(2, error_kind)


@pytest.mark.parametrize("error_kind", ["auth", "input", "other"])
def test_nonretryable_errors_never_retry(error_kind):
    assert not retry_allowed(1, error_kind)
