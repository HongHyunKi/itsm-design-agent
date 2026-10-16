"""현재 동기 설계 실행의 그래프 상태와 런타임 의존성."""

import operator
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from app.core.config import Settings, get_settings
from app.schemas.design import Design, ModelCall, Review


# 단계 실패. 노드의 AppError를 직렬화 가능한 값으로 옮겨 그래프가 실패 상태로 끝나게 한다.
class Failure(TypedDict):
    code: str
    message: str
    status: int
    detail: Any


class State(TypedDict, total=False):
    source: str
    raw: str
    design: Design
    mermaid_erd: str
    postgresql_ddl: str
    review: Review
    # 노드는 자기 호출만 반환하고 누적은 리듀서가 맡는다(병렬 노드에서도 안전).
    calls: Annotated[list[ModelCall], operator.add]
    failure: Failure


# 실행 환경: 노드에 설정과 선택적 Langfuse 추적 객체를 전달한다.
# 기본값은 LangGraph Studio처럼 context 없이 실행할 때 쓴다.
@dataclass
class Context:
    settings: Settings = field(default_factory=get_settings)
    tracer: Any = None
