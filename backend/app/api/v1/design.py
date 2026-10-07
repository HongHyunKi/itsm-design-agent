from typing import Annotated

from fastapi import APIRouter, Body

from app.api.v1.deps import SettingsDep
from app.api.v1.design_examples import REQUEST_EXAMPLES, RESPONSE_EXAMPLE, RESPONSE_EXAMPLES
from app.schemas.common import ErrorResponse
from app.schemas.design import DesignRequest, DesignResponse
from app.services.design import run_design

router = APIRouter(tags=["design"])


@router.post(
    "/design",
    response_model=DesignResponse,
    summary="요구사항으로 ITSM 설계 초안 생성",
    description="""서비스 요청·장애 관리 요구사항을 입력하면 한 요청에서 설계 생성과 검토를 완료합니다.

실행하려면 서버의 로컬 `.env`에 `ANTHROPIC_API_KEY`가 필요합니다. 실제 모델 호출 비용이 발생합니다.

- **입력:** `text` 1~12,000자. 공백만 있는 입력은 허용하지 않습니다.
- **반환:** 요구사항과 원문 근거, 기능 명세, 공통 데이터 모델, Mermaid ERD·PostgreSQL DDL,
  요구사항↔기능↔테이블 추적표, 누락·모순·확인 사항.
- **처리:** 생성 → 구조 검증 → ERD·DDL 변환 → 의미 검토. 정상 경로에서 모델을 2회 호출합니다.
  구조 검증에 실패하면 변환·의미 검토를 실행하지 않습니다.
- **제한:** 호출당 기본 120초이며 자동 재시도하지 않습니다. 출력이 잘리면
  `ANTHROPIC_MAX_TOKENS`를 늘리거나 입력 범위를 줄이세요.

**결과 해석:** `structure=passed`는 코드의 구조 검사를 통과했다는 뜻입니다.
`semantic_review=completed`는 검토 완료이며 내용의 정확성을 보장하지 않습니다.
생성 SQL은 실행하지 않으므로 `database_execution=not_run`, 상태는 `completed_with_warnings`입니다.
`prompt_caching_enabled`는 캐싱 설정이며 실제 적중은 `cache_read_input_tokens`로 확인합니다.
`tracing_enabled`는 추적 활성화 여부이며 Langfuse 원격 수신을 보장하지 않습니다.

예시는 `backend/scenarios`의 대표 시나리오입니다. 요청은 고객이 보낸 가상의 요구사항 정의서이고,
응답은 사람이 작성한 기준 설계입니다. 실제 생성 내용·시간·토큰 수는 실행마다 달라집니다.""",
    responses={
        200: {
            "description": "설계 생성·검토 완료 (DB 실행 검증은 미실시)",
            "content": {"application/json": {"examples": RESPONSE_EXAMPLES}},
        },
        422: {
            "model": ErrorResponse,
            "description": "입력 형식·길이 오류 또는 생성 결과의 스키마·참조·추적 검증 실패",
            "content": {
                "application/json": {
                    "examples": {
                        "input": {
                            "summary": "빈 요구사항 입력",
                            "value": {
                                "code": "validation_failed",
                                "message": "Invalid request",
                                "detail": [
                                    {
                                        "loc": ["body", "text"],
                                        "msg": "String should have at least 1 character",
                                        "type": "string_too_short",
                                    }
                                ],
                            },
                        },
                        "structure": {
                            "summary": "요구사항 추적 누락",
                            "value": {
                                "code": "structure_invalid",
                                "message": "생성 결과 구조 검증 실패. ERD·DDL·의미 검토를 실행하지 않았습니다.",
                                "detail": {"stage": "validate", "issues": ["traceability: 요구사항 추적 누락"]},
                            },
                        },
                    }
                }
            },
        },
        502: {
            "model": ErrorResponse,
            "description": "모델 API 오류·출력 잘림·생성 거부 또는 검토 결과 형식·참조 오류",
            "content": {
                "application/json": {
                    "example": {
                        "code": "model_output_truncated",
                        "message": "출력 토큰 한도로 응답이 잘렸습니다. ANTHROPIC_MAX_TOKENS를 늘리거나 입력 범위를 줄이세요.",
                        "detail": {
                            "stage": "generate",
                            "usage": {
                                **RESPONSE_EXAMPLE["model_calls"][0],
                                "output_tokens": 2048,
                            },
                        },
                    }
                }
            },
        },
        503: {
            "model": ErrorResponse,
            "description": "Anthropic API 키 미설정",
            "content": {
                "application/json": {
                    "example": {
                        "code": "model_not_configured",
                        "message": "로컬 backend/.env에 ANTHROPIC_API_KEY를 설정하세요.",
                        "detail": {"stage": "generate"},
                    }
                }
            },
        },
        504: {
            "model": ErrorResponse,
            "description": "모델 호출 시간 초과",
            "content": {
                "application/json": {
                    "example": {
                        "code": "model_timeout",
                        "message": "모델 호출 시간 초과: ANTHROPIC_TIMEOUT_SECONDS를 확인하세요.",
                        "detail": {"stage": "generate"},
                    }
                }
            },
        },
    },
)
async def create_design(
    body: Annotated[DesignRequest, Body(openapi_examples=REQUEST_EXAMPLES)], settings: SettingsDep
) -> DesignResponse:
    return await run_design(body.text, settings)
