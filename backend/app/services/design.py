"""기존 텍스트 설계 API의 서비스 진입점."""

from app.core.config import Settings
from app.core.tracing import get_tracer, observation
from app.schemas.design import DesignResponse
from app.services.design_pipeline.errors import as_error
from app.services.design_pipeline.graph import graph


async def run_design(source: str, settings: Settings) -> DesignResponse:
    tracer = get_tracer(settings)
    with observation(tracer, "design", metadata={"input_characters": len(source)}):
        result = await graph.ainvoke({"source": source}, context={"settings": settings, "tracer": tracer})
        if failed := result.get("failure"):
            raise as_error(failed)
        return DesignResponse(
            design=result["design"],
            mermaid_erd=result["mermaid_erd"],
            postgresql_ddl=result["postgresql_ddl"],
            review=result["review"],
            model_calls=result["calls"],
            prompt_caching_enabled=settings.enable_prompt_caching,
            tracing_enabled=tracer is not None,
            warnings=[
                "DDL은 DB에서 실행 검증하지 않은 초안입니다.",
                "의미 검토와 가정·확인 질문은 사람이 확인해야 합니다.",
            ],
        )
