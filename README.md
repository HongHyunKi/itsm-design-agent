# fastapi-boilerplate

여러 프로젝트에서 쓸 수 있는 FastAPI 보일러플레이트입니다.

## 기술 스택

| 구분 | 사용 기술 |
|---|---|
| 언어 | Python 3.12 |
| 웹 프레임워크 | FastAPI |
| ASGI 서버 | Uvicorn |
| 데이터 검증 | Pydantic v2 |
| 설정 관리 | pydantic-settings |
| DB | PostgreSQL 16 (드라이버: psycopg 3) |
| ORM | SQLAlchemy 2 |
| DB 마이그레이션 | Alembic |
| 테스트 | pytest |
| 린트, 포맷 | ruff |
| 실행 환경 | Docker, Docker Compose |
| CI | GitHub Actions |

## 실행 (Docker, 기본)

```bash
cd backend
cp .env.example .env
docker compose up --build        # api: http://localhost:8000, db: Postgres 16
```

- 앱이 시작될 때 `alembic upgrade head`를 실행하고 샘플 데이터를 시드합니다.
- API 문서: http://localhost:8000/docs
- 헬스체크: `GET /health`
- API: `/api/v1/items`
- Postgres 호스트 포트는 `.env`의 `POSTGRES_PORT`로 바꿉니다. compose와 `DATABASE_URL`이 같은 값을 씁니다.
- 컨테이너 안에서 테스트: `docker compose run --rm api pytest`

## 로컬 실행 (DB만 Docker)

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d db
uvicorn app.main:app --reload
```

DB 없이 가볍게 돌리려면 `.env`에서 `DATABASE_URL=sqlite:///./app.db`로 바꾸면 됩니다.

## 테스트

```bash
cd backend
pytest                                   # 기본: 인메모리 SQLite (DB 서버 불필요)
TEST_DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/app pytest   # Postgres로 실행
```

`TEST_DATABASE_URL`을 지정하면 테스트마다 테이블을 만들고 지우므로 반드시 테스트 전용 DB를 쓰세요.

## 린트와 포맷 (ruff)

```bash
cd backend
ruff check --fix .
ruff format .
```

설정은 `backend/pyproject.toml`에 있습니다.

## CI

`.github/workflows/ci.yml`이 `main` 브랜치 push와 PR마다 다음을 실행합니다.

1. ruff 린트와 포맷 검사
2. Postgres에서 `alembic upgrade head`와 `downgrade base` 왕복
3. Postgres에서 pytest(계층 규칙 테스트 포함)

## 마이그레이션

```bash
# 모델을 추가했다면 먼저 app/models/__init__.py에 import를 추가합니다
alembic revision --autogenerate -m "add something"
alembic upgrade head
```

## 구조와 계층 규칙

```
backend/app/
├── api/v1/        라우터만 둡니다. deps.py에 Annotated Depends 별칭(SettingsDep, DbDep, LoggerDep, ...)
├── schemas/       요청/응답 모델. common.py: ErrorResponse {code, message, detail}
├── services/      비즈니스 로직과 트랜잭션 경계(commit)
├── repositories/  DB 조회와 저장만 합니다(판단 로직 없음)
├── models/        SQLAlchemy ORM. 새 모델은 __init__.py에 등록합니다
├── db/            session, init_db(alembic upgrade), seed, migrations/
├── integrations/  ports.py(Protocol + 결과 dataclass), 어댑터, factory.py(mock/live 분기)
└── core/          config, logging, exceptions, security
```

`tests/test_layers.py`가 아래 규칙을 강제합니다. 위반하면 테스트가 실패하고, 실패 메시지에 고치는 방법이 나옵니다.

1. `models`는 `app.models` 밖의 `app.*`를 import하지 않습니다.
2. `api`는 `repositories`와 `models`를 import하지 않습니다(`services`만 호출).
3. `services`는 `api`를 import하지 않습니다.
4. `repositories`는 `services`와 `api`를 import하지 않습니다.
5. `services`는 `integrations.factory`와 `integrations.ports`만 import합니다.

## 새 리소스 추가 순서

`models/<name>.py` → `models/__init__.py` 등록 → `alembic revision --autogenerate` → `schemas/` → `repositories/` → `services/` → `deps.py`에 `XxxServiceDep` 추가 → `api/v1/<name>.py` → `main.py`에서 `include_router`

## 외부 연동 추가

1. `ports.py`에 Protocol과 결과 dataclass를 정의합니다.
2. `integrations/mock_<name>.py`와 `integrations/<vendor>_<name>.py`에 어댑터를 구현합니다.
3. `factory.py`에서 `settings.is_live`로 분기합니다. live 어댑터는 함수 안에서 import하고 `@lru_cache`로 재사용합니다.

예시로 `Notifier` 포트와 mock 어댑터만 들어 있습니다. live 어댑터는 아직 없어서 `APP_MODE=live`로 실행하면 `NotImplementedError`가 납니다.

## 에러 응답

`AppError` 하위 예외(`NotFound` 404, `AuthFailed` 401, `PermissionDenied` 403, `ValidationFailed` 422, `RateLimited` 429)와 요청 검증 실패는 모두 같은 형태로 응답합니다.

```json
{"code": "not_found", "message": "Item 1 not found", "detail": null}
```

처리하지 않은 예외는 500 `{"code": "internal_error", ...}`로 응답합니다. 원인은 로그에만 남기고 응답에는 싣지 않습니다.

검증 실패 응답과 로그에는 위치(`loc`)와 사유(`msg`, `type`)만 남기고, 사용자가 보낸 입력값은 남기지 않습니다.
모든 응답에는 `X-Request-ID` 헤더가 붙습니다(요청에 없으면 8자리를 새로 만듭니다). 같은 ID가 로그에도 찍힙니다.

## 운영 설정

`APP_MODE=live`인데 `SECRET_KEY`가 기본값(`change-me`)이거나 비어 있으면 앱이 시작되지 않습니다.
