"""대표 합성 시나리오. 폴더 하나가 시나리오 하나(request.json·expected.json)이며 폴더 이름순으로 정렬한다."""

import json
from pathlib import Path

ROOT = Path(__file__).parent


def names() -> list[str]:
    return sorted(p.name for p in ROOT.iterdir() if (p / "request.json").is_file())


def load(name: str) -> tuple[str, dict]:
    """원문 text와 사람이 작성한 기준 결과(expected.json)를 반환한다."""
    folder = ROOT / name
    request = json.loads((folder / "request.json").read_text(encoding="utf-8"))
    return request["text"], json.loads((folder / "expected.json").read_text(encoding="utf-8"))
