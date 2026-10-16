"""현재 텍스트 설계 API의 유일한 LangGraph 실행 그래프."""

from langgraph.graph import END, START, StateGraph

from app.services.design_pipeline.agents.design_generator import generate
from app.services.design_pipeline.agents.reviewer import review
from app.services.design_pipeline.errors import guarded
from app.services.design_pipeline.nodes.artifact_render import render
from app.services.design_pipeline.nodes.structure_validation import validate
from app.services.design_pipeline.state import Context, State


def stop_on_failure(next_node: str):
    return lambda state: END if "failure" in state else next_node


builder = StateGraph(State, context_schema=Context)
for node in (generate, validate, render, review):
    builder.add_node(node.__name__, guarded(node))
builder.add_edge(START, "generate")
builder.add_conditional_edges("generate", stop_on_failure("validate"), ["validate", END])
builder.add_conditional_edges("validate", stop_on_failure("render"), ["render", END])
builder.add_conditional_edges("render", stop_on_failure("review"), ["review", END])
builder.add_edge("review", END)
graph = builder.compile()
