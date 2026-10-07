"""계층 규칙 강제 테스트. 각 파일의 최상위 import만 ast로 파싱해 검사합니다.

함수 안 import(예: factory의 live 어댑터 지연 import)는 검사 대상이 아닙니다.
"""

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _module_name(path: Path) -> str:
    parts = path.relative_to(APP_DIR.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _top_level_imports(path: Path) -> list[tuple[int, list[str]]]:
    """(줄 번호, 그 import 문이 가리키는 모듈 후보들) 목록."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = _module_name(path) if path.name == "__init__.py" else _module_name(path).rsplit(".", 1)[0]
    found = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            found += [(node.lineno, [alias.name]) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:  # 상대 import → 절대 경로로 변환
                pkg = package.split(".")[: len(package.split(".")) - (node.level - 1)]
                base = ".".join(pkg + ([base] if base else []))
            # `from app import models` 같은 경우도 잡도록 하위 이름까지 후보에 넣습니다.
            found.append((node.lineno, [base] + [f"{base}.{alias.name}" for alias in node.names]))
    return found


def _under(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


# (검사할 계층, 위반 판정 함수, 고치는 방법 한 줄)
RULES = [
    (
        "app.models",
        lambda m: _under(m, "app") and m != "app" and not _under(m, "app.models"),
        "models는 순수 ORM 정의만 둡니다. 필요한 로직은 services로 옮기세요.",
    ),
    (
        "app.api",
        lambda m: _under(m, "app.repositories") or _under(m, "app.models"),
        "라우터는 services만 호출하세요. DB 접근은 서비스 메서드로 감싸고 응답은 schemas로 받으세요.",
    ),
    (
        "app.services",
        lambda m: _under(m, "app.api"),
        "services는 HTTP 계층을 모릅니다. 필요한 값은 서비스 메서드 인자로 받으세요.",
    ),
    (
        "app.repositories",
        lambda m: _under(m, "app.services") or _under(m, "app.api"),
        "repositories는 조회와 저장만 합니다. 판단 로직은 services로 올리세요.",
    ),
    (
        "app.services",
        lambda m: (
            _under(m, "app.integrations")
            and m != "app.integrations"
            and not _under(m, "app.integrations.factory")
            and not _under(m, "app.integrations.ports")
        ),
        "어댑터를 직접 import하지 말고 integrations.factory의 get_*()로 받고, 타입은 integrations.ports의 Protocol을 쓰세요.",
    ),
]


def _files_in(layer: str) -> list[Path]:
    return sorted((APP_DIR.parent / layer.replace(".", "/")).rglob("*.py"))


@pytest.mark.parametrize("layer, violates, fix", RULES, ids=[f"{r[0]}#{i + 1}" for i, r in enumerate(RULES)])
def test_layer_rule(layer, violates, fix):
    files = _files_in(layer)
    assert files, f"{layer} 디렉터리에 파일이 없습니다"
    violations = [
        f"{path.relative_to(APP_DIR.parent)}:{lineno} import {next(m for m in mods if violates(m))}"
        for path in files
        for lineno, mods in _top_level_imports(path)
        if any(violates(m) for m in mods)
    ]
    assert not violations, "계층 규칙 위반:\n  " + "\n  ".join(violations) + f"\n→ 고치는 법: {fix}"
