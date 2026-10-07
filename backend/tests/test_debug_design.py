import asyncio
import json

import pytest

from app.core.config import Settings
from app.schemas.design import Design
from app.services.design_model import validate_design
from scripts.debug_design import SCENARIO, execute, redact, write_html
from tests import test_design

model_api = test_design.model_api


@pytest.mark.parametrize(
    "fault,failed_stage,skipped",
    [
        (None, None, []),
        ("bad-reference", "validate", ["render", "review"]),
        ("missing-trace", "validate", ["render", "review"]),
        ("invalid-json", "validate", ["render", "review"]),
        ("truncated", "generate", ["validate", "render", "review"]),
        ("api-error", "generate", ["validate", "render", "review"]),
        ("review-reference", "review", []),
        ("semantic-omission", None, []),
    ],
)
def test_debugger_runs_real_graph_without_network(fault, failed_stage, skipped, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("기준 재생은 외부 모델을 호출하면 안 됨")

    monkeypatch.setattr("app.services.design.anthropic.AsyncAnthropic", forbidden)
    expected = json.loads((SCENARIO / "expected.json").read_text())
    before = json.dumps(expected)
    source = json.loads((SCENARIO / "request.json").read_text())["text"]
    assert not validate_design(Design.model_validate(expected["design"]), source)
    events = []
    result = asyncio.run(execute("reference", fault, Settings(_env_file=None), expected, source, events.append))
    assert json.dumps(expected) == before
    assert result["external_model_calls"] == 0
    assert {s["name"] for s in result["stages"] if s["status"] == "skipped"} == set(skipped)
    if failed_stage:
        assert result["status"] == "failed"
        assert next(s for s in result["stages"] if s["name"] == failed_stage)["status"] == "failed"
        assert result["error"]
        if "render" in skipped:
            assert "postgresql_ddl" not in result["result"]
    else:
        assert result["status"] == "completed_with_warnings"
        assert all(c["status"] == "passed" for c in result["checks"])
        assert len(result["model_calls"]) == 2
        assert [e["name"] for e in events if e["event"] == "stage_start"] == [
            "generate",
            "validate",
            "render",
            "review",
        ]
        if fault == "semantic-omission":
            assert any(f["kind"] == "omission" for f in result["result"]["review"]["findings"])
    assert result["database_execution"] == "not_run"


def test_debug_report_escapes_html_and_redacts_known_secrets(tmp_path):
    expected = json.loads((SCENARIO / "expected.json").read_text())
    source = json.loads((SCENARIO / "request.json").read_text())["text"]
    result = asyncio.run(execute("reference", None, Settings(_env_file=None), expected, source, lambda _: None))
    report = redact(
        {
            "mode": "reference",
            "configuration": {},
            "source": '<script>alert("private-test-key")</script>',
            "expected": expected,
            **result,
        },
        ["private-test-key"],
    )
    path = tmp_path / "report.html"
    write_html(report, path)
    text = path.read_text()
    assert "private-test-key" not in text
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "[REDACTED]" in text
    assert "외부 모델 호출 시도 0회" in text
    assert "<details>" in text


def test_live_debugger_observes_real_model_boundary(model_api):
    # 기존 SDK HTTP MockTransport로 실제 호출 경로를 검증하고 외부 네트워크는 사용하지 않는다.
    expected = json.loads((SCENARIO / "expected.json").read_text())
    source = json.loads((SCENARIO / "request.json").read_text())["text"]
    model_api.generation, model_api.review = expected["design"], expected["review"]
    result = asyncio.run(
        execute(
            "live",
            None,
            Settings(_env_file=None, anthropic_api_key="offline-placeholder"),
            expected,
            source,
            lambda _: None,
        )
    )
    assert len(model_api.requests) == 2
    assert result["external_model_calls"] == 2
    assert result["status"] == "completed_with_warnings"
    assert all(call["kind"] == "anthropic_api" for call in result["model_calls"])
    assert all(call["usage"]["output_tokens"] > 0 for call in result["model_calls"])


def test_live_missing_key_is_not_counted_as_external_call():
    expected = json.loads((SCENARIO / "expected.json").read_text())
    source = json.loads((SCENARIO / "request.json").read_text())["text"]
    result = asyncio.run(
        execute("live", None, Settings(_env_file=None, anthropic_api_key=""), expected, source, lambda _: None)
    )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "model_not_configured"
    assert result["external_model_calls"] == 0
