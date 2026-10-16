"""검증된 공통 모델의 Mermaid ERD·PostgreSQL DDL 변환 노드."""

from langgraph.runtime import Runtime

from app.core.tracing import observation
from app.services.design_model import render_model
from app.services.design_pipeline.state import Context, State


def render(state: State, runtime: Runtime[Context]):
    with observation(runtime.context.tracer, "render"):
        erd, ddl = render_model(state["design"])
        return {"mermaid_erd": erd, "postgresql_ddl": ddl}
