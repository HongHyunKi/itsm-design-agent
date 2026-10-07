from collections import Counter

from app.schemas.design import Design


def validate_design(design: Design, source: str) -> list[str]:
    """결정적 구조 검사. 오류에 원문이나 자유 텍스트를 포함하지 않는다."""
    errors = []

    def unique(values, label):
        if any(n > 1 for n in Counter(values).values()):
            errors.append(f"{label}: 중복 식별자")

    requirements = {r.id: r for r in design.requirements}
    functions = {f.id for f in design.functions}
    tables = {t.name: t for t in design.data_model.tables}
    unique([r.id for r in design.requirements], "requirements")
    unique([f.id for f in design.functions], "functions")
    unique([t.name for t in design.data_model.tables], "tables")
    for i, req in enumerate(design.requirements):
        if req.provenance == "source" and not req.evidence:
            errors.append(f"requirements[{i}]: 원문 근거 필요")
        if any(quote not in source for quote in req.evidence):
            errors.append(f"requirements[{i}]: 원문 인용 불일치")
        if req.provenance == "proposal" and (not req.assumption.strip() or not req.needs_confirmation):
            errors.append(f"requirements[{i}]: 제안 사유와 확인 필요 표시 필수")
    for i, table in enumerate(design.data_model.tables):
        unique([c.name for c in table.columns], f"tables[{i}].columns")
        if sum(c.primary_key for c in table.columns) != 1:
            errors.append(f"tables[{i}]: 단일 PK 필요")
        for j, col in enumerate(table.columns):
            label = f"tables[{i}].columns[{j}]"
            if col.primary_key and col.nullable:
                errors.append(f"{label}: PK는 NULL 불가")
            if col.references:
                target = tables.get(col.references.table)
                ref = next((c for c in target.columns if c.name == col.references.column), None) if target else None
                if ref is None:
                    errors.append(f"{label}: FK 대상 없음")
                elif not (ref.primary_key or ref.unique) or ref.type != col.type:
                    errors.append(f"{label}: FK 대상은 같은 타입의 PK/UNIQUE여야 함")
    unique([t.requirement_id for t in design.traceability], "traceability")
    seen_requirements, seen_functions, seen_tables = set(), set(), set()
    for i, trace in enumerate(design.traceability):
        req = requirements.get(trace.requirement_id)
        seen_requirements.add(trace.requirement_id)
        seen_functions.update(trace.function_ids)
        seen_tables.update(trace.tables)
        unique(trace.function_ids, f"traceability[{i}].function_ids")
        unique(trace.tables, f"traceability[{i}].tables")
        if req is None or not set(trace.function_ids) <= functions or not set(trace.tables) <= tables.keys():
            errors.append(f"traceability[{i}]: 존재하지 않는 참조")
        if req and req.needs_storage and not trace.tables:
            errors.append(f"traceability[{i}]: 저장 필요 요구사항의 테이블 연결 누락")
        if not trace.tables and not trace.no_storage_reason.strip():
            errors.append(f"traceability[{i}]: 저장 불필요 사유 필요")
    if requirements.keys() - seen_requirements:
        errors.append("traceability: 요구사항 추적 누락")
    if functions - seen_functions:
        errors.append("traceability: 기능 추적 누락")
    if tables.keys() - seen_tables:
        errors.append("traceability: 테이블 추적 누락")
    return errors


def render_model(design: Design) -> tuple[str, str]:
    """호출자는 먼저 validate_design 통과를 확인한다. SQL은 실행하지 않는다."""
    erd, ddl, foreign_keys = ["erDiagram"], [], []
    for table in design.data_model.tables:
        erd.append(f"    {table.name} {{")
        columns = []
        for col in table.columns:
            keys = [
                key for enabled, key in [(col.primary_key, "PK"), (col.references, "FK"), (col.unique, "UK")] if enabled
            ]
            erd.append(f"        {col.type} {col.name}" + (" " + ", ".join(keys) if keys else ""))
            sql = f'    "{col.name}" {col.type.upper()}'
            if not col.nullable:
                sql += " NOT NULL"
            if col.primary_key:
                sql += " PRIMARY KEY"
            elif col.unique:
                sql += " UNIQUE"
            columns.append(sql)
            if ref := col.references:
                foreign_keys.append(
                    f'ALTER TABLE "{table.name}" ADD FOREIGN KEY ("{col.name}") '
                    f'REFERENCES "{ref.table}" ("{ref.column}");'
                )
        erd.append("    }")
        ddl.append(f'CREATE TABLE "{table.name}" (\n' + ",\n".join(columns) + "\n);")
    for table in design.data_model.tables:
        for col in table.columns:
            if ref := col.references:
                parent = "|o" if col.nullable else "||"
                child = "o|" if col.primary_key or col.unique else "o{"
                relationship = "--" if col.primary_key else ".."
                erd.append(f'    {ref.table} {parent}{relationship}{child} {table.name} : "{col.name}"')
    return "\n".join(erd), "\n\n".join(["-- 미검증 초안: DB 실행 검증 미실시", *ddl, *foreign_keys])
