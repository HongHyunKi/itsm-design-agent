"""로컬 합성 시나리오 디버거: 저장소 루트에서 ./debug-design --mode reference."""

import argparse
import asyncio
import html
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from pydantic import BaseModel, ValidationError

import scenarios
from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.logging import setup_logging
from app.schemas.design import ModelCall
from app.services import design as service
from app.services.design_model import render_model, validate_design

BACKEND = Path(__file__).resolve().parents[1]
STAGES = {
    "generate": ("설계 생성", "Anthropic 모델 호출", "원문에서 요구사항·근거·기능·모델·추적·가정·질문을 생성"),
    "validate": (
        "구조 검증",
        "Python · Pydantic / validate_design",
        "스키마·중복 ID·인용·PK/FK·추적을 검사. 오류 시 후속 단계 생략",
    ),
    "render": ("ERD·DDL 변환", "Python · render_model", "같은 검증 모델에서 두 문자열 생성. DB 실행은 하지 않음"),
    "review": (
        "의미 검토",
        "Anthropic 모델 호출",
        "원문과 설계를 대조하고 누락·모순·확인 후보를 반환. 자동 수정하지 않음",
    ),
}
FAULTS = (
    "bad-reference",
    "missing-trace",
    "invalid-json",
    "truncated",
    "api-error",
    "review-reference",
    "semantic-omission",
)


def serializable(value):
    return json.loads(
        json.dumps(
            value,
            ensure_ascii=False,
            default=lambda obj: obj.model_dump(mode="json") if isinstance(obj, BaseModel) else None,
        )
    )


def redact(value, secrets):
    """설정은 저장하지 않으며, 알려진 키가 출력 문자열에 섞인 경우도 제거한다."""
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, dict):
        return {redact(k, secrets): redact(v, secrets) for k, v in value.items()}
    return value


def inject_fault(expected, fault):
    """시나리오 구조에 의존하지 않는 위치에 주입한다. 의미 누락은 시나리오의 semantic_omission 정의를 따른다."""
    design = expected["design"]
    if fault == "bad-reference":
        columns = (c for t in design["data_model"]["tables"] for c in t["columns"])
        next(c for c in columns if c["references"])["references"]["table"] = "missing_table"
    elif fault == "missing-trace":
        design["traceability"].pop()
    elif fault == "review-reference":
        expected["review"]["findings"][0]["related_ids"] = ["C-REQ-999"]
    elif fault == "semantic-omission":
        # 구조는 유효하지만 업무 의미가 빠진 사례: 지정 컬럼과 기능 입력을 제거한다.
        spec = expected["semantic_omission"]
        table = next(t for t in design["data_model"]["tables"] if t["name"] == spec["table"])
        table["columns"] = [c for c in table["columns"] if c["name"] != spec["column"]]
        next(f for f in design["functions"] if f["id"] == spec["function"])["inputs"].remove(spec["input"])
        expected["review"]["summary"] = "구조 검사는 통과했지만 저장 누락 후보가 있습니다. 오류 주입용 기준 검토입니다."
        expected["review"]["findings"].append(spec["finding"])


def contract_checks(state, calls, mode):
    design = state.get("design")
    if design is None or state.get("errors"):
        return [{"check": "생성 스키마·구조 검사", "status": "failed"}]
    checks = [
        ("검토 결과 스키마·참조·인용 검사", "review" in state),
        ("생성 스키마·구조 검사", not validate_design(design, state["source"])),
        (
            "동일 모델에서 ERD·DDL 생성",
            "postgresql_ddl" in state and render_model(design) == (state["mermaid_erd"], state["postgresql_ddl"]),
        ),
        ("FK로 연결한 데이터 모델 존재", any(c.references for t in design.data_model.tables for c in t.columns)),
        (
            "저장 불필요 요구사항의 사유와 빈 테이블 연결",
            all(
                r.needs_storage
                or any(
                    t.requirement_id == r.id and not t.tables and t.no_storage_reason.strip()
                    for t in design.traceability
                )
                for r in design.requirements
            ),
        ),
        (
            "생성·검토 호출 2회 완료" + (" (기준 응답 재생)" if mode == "reference" else " (실제 모델)"),
            len(calls) == 2 and all(c["status"] == "completed" for c in calls),
        ),
    ]
    return [{"check": label, "status": "passed" if passed else "failed"} for label, passed in checks]


async def execute(mode, fault, settings, expected, source, event_sink):
    fixture = json.loads(json.dumps(expected))
    inject_fault(fixture, fault)
    calls, stages, state = [], {}, {"source": source}
    original_call = service.call_model

    async def inspected_call(payload, stage, schema, context):
        started = time.monotonic()
        call = {
            "stage": stage,
            "kind": "reference_replay" if mode == "reference" else "anthropic_api",
            "status": "running",
            "schema": schema.__name__,
            "system_prompt": service.SYSTEM + (service.GENERATE if stage == "generate" else service.REVIEW),
            "input": json.loads(payload),
        }
        calls.append(call)
        event_sink({"event": "model_start", "stage": stage, "call": call})
        try:
            if mode == "live":
                raw, usage = await original_call(payload, stage, schema, context)
            else:
                if stage == "generate" and fault in ("truncated", "api-error"):
                    code = "model_output_truncated" if fault == "truncated" else "model_api_failed"
                    raise service.failure(
                        code, "오류 주입: 출력 한도 초과" if fault == "truncated" else "오류 주입: 외부 API 실패", stage
                    )
                raw = (
                    "{invalid-json"
                    if stage == "generate" and fault == "invalid-json"
                    else json.dumps(fixture["design" if stage == "generate" else "review"], ensure_ascii=False)
                )
                usage = ModelCall(
                    stage=stage,
                    model="reference-fixture",
                    duration_ms=0,
                    input_tokens=0,
                    output_tokens=0,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=0,
                )
            call.update(status="completed", output=raw, usage=usage.model_dump())
            return raw, usage
        except AppError as exc:
            call.update(status="failed", error={"code": exc.code, "message": exc.message, "detail": exc.detail})
            raise
        finally:
            call["duration_ms"] = round((time.monotonic() - started) * 1000)
            if call["status"] == "running":
                call.update(status="failed", error={"code": "unexpected_error"})
            event_sink({"event": "model_end", "stage": stage, "call": call})

    error = None
    # CLI 전용 프로세스에서 모델 경계만 관찰한다. 서비스 그래프·노드·분기 자체는 그대로 사용한다.
    with patch.object(service, "call_model", inspected_call):
        try:
            async for event in service.graph.astream(
                state, context={"settings": settings, "tracer": None}, stream_mode="debug"
            ):
                payload = event["payload"]
                name = payload.get("name")
                if name not in STAGES:
                    continue
                if event["type"] == "task":
                    stages[name] = {
                        "name": name,
                        "status": "running",
                        "started_at": event["timestamp"],
                        "input": serializable(payload["input"]),
                    }
                    event_sink({"event": "stage_start", **stages[name]})
                    print(f"→ {name}: {STAGES[name][0]}", flush=True)
                elif event["type"] == "task_result":
                    stage = stages[name]
                    output = payload["result"]
                    state.update(output)
                    stage.update(
                        status="failed" if payload.get("error") or output.get("errors") else "completed",
                        output=serializable(output),
                        ended_at=event["timestamp"],
                    )
                    stage["duration_ms"] = round(
                        (
                            datetime.fromisoformat(stage["ended_at"]) - datetime.fromisoformat(stage["started_at"])
                        ).total_seconds()
                        * 1000
                    )
                    event_sink({"event": "stage_end", **stage})
                    print(f"  {stage['status']} · {stage['duration_ms']} ms", flush=True)
            if state.get("errors"):
                error = {"code": "structure_invalid", "stage": "validate", "issues": state["errors"]}
        except AppError as exc:
            error = {"code": exc.code, "message": exc.message, "detail": exc.detail}
        except Exception:
            error = {
                "code": "unexpected_error",
                "message": "예기치 않은 실행 오류. 민감정보 보호를 위해 예외 본문은 기록하지 않습니다.",
            }
    for name in STAGES:
        if name not in stages:
            stages[name] = {"name": name, "status": "skipped", "reason": "선행 단계 실패로 실행하지 않음"}
        elif stages[name]["status"] == "running":
            stages[name].update(status="failed", error=error)
    if error:
        event_sink({"event": "run_failed", "error": error})
    return {
        "status": "failed" if error else "completed_with_warnings",
        "error": error,
        "stages": list(stages.values()),
        "model_calls": calls,
        "external_model_calls": sum(c.get("error", {}).get("code") != "model_not_configured" for c in calls)
        if mode == "live"
        else 0,
        "checks": contract_checks(state, calls, mode),
        "result": serializable({k: v for k, v in state.items() if k != "raw"}),
        "database_execution": "not_run",
        "semantic_quality": "human_review_required",
    }


def write_html(report, path):
    def block(value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        return "<pre>" + html.escape(text) + "</pre>"

    rows = "".join(f"<tr><td>{html.escape(c['check'])}</td><td>{c['status']}</td></tr>" for c in report["checks"])
    steps = ""
    for stage in report["stages"]:
        name = stage["name"]
        title, kind, rule = STAGES[name]
        call = next((c for c in report["model_calls"] if c["stage"] == name), None)
        steps += f"<details><summary>{name} · {title} — {stage['status']} · {stage.get('duration_ms', '—')} ms</summary><p>{kind} / {rule}</p>"
        for label, value in [
            ("단계 입력 상태", stage.get("input")),
            ("단계 출력 / 검사 결과", stage.get("output", stage.get("error", stage.get("reason")))),
        ]:
            steps += f"<details><summary>{label}</summary>{block(value)}</details>"
        if name == "render" and stage.get("output"):
            steps += "<h3>Mermaid ERD</h3>" + block(stage["output"].get("mermaid_erd"))
            steps += "<h3>PostgreSQL DDL · 실행 미검증</h3>" + block(stage["output"].get("postgresql_ddl"))
        if call:
            steps += "<h3>모델 호출 상태·사용량</h3>" + block(
                {k: v for k, v in call.items() if k not in ("system_prompt", "input", "output")}
            )
            for label, key in [
                ("모델에 보낸 시스템 지시", "system_prompt"),
                ("모델에 보낸 데이터", "input"),
                ("모델이 반환한 응답", "output"),
            ]:
                steps += f"<details><summary>{label}</summary>{block(call.get(key))}</details>"
        steps += "</details>"
    findings = report["result"].get("review", {}).get("findings", [])
    finding_rows = "".join(
        "<tr>"
        + "".join(
            "<td>" + html.escape(str(f.get(key, ""))) + "</td>"
            for key in ("kind", "description", "evidence", "suggestion")
        )
        + "</tr>"
        for f in findings
    )
    manual = "".join("<li>" + html.escape(item) + "</li>" for item in report["expected"]["manual_checks"])
    document = f"""<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ITSM 단계별 디버깅</title><style>
body{{font:15px/1.6 system-ui,sans-serif;color:#182432;background:#f4f6f8;margin:0;padding:32px;max-width:1400px;margin-inline:auto}}
h1{{margin-bottom:8px}} .badge{{display:inline-block;background:#163b51;color:white;padding:5px 12px;border-radius:4px}}
section,details{{background:white;border:1px solid #d4dce2;padding:18px;margin:16px 0;border-radius:6px}}
summary{{font-weight:700;cursor:pointer}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7f9;padding:16px;font:13px/1.6 ui-monospace,monospace;max-height:640px;overflow:auto}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}th,td{{text-align:left;padding:8px 16px;border-bottom:1px solid #d4dce2}}table{{width:100%;border-collapse:collapse}}
@media(max-width:800px){{body{{padding:16px}}.grid{{grid-template-columns:1fr}}}}
</style><h1>ITSM · 단계별 디버깅</h1><span class="badge">{report["mode"]} / {report["status"]}</span>
<p>실제 외부 모델 호출 시도 {report["external_model_calls"]}회 · LLM 도구 선택 호출 없음 · DB 실행 미검증</p>
<p>reference는 사람이 작성한 응답 재생이며 실제 모델 성능이 아닙니다. 판단은 코드 검사와 모델의 공개 근거·가정·검토 결과입니다.</p>
<section><h2>실행 조건</h2>{block(report["configuration"])}<h2>원문</h2>{block(report["source"])}{block(report["error"]) if report["error"] else ""}</section>
<section><h2>실행·구조 계약 검사</h2><table>{rows}</table><p>passed는 해당 구조 조건의 통과이며 업무 정확도 점수가 아닙니다.</p></section>
<h2>실행 순서 — 펼쳐서 확인</h2>{steps}
<section><h2>의미 검토 판단 후보</h2><table><tr><th>종류</th><th>설명</th><th>원문 근거</th><th>제안</th></tr>{finding_rows}</table><p>검토 미실행 또는 후보 없음이면 표가 비어 있습니다. 단계 상태를 함께 확인하세요.</p></section>
<h2>기준 출력 ↔ 이번 실행</h2><p>기준은 설계 제안입니다. 이름·개수의 완전 일치 대신 아래 업무 조건을 검토하세요.</p>
<section><h3>사람이 확인할 조건</h3><ol>{manual}</ol></section>
<div class="grid"><section><h3>사람이 작성한 기준 설계·검토</h3>{block(report["expected"])}</section><section><h3>이번 실행 결과 (실패 시 중간 결과)</h3>{block(report["result"])}</section></div>
<p>원본 파일: <a href="report.json">report.json</a> · <a href="events.jsonl">events.jsonl</a>. 변환 완료 시 draft-model.mmd / draft-schema.sql도 저장합니다.</p></html>"""
    path.write_text(document, encoding="utf-8")


def pick_scenarios(value):
    """all, 폴더 이름, 번호(2·02) 중 하나로 실행할 시나리오를 고른다."""
    names = scenarios.names()
    if value == "all":
        return names
    found = [n for n in names if value == n or value.isdigit() and int(n.split("-", 1)[0]) == int(value)]
    if not found:
        raise argparse.ArgumentTypeError(f"all, 번호 또는 {', '.join(names)} 중 하나")
    return found


def run_scenario(name, args, settings, default_limit, secrets):
    source, expected = scenarios.load(name)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    directory = BACKEND / ".debug-runs" / run_id
    directory.mkdir(parents=True, mode=0o700)
    with (directory / "events.jsonl").open("w", encoding="utf-8") as file:

        def sink(event):
            file.write(json.dumps(redact(serializable(event), secrets), ensure_ascii=False) + "\n")
            file.flush()

        print(f"[{name}]", flush=True)
        result = asyncio.run(execute(args.mode, args.fault, settings, expected, source, sink))
    report = redact(
        {
            "mode": args.mode,
            "scenario": name,
            "run_id": run_id,
            "source": source,
            "expected": expected,
            "configuration": {
                "model": settings.anthropic_model,
                "max_tokens": settings.anthropic_max_tokens,
                "env_max_tokens": default_limit,
                "timeout_seconds": settings.anthropic_timeout_seconds,
                "prompt_caching_enabled": settings.enable_prompt_caching,
                "scenario": name,
                "fault": args.fault,
                "tracing": "local_only",
                "graph": "app.services.design.graph",
            },
            **result,
        },
        secrets,
    )
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_html(report, directory / "report.html")
    for key, filename in [("mermaid_erd", "draft-model.mmd"), ("postgresql_ddl", "draft-schema.sql")]:
        if key in report["result"]:
            (directory / filename).write_text(report["result"][key], encoding="utf-8")
    print(f"{report['status']} · {name} · {args.mode} · 외부 모델 호출 {report['external_model_calls']}회")
    print(f"보고서: {directory / 'report.html'}")
    return report["status"] != "failed"


def main():
    parser = argparse.ArgumentParser(
        prog="./debug-design", description="ITSM 대표 합성 시나리오의 실제 그래프 단계별 디버깅"
    )
    choices = "{all,번호," + ",".join(scenarios.names()) + "}"
    help_text = "기본값은 첫 시나리오. all은 시나리오마다 별도 보고서를 만든다."
    parser.add_argument("scenario", nargs="?", type=pick_scenarios, metavar=choices, help=help_text)
    parser.add_argument(
        "--scenario", dest="scenario_option", type=pick_scenarios, metavar=choices, help="위치 인자와 같음"
    )
    parser.add_argument("--mode", choices=("reference", "live"), default="reference")
    parser.add_argument("--fault", choices=FAULTS)
    parser.add_argument("--max-tokens", type=int, help="이번 실행 출력 한도만 변경 (.env 보존)")
    args = parser.parse_args()
    if args.scenario and args.scenario_option:
        parser.error("시나리오는 위치 인자 또는 --scenario 중 하나로만 지정합니다.")
    args.scenario = args.scenario or args.scenario_option or scenarios.names()[:1]
    if args.fault and args.mode != "reference":
        parser.error("--fault는 외부 호출 없는 reference 모드에서만 사용합니다.")
    if args.max_tokens is not None and not 1 <= args.max_tokens <= 64000:
        parser.error("--max-tokens는 1~64000입니다.")
    try:
        settings = Settings(_env_file=BACKEND / ".env")
    except ValidationError:
        parser.error("환경변수 형식이 잘못되었습니다. 값은 출력하지 않습니다. .env 설정을 확인하세요.")
    default_limit = settings.anthropic_max_tokens
    if args.max_tokens is not None:
        settings.anthropic_max_tokens = args.max_tokens
    setup_logging("WARNING")
    secrets = [
        settings.anthropic_api_key.get_secret_value(),
        settings.langfuse_secret_key.get_secret_value(),
        settings.secret_key.get_secret_value(),
    ]
    results = [run_scenario(name, args, settings, default_limit, secrets) for name in args.scenario]
    if len(results) > 1:
        print(f"시나리오 {len(results)}개 중 {sum(results)}개 완료")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
