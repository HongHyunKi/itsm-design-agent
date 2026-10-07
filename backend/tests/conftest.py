import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.main import app
from app.models import Base


@pytest.fixture
def client() -> Iterator[TestClient]:
    # TEST_DATABASE_URL이 있으면 그 DB(Postgres 등), 없으면 인메모리 SQLite를 씁니다.
    # 테스트마다 테이블을 만들고 지우므로 반드시 테스트 전용 DB를 지정하세요.
    # lifespan(마이그레이션, 시드)은 돌리지 않도록 TestClient를 `with` 없이 씁니다.
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        engine = create_engine(url)
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        with TestingSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
