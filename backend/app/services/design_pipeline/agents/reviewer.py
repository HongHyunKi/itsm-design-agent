"""원문 대비 설계 의미 검토 역할."""

import json

from langgraph.runtime import Runtime
from pydantic import ValidationError

from app.schemas.design import Review
from app.services.design_pipeline import model_client
from app.services.design_pipeline.errors import failure
from app.services.design_pipeline.state import Context, State

REVIEW = """원문과 설계를 대조하여 누락, 모순, 확인 필요 사항을 검토한다.
자동 수정하지 않는다. 판단은 사람이 확인할 후보로 제시한다.
원문에 없는 일반 모범사례나 정책은 누락으로 단정하지 말고 confirmation(확인 질문)으로 제시한다.
정상 일치 확인은 findings에 넣지 않는다. 명시되지 않은 업무 정책을 필수라고 단정하지 않는다.
related_ids는 allowed_related_ids에 있는 문자열만 사용한다. 컬럼명·설명·임의 ID는 넣지 않는다.
evidence는 source의 연속 부분문자열만 그대로 복사한다. design의 내용·필드명을 인용하지 않는다.
source에 없는 정책이나 설계 문제는 evidence=[]로 두고 description에서 설명한다.
DB 실행 검증은 수행되지 않았다. 구조 통과를 업무 의미 정확성으로 간주하지 않는다.
"""


async def review(state: State, runtime: Runtime[Context]):
    ids = (
        {r.id for r in state["design"].requirements}
        | {f.id for f in state["design"].functions}
        | {t.name for t in state["design"].data_model.tables}
    )
    payload = json.dumps(
        {"source": state["source"], "design": state["design"].model_dump(), "allowed_related_ids": sorted(ids)},
        ensure_ascii=False,
    )
    raw, call = await model_client.call_model(payload, "review", Review, runtime.context, REVIEW)
    try:
        result = Review.model_validate_json(raw)
    except ValidationError:
        raise failure("invalid_review_output", "검토 결과가 스키마와 일치하지 않습니다.", "review") from None
    issues = []
    for i, finding in enumerate(result.findings):
        if not set(finding.related_ids) <= ids:
            issues.append(f"findings[{i}].related_ids: 존재하지 않는 참조")
        if any(q not in state["source"] for q in finding.evidence):
            issues.append(f"findings[{i}].evidence: 원문 인용 불일치")
    if issues:
        raise failure(
            "invalid_review_reference", "검토 결과의 참조 또는 원문 인용이 잘못되었습니다.", "review", issues=issues
        )
    return {"review": result, "calls": [call]}
