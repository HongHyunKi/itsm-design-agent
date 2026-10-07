"""Swagger 설명용 예시. 실제 모델 출력이나 실측 사용량이 아니다."""

REQUEST_EXAMPLES = {
    "service_request": {
        "summary": "서비스 요청 · 짧은 기본 예시",
        "value": {"text": "사용자는 제목을 입력해 서비스 요청을 등록하고 제목을 저장한다."},
    },
    "incident": {
        "summary": "장애 관리 · 접수와 처리",
        "value": {"text": "사용자가 장애 제목과 내용을 신고하면 담당자가 조치 내용을 기록하고 해결 상태로 변경한다."},
    },
    "combined": {
        "summary": "서비스 요청·장애 · 통합 등록",
        "value": {"text": "사용자가 제목을 입력해 서비스 요청 또는 장애를 등록하고 유형과 제목을 저장한다."},
    },
}

RESPONSE_EXAMPLE = {
    "status": "completed_with_warnings",
    "design": {
        "requirements": [
            {
                "id": "C-REQ-1",
                "text": "요청 제목 저장",
                "kind": "functional",
                "provenance": "source",
                "evidence": ["제목을 저장한다"],
                "assumption": "",
                "needs_confirmation": False,
                "needs_storage": True,
            }
        ],
        "functions": [
            {
                "id": "C-FUN-1",
                "name": "요청 등록",
                "description": "요청 제목 저장",
                "actor": "사용자",
                "inputs": ["제목"],
                "outputs": ["요청 ID"],
                "preconditions": [],
                "rules": ["제목 필수"],
                "exceptions": ["빈 제목 거절"],
                "priority": "undecided",
            }
        ],
        "data_model": {
            "tables": [
                {
                    "name": "request",
                    "description": "요청",
                    "columns": [
                        {
                            "name": "id",
                            "type": "bigint",
                            "nullable": False,
                            "primary_key": True,
                            "unique": False,
                            "references": None,
                        },
                        {
                            "name": "title",
                            "type": "text",
                            "nullable": False,
                            "primary_key": False,
                            "unique": False,
                            "references": None,
                        },
                    ],
                }
            ]
        },
        "traceability": [
            {
                "requirement_id": "C-REQ-1",
                "function_ids": ["C-FUN-1"],
                "tables": ["request"],
                "reason": "요청 저장",
                "no_storage_reason": "",
            }
        ],
        "assumptions": ["식별자는 애플리케이션에서 부여하는 설계 제안"],
        "questions": ["제목의 최대 길이는 얼마인가요?"],
    },
    "mermaid_erd": "erDiagram\n    request {\n        bigint id PK\n        text title\n    }",
    "postgresql_ddl": "-- 미검증 초안: DB 실행 검증 미실시\n"
    "\n"
    'CREATE TABLE "request" (\n'
    '    "id" BIGINT NOT NULL PRIMARY KEY,\n'
    '    "title" TEXT NOT NULL\n'
    ");",
    "review": {"findings": [], "summary": "추가 누락 후보 없음. 확인 질문 검토 필요."},
    "verification": {"structure": "passed", "semantic_review": "completed", "database_execution": "not_run"},
    "warnings": ["DDL은 DB에서 실행 검증하지 않은 초안입니다.", "의미 검토와 가정·확인 질문은 사람이 확인해야 합니다."],
    "model_calls": [
        {
            "stage": "generate",
            "model": "claude-haiku-4-5-20251001",
            "duration_ms": 8000,
            "input_tokens": 2000,
            "output_tokens": 800,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        {
            "stage": "review",
            "model": "claude-haiku-4-5-20251001",
            "duration_ms": 8000,
            "input_tokens": 2000,
            "output_tokens": 800,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    ],
    "prompt_caching_enabled": True,
    "tracing_enabled": False,
}
