"""생성 출력의 스키마와 공통 모델 구조 검사 관문."""

from langgraph.runtime import Runtime
from pydantic import ValidationError

from app.core.tracing import observation, update_observation
from app.schemas.design import Design
from app.services.design_model import validate_design
from app.services.design_pipeline.errors import failure
from app.services.design_pipeline.state import Context, State


def validate(state: State, runtime: Runtime[Context]):
    with observation(runtime.context.tracer, "validate") as span:
        try:
            design = Design.model_validate_json(state["raw"])
            errors, status = validate_design(design, state["source"]), "structure_invalid"
        except ValidationError as exc:
            # 경로와 유형만 노출한다. 모델 본문과 검증 예외 문자열은 남기지 않는다.
            errors = [
                f"{'unexpected_field' if e['type'] == 'extra_forbidden' else '.'.join(map(str, e['loc']))}: {e['type']}"
                for e in exc.errors()
            ]
            status = "invalid_model_output"
        if errors:
            update_observation(span, level="ERROR", status_message=status)
    if errors:
        raise failure(
            "structure_invalid",
            "생성 결과 구조 검증 실패. ERD·DDL·의미 검토를 실행하지 않았습니다.",
            "validate",
            422,
            issues=errors,
        )
    return {"design": design}
