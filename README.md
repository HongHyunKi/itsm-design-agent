# ITSM 요구사항 기반 설계 에이전트

서비스 요청·장애 관리 요구사항에서 기능 명세, 데이터 모델, ERD·DDL, 추적표와 검토 결과를 만드는 프로젝트입니다. 목표 제품에는 문서 업로드와 설계 결과를 확인하는 웹 UI가 포함됩니다. 현재 구현은 `backend/`의 텍스트 입력 API이며, 이후 구현 범위와 작업 상태는 기획·설계 문서에서 관리합니다.

현재 `POST /api/v1/design`은 LangGraph의 `generate → validate → render → review`를 한 요청에서 실행합니다. 정상 경로에서 Anthropic 모델을 생성·검토에 각각 한 번 호출하고, 구조 검증에 실패하면 ERD·DDL 생성과 의미 검토를 실행하지 않습니다.

이 4단계 그래프는 `backend/app/services/design_pipeline/`에서 파일 책임을 나눕니다. `graph.py`·`state.py`는 실행 흐름과 상태, `model_client.py`·`errors.py`는 Anthropic 호출과 단계 오류, `agents/design_generator.py`·`agents/reviewer.py`는 생성·검토 역할, `nodes/structure_validation.py`·`nodes/artifact_render.py`는 결정적 검사·변환을 맡습니다. `services/design.py`는 API 서비스 진입점이고 공통 모델 규칙은 `services/design_model.py`에 남습니다. 문서·요구사항·기능·데이터 전문 역할과 사용자 답변·DB 검증 노드는 [후속 구조안](docs/plans/백엔드_통합_구조.md)에 구분해 두었습니다.

- [기획·설계 문서 및 개발 계획](docs/plans/README.md)
- [대표 시나리오와 디버깅](backend/scenarios/README.md)
- [작업 규칙](AGENTS.md)

## 백엔드 실행

Python 3.12를 사용합니다. 설계 API 실행에는 DB가 필요하지 않습니다.

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
test -f .env || cp .env.example .env
# 편집기로 .env의 ANTHROPIC_API_KEY를 설정
uvicorn app.main:app --reload --host 127.0.0.1
```

API 키를 명령행·채팅·문서에 넣지 마세요. 키가 없어도 서버와 `GET /health`는 시작하며 설계 요청은 503을 반환합니다. API 계약과 요청·응답 예시는 <http://127.0.0.1:8000/docs>에서 확인할 수 있습니다.

```bash
curl --fail-with-body http://127.0.0.1:8000/api/v1/design \
  -H 'Content-Type: application/json' \
  -d '{"text":"사용자가 제목을 입력해 서비스 요청 또는 장애를 등록하고 유형과 제목을 저장한다."}'
```

입력은 JSON의 `text` 1~12,000자이며 공백만 있는 입력은 거절합니다. 응답은 근거가 연결된 요구사항, 기능 명세, 공통 데이터 모델, Mermaid ERD, PostgreSQL DDL, 추적표, 검토 결과를 포함합니다. `verification.structure=passed`는 코드의 구조 검사를 통과했다는 뜻이고, `semantic_review=completed`는 모델 검토 호출 완료를 뜻합니다. 생성 DDL을 DB에서 실행하지 않으므로 `database_execution=not_run`이며 완료 응답도 `completed_with_warnings`입니다.

모델 출력이 잘리면 502 `model_output_truncated`를 반환합니다. 입력 범위를 줄이거나 `ANTHROPIC_MAX_TOKENS`를 조정해 다시 요청하세요. 자동 재시도나 성공 예시로의 대체는 없습니다. 다른 오류 코드와 상세 응답 형태는 `/docs`를 기준으로 확인하세요.

### LangGraph Studio로 그래프 보기

`backend/langgraph.json`이 `design` 그래프를 등록합니다. `langgraph-cli[inmem]`은 앱과 OpenTelemetry 버전이 충돌하므로 앱 `.venv`가 아닌 별도 가상환경에 설치합니다.

```bash
cd backend
python3.12 -m venv .venv-studio
.venv-studio/bin/pip install -r requirements.txt "langgraph-cli[inmem]"
.venv-studio/bin/langgraph dev
```

Studio 실행은 `.env`의 설정으로 실제 모델을 호출합니다. 입력은 `{"source": "..."}`이며, 그래프가 API와 같은 1~12,000자·공백 입력 제한을 모델 호출 전에 검사합니다. 위반 시 `failure`에 `validation_failed`와 `generate` 단계가 남습니다. 다른 단계의 오류도 `failure`에 코드와 단계가 남습니다.

## 설정

기본값은 [backend/.env.example](backend/.env.example)에 있습니다. `backend/`에서 서버를 실행할 때 `.env`를 읽고, 같은 이름의 환경변수가 우선합니다. 변경 후 서버를 재시작하세요.

| 설정 | 기본값 | 용도 |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | 빈 값 | 설계 API의 실제 모델 호출 |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5` | 생성·검토에 사용할 모델 |
| `ANTHROPIC_MAX_TOKENS` | `8192` | 호출별 출력 한도 |
| `ANTHROPIC_TIMEOUT_SECONDS` | `120` | 호출별 시간 제한(초) |
| `ENABLE_PROMPT_CACHING` | `true` | 고정 시스템 프롬프트 캐싱 설정 |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | 빈 값 | 둘 다 있을 때 메타데이터 추적 활성화 |
| `LANGFUSE_BASE_URL` | `https://cloud.langfuse.com` | Langfuse 서버 주소 |
| `LANGFUSE_TRACING_ENABLED` | `true` | 추적 활성화 여부 |

캐싱 설정은 실제 캐시 적중을 뜻하지 않습니다. 사용량은 응답의 `model_calls[].cache_creation_input_tokens`와 `cache_read_input_tokens`로 확인합니다. `tracing_enabled=true`도 Langfuse 원격 수신을 보장하지 않으므로 프로젝트 화면에서 확인해야 합니다. 추적에는 원문·전체 프롬프트·전체 응답 대신 실행 메타데이터만 보냅니다.

## 대표 시나리오와 검증

저장소 루트의 `debug-design`은 기준 응답을 재생하거나 실제 모델을 호출해 그래프 단계를 로컬 보고서로 보여줍니다. 다음 명령은 저장소 루트에서 실행하며, 옵션과 결과 해석은 [시나리오 안내](backend/scenarios/README.md)를 따르세요.

```bash
./debug-design
./debug-design --fault bad-reference
./debug-design --mode live --max-tokens 8192
```

기준 응답 재생은 모델 품질 검증이 아닙니다. 디버거는 단계별 구조·변환·검토 검사 결과를 따로 표시하며, 실행 단계가 끝나도 계약 검사가 실패하면 `contract_check_failed`로 기록합니다. 보고서는 `backend/.debug-runs/`에 저장됩니다. 코드 검사 명령은 다음과 같습니다.

```bash
cd backend
source .venv/bin/activate
pytest -q
ruff check .
ruff format --check .
```

현재 API는 텍스트만 받습니다. 입력은 모델 API로 전송됩니다. 결과와 원문을 DB에 저장하거나 중단된 요청을 재개하지 않습니다. 생성 SQL도 실행하지 않습니다. DB 연결·Alembic 마이그레이션 구성만 남아 있고 운영 테이블은 아직 없으며, 설계 API는 DB를 사용하지 않습니다.
