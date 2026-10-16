"""현행 통합 설계 생성 역할. 향후 요구사항·기능·데이터 역할로 분리한다."""

import json

from langgraph.runtime import Runtime
from pydantic import ValidationError

from app.schemas.design import Design, DesignRequest
from app.services.design_pipeline import model_client
from app.services.design_pipeline.errors import failure
from app.services.design_pipeline.state import Context, State

GENERATE = """요구사항, 기능 명세, 최소 공통 데이터 모델과 추적표를 생성한다.
C-REQ-1, C-FUN-1 형식의 고유 ID를 사용한다. source 요구사항은 evidence 필수,
proposal은 assumption 및 needs_confirmation=true 필수다. 원문에 없는 설계 결정은 assumptions에 밝힌다.
기능의 미정 정보는 해당 필드에 미정 사유를 쓴다. 원문에 우선순위가 없으면 반드시 priority=undecided다.
중요해 보인다는 이유로 high를 추정하지 않는다.
각 요구사항당 추적 행 하나를 만들고 기능을 연결한다. 모든 기능과 테이블은 추적표에 나타나야 한다.
needs_storage=true는 테이블 필수, 저장 불필요면 tables=[]와 no_storage_reason을 작성한다.
테이블은 단일 PK, NOT NULL PK만 지원한다. FK는 같은 자료형의 PK 또는 UNIQUE에 연결한다.
자료형은 integer/bigint/text/boolean/date/timestamptz/uuid만 사용한다.
SQL 식별자는 소문자 영문으로 시작하는 영문·숫자·밑줄 63자 이하다.
복합 키/CHECK/인덱스/기본값/자동증가는 지원하지 않는다. 자동증가를 구현했다고 가정하지 않는다.
필요한 규칙은 애플리케이션 처리 또는 미정으로 functions.rules 및 questions에 기록한다.
출력 분량을 절약하되 원문 요구사항을 누락하거나 합쳐서 숨기지 않는다.
"""


async def generate(state: State, runtime: Runtime[Context]):
    try:
        source = DesignRequest.model_validate({"text": state.get("source")}).text
    except ValidationError:
        raise failure("validation_failed", "원문은 공백이 아닌 1~12,000자여야 합니다.", "generate", 422) from None
    raw, call = await model_client.call_model(
        json.dumps({"source": source}, ensure_ascii=False), "generate", Design, runtime.context, GENERATE
    )
    return {"raw": raw, "calls": [call]}
