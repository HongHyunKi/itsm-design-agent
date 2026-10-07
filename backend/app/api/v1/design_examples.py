"""Swagger 예시. scenarios의 대표 입력·기준 설계를 그대로 사용한다. 실제 모델 출력이나 실측 사용량이 아니다."""

import scenarios
from app.schemas.design import Design
from app.services.design_model import render_model

REQUEST_EXAMPLES, RESPONSE_EXAMPLES = {}, {}
for name in scenarios.names():
    text, expected = scenarios.load(name)
    erd, ddl = render_model(Design.model_validate(expected["design"]))
    REQUEST_EXAMPLES[name] = {"summary": expected["title"], "value": {"text": text}}
    RESPONSE_EXAMPLES[name] = {
        "summary": expected["title"],
        "value": {
            "status": "completed_with_warnings",
            "design": expected["design"],
            "mermaid_erd": erd,
            "postgresql_ddl": ddl,
            "review": expected["review"],
            "verification": {"structure": "passed", "semantic_review": "completed", "database_execution": "not_run"},
            "warnings": [
                "DDL은 DB에서 실행 검증하지 않은 초안입니다.",
                "의미 검토와 가정·확인 질문은 사람이 확인해야 합니다.",
            ],
            "model_calls": [
                {
                    "stage": stage,
                    "model": "claude-haiku-4-5-20251001",
                    "duration_ms": 8000,
                    "input_tokens": 2000,
                    "output_tokens": 800,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                }
                for stage in ("generate", "review")
            ],
            "prompt_caching_enabled": True,
            "tracing_enabled": False,
        },
    }
RESPONSE_EXAMPLE = next(iter(RESPONSE_EXAMPLES.values()))["value"]
