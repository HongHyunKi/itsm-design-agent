# ITSM 요구사항 기반 시스템 자동 설계 에이전트

서비스 요청·장애 관리 요구사항을 설계 초안으로 변환하는 **백엔드 MVP**입니다. 실제 ITSM 운영 시스템을 구현하는 프로젝트가 아닙니다. 프론트엔드는 포함하지 않습니다.

`POST /api/v1/design` 한 요청에서 LangGraph의 `generate → validate → render → review`를 실행합니다. 정상 경로는 Anthropic 생성·검토 2회이며 자동 재시도하지 않습니다. 요구사항·근거, 기능 명세, 공통 데이터 모델, Mermaid ERD·PostgreSQL DDL, 추적표, 누락·모순·확인 사항을 JSON으로 반환합니다. 구조 오류는 ERD·DDL 생성과 의미 검토를 차단합니다.

- [기획·설계 문서 목록](docs/plans/README.md): 전체 제품의 장기 목표
- [이번 실행 계획과 검증 기록](docs/plans/tasks/001-백엔드-MVP.md): 현재 범위·실측·제한
- [작업 규칙](AGENTS.md)

## 실행: DB 없이

Python 3.12를 사용합니다. 모든 명령은 이 저장소에서 시작하며 다른 저장소는 필요하지 않습니다.

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# 기존 .env를 덮어쓰지 않습니다.
test -f .env || cp .env.example .env
# 편집기로 .env의 ANTHROPIC_API_KEY를 직접 설정합니다.
uvicorn app.main:app --reload --host 127.0.0.1
```

API 키를 명령행·채팅·문서에 넣지 마세요. 로컬 `backend/.env`는 Git 및 Docker 빌드에서 제외됩니다. 키가 없어도 서버와 `/health`는 시작하고, 설계 요청만 503을 반환합니다. `APP_MODE=mock`은 기존 items 예제의 설정이며 설계 API는 항상 실제 Anthropic을 호출합니다. 설계 API에 `APP_MODE=live`를 설정할 필요는 없습니다.

- API 문서: <http://127.0.0.1:8000/docs> — 한글 설명, design 요청 예시 3종과 성공·오류 응답 예시 제공. items는 샘플 코드로 표시합니다.
- 헬스체크: `GET /health`
- 설계: `POST /api/v1/design` (기존 `/api/v1` 경로 규칙 유지)

```bash
curl --fail-with-body http://127.0.0.1:8000/api/v1/design \
  -H 'Content-Type: application/json' \
  -d '{"text":"사용자가 제목을 입력해 서비스 요청 또는 장애를 등록하고 유형과 제목을 저장한다."}'
```

입력은 JSON `text` 하나이며 1~12,000자, 공백만 있는 입력은 거절합니다. 길이 상한은 출력 완료 보장이 아닙니다. 기본 8192토큰으로도 긴 설계가 잘리면 502 `model_output_truncated`를 반환합니다. `ANTHROPIC_MAX_TOKENS`를 늘리거나 요구사항 범위를 줄여 다시 요청하세요. 서버가 원문을 자동으로 줄이거나 성공 샘플로 대체하지 않습니다.

## 환경변수

기본값과 빈 키 항목은 [backend/.env.example](backend/.env.example)에 있습니다. `.env`는 `backend/`에서 실행할 때 읽으며 환경변수가 같은 이름의 `.env` 설정보다 우선합니다. 변경 후 서버를 재시작하세요.

| 이름                                      | 기본값                     | 의미                                            |
| ----------------------------------------- | -------------------------- | ----------------------------------------------- |
| ANTHROPIC_API_KEY                         | 빈 값                      | 실제 호출에 필요, 로컬 .env에만 보관            |
| ANTHROPIC_MODEL                           | claude-haiku-4-5           | 생성과 검토에 같은 모델 사용                    |
| ANTHROPIC_MAX_TOKENS                      | 8192                       | 호출별 출력 상한, 1~64000                       |
| ANTHROPIC_TIMEOUT_SECONDS                 | 120                        | 호출별 전체 시간 제한, 최대 600초               |
| ENABLE_PROMPT_CACHING                     | true                       | 고정 시스템 프롬프트에 ephemeral 캐시 경계 설정 |
| INITIALIZE_DATABASE                       | false                      | 기존 items용 DB 마이그레이션·시드 실행 여부     |
| LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY | 빈 값                      | 둘 다 설정해야 추적 활성화                      |
| LANGFUSE_BASE_URL                         | https://cloud.langfuse.com | 프로젝트가 위치한 EU/US/자체 호스팅 주소        |
| LANGFUSE_TRACING_ENABLED                  | true                       | false이면 자격증명이 있어도 추적 비활성화       |

공식 [구조화 출력](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) 방식으로 `messages.create(output_config.format=...)`와 SDK의 Pydantic 스키마 변환을 사용합니다. `stop_reason`을 먼저 확인한 뒤 Pydantic 및 코드로 검사합니다.

[프롬프트 캐싱](https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching)은 **설정 활성화와 적중이 다릅니다**. Haiku 4.5는 캐시 대상 접두어가 최소 4,096토큰이어야 합니다. 짧은 고정 프롬프트는 캐시가 만들어지지 않을 수 있으며, 길이 맞추기용 텍스트를 추가하지 않습니다. `model_calls[].cache_creation_input_tokens`와 `cache_read_input_tokens`가 실제 사용량입니다. 읽기 토큰이 0이면 적중으로 보고하지 않습니다. 생성·검토는 스키마와 프롬프트가 달라 캐시 공유를 보장하지 않습니다.

## 응답

다음은 **형태 설명용 축약 예시**입니다. 배열의 실제 항목 구조는 `/docs`의 `DesignResponse`를 확인하세요. `design.requirements`는 provenance/evidence/assumption으로 원문 사실과 제안을 구분하며 `functions`에는 입력·출력·선행 조건·규칙·예외·우선순위가 있습니다.

```json
{
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
        "needs_confirmation": false,
        "needs_storage": true
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
        "priority": "undecided"
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
              "nullable": false,
              "primary_key": true,
              "unique": false,
              "references": null
            },
            {
              "name": "title",
              "type": "text",
              "nullable": false,
              "primary_key": false,
              "unique": false,
              "references": null
            }
          ]
        }
      ]
    },
    "traceability": [
      {
        "requirement_id": "C-REQ-1",
        "function_ids": ["C-FUN-1"],
        "tables": ["request"],
        "reason": "요청 저장",
        "no_storage_reason": ""
      }
    ],
    "assumptions": ["식별자는 애플리케이션에서 부여하는 설계 제안"],
    "questions": ["제목의 최대 길이는 얼마인가요?"]
  },
  "mermaid_erd": "erDiagram\n    request {\n        bigint id PK\n        text title\n    }",
  "postgresql_ddl": "-- 미검증 초안: DB 실행 검증 미실시\n\nCREATE TABLE \"request\" (\n    \"id\" BIGINT NOT NULL PRIMARY KEY,\n    \"title\" TEXT NOT NULL\n);",
  "review": {
    "findings": [],
    "summary": "추가 누락 후보 없음. 확인 질문 검토 필요."
  },
  "verification": {
    "structure": "passed",
    "semantic_review": "completed",
    "database_execution": "not_run"
  },
  "warnings": [
    "DDL은 DB에서 실행 검증하지 않은 초안입니다.",
    "의미 검토와 가정·확인 질문은 사람이 확인해야 합니다."
  ],
  "model_calls": [],
  "prompt_caching_enabled": true,
  "tracing_enabled": false
}
```

위 예시에서 `model_calls`만 생략했습니다. 실제 완료 응답에는 generate/review 각각의 모델명·시간(ms)·입력/출력·캐시 토큰 기록이 있습니다. `semantic_review=completed`는 검토 호출 완료이며 의미상 정확성 보증이 아닙니다. DB 실행 미검증이므로 완료 응답도 항상 경고 상태입니다. 저장 불필요 요구사항은 `needs_storage=false`, 빈 `tables`와 `no_storage_reason`으로 정상 처리합니다.

| HTTP | code                                             | 처리                                                            |
| ---- | ------------------------------------------------ | --------------------------------------------------------------- |
| 422  | validation_failed                                | 빈 입력·입력 길이·요청 형식 수정                                |
| 422  | structure_invalid                                | 생성 스키마·중복 ID·원문 인용·PK/FK·추적 오류; 후속 단계 미실행 |
| 503  | model_not_configured                             | 로컬 .env에 API 키 설정                                         |
| 504  | model_timeout                                    | ANTHROPIC_TIMEOUT_SECONDS 또는 입력 범위 확인                   |
| 502  | model_output_truncated                           | ANTHROPIC_MAX_TOKENS 또는 입력 범위 조정                        |
| 502  | model_api_failed / model_incomplete              | 외부 API 실패·거부; 키·한도·연결 확인                           |
| 502  | invalid_review_output / invalid_review_reference | 의미 검토 결과 형식·참조 오류                                   |

오류는 기존 `{code, message, detail}` 형태이며 stage와 안전한 오류 정보만 반환합니다. 키·공급자 오류 본문·잘린 생성 본문은 반환하지 않습니다. `X-Request-ID`로 요청 로그를 연결합니다.

## Langfuse 활성화

[공식 Python SDK 설정](https://langfuse.com/docs/observability/sdk/overview)에 따라 로컬 `.env`에 프로젝트의 `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`을 설정하고 재시작합니다. 별도 `auth_check`가 핵심 API를 막지 않으며 초기화·추적 기록·전송 실패는 설계 생성과 분리됩니다.

기본 추적은 design 및 네 단계의 시간, 모델명, 토큰 사용량, 종료 사유, 안전한 오류 코드와 입력 문자 수만 기록합니다. 원문·전체 프롬프트·전체 생성 응답·예외 본문은 보내지 않습니다. `tracing_enabled=true`는 SDK 추적 활성화이며 원격 서버 수신 성공을 보장하지 않습니다. 프로젝트 화면에서 수신을 확인해야 합니다. 자격증명이 없으면 핵심 API는 계속 동작합니다.

## 대표 시나리오 디버깅 (5~10개 추가 예정)

[대표 입력·기준 출력과 실행 안내](backend/scenarios/README.md)를 제공합니다. 단계별 입력·출력, 모델에 보낸 프롬프트, 검증 오류, 의미 검토와 기준 결과 비교를 로컬 HTML 보고서에서 확인할 수 있습니다.

```bash
# 저장소 루트에서 실행. 가상환경을 미리 활성화하지 않아도 됩니다.
./debug-design                                                # 기준 응답 재생, 외부 호출 없음
./debug-design --fault bad-reference                          # FK 오류와 후속 단계 생략
./debug-design --mode live --max-tokens 8192                   # 실제 Claude, 이번 실행만 출력 한도 변경
./debug-design --help                                         # 옵션 확인
```

`debug-design`은 `backend/.venv/bin/python`으로 기존 디버거를 실행합니다. 최초 가상환경·의존성 설치는 위 실행 안내를 따르세요. 터미널에 출력된 `report.html`을 여세요. 보고서는 `backend/.debug-runs/`에 실행별로 저장됩니다. 기준 응답 재생은 실제 모델 품질 검증이 아니며, 모델 도구 선택 호출이 없는 현재 흐름의 Python 실행과 모델 호출을 구분해 보여줍니다.

## 검증

자동 테스트는 공식 Anthropic SDK의 HTTP 전송만 대체하며 외부 연결·비용 없이 실제 그래프 분기와 변환기를 실행합니다.

```bash
cd backend
source .venv/bin/activate
pytest -q
ruff check .
ruff format --check .
```

현재 자동 테스트 59개 및 린트·포맷 검사가 통과했습니다. 기존 MVP 검증 당시 PostgreSQL 16 임시 DB에서 마이그레이션 upgrade/downgrade와 당시 테스트 47개도 통과했습니다. 현재 59개 검사는 외부 DB·모델 연결 없이 실행했습니다. Uvicorn의 DB 없는 시작·HTTP 헬스체크·입력 검증을 확인했습니다. 기본 모델·2048토큰 설정의 실제 Claude 최종 실행은 HTTP 200, 약 24초였습니다. 개발 중 실제 5회 중 2회는 검토 인용/참조 검사에서 실패했고, 최종 프롬프트를 보완했습니다. Langfuse 원격 연결은 미검증이며 실제 캐시 생성·읽기 토큰은 모두 0이었습니다. 상세는 [실행 기록](docs/plans/tasks/001-백엔드-MVP.md)을 확인하세요. 기존 DB 마이그레이션 검사는 **생성 DDL 실행 검증이 아닙니다**.

기존 CI는 PostgreSQL 16에서 아래 검사도 수행합니다. 테스트 전용 DB만 사용하세요. pytest는 테이블을 생성·삭제합니다.

```bash
DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/app alembic upgrade head
DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/app alembic downgrade base
TEST_DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/app pytest
```

## 현재 제한과 기존 기반 코드

자료형은 integer/bigint/text/boolean/date/timestamptz/uuid, 제약은 단일 PK·컬럼 UNIQUE·NULL·단일 FK만 지원합니다. 식별자는 ASCII 소문자 영문으로 시작하는 영문·숫자·밑줄 63자 이하이며 SQL에서는 인용합니다. 모든 테이블 생성 후 FK를 추가하므로 순환 참조도 변환할 수 있습니다. 같은 모델을 코드로 ERD·DDL에 변환하며 자유 SQL을 받거나 실행하지 않습니다. 복합 키·CHECK·인덱스·기본값·삭제 정책은 지원하지 않습니다. 업무 규칙은 기능 명세와 검토 결과로 확인해야 합니다.

입력은 모델 API로 전송됩니다. 결과·원문을 DB에 보존하지 않으며 요청이 중단되면 이어서 실행할 수 없습니다. UI, 업로드·다운로드, 프로젝트 관리, 인증, 큐·워커·상태 조회, RAG와 자동 수정은 제외합니다. 로컬 사용 기준이며 서비스 품질 평가는 별도입니다.

기존 `/api/v1/items`, SQLAlchemy·Alembic 코드와 계층 규칙 테스트는 유지했습니다. 이 예제 API가 필요하면 DB를 준비하고 `INITIALIZE_DATABASE=true`로 실행하세요. `backend/compose.yaml`은 기존 DB 포함 데모 구성이며 `docker compose up --build`가 마이그레이션과 mock 시드를 수행합니다. 설계 API는 해당 DB를 사용하지 않습니다. 기존 `APP_MODE=live`에서는 별도 SECRET_KEY가 필요하며 예제 notifier의 live 구현은 없습니다.

```text
backend/app/
├── api/v1/design.py       HTTP 계약
├── schemas/design.py      입력·생성·검토·응답 스키마
├── services/design.py     단일 그래프와 Anthropic 호출
├── services/design_model.py  구조 검사·ERD·DDL 변환
└── core/tracing.py        선택적 메타데이터 추적
```
