"""설계 그래프 단계별 오류 응답을 만드는 공통 경계."""

import functools
import inspect

from app.core.exceptions import AppError
from app.services.design_pipeline.state import Failure


def failure(code: str, message: str, stage: str, status: int = 502, **detail) -> AppError:
    return AppError(message, {"stage": stage, **detail}, status_code=status, code=code)


def guarded(node):
    """노드가 던진 AppError를 상태의 failure로 바꾼다. 실패도 그래프 상태로 남아 다음 단계가 이를 보고 멈춘다."""

    @functools.wraps(node)
    async def wrapper(state, runtime):
        try:
            result = node(state, runtime)
            return await result if inspect.isawaitable(result) else result
        except AppError as exc:
            return {"failure": Failure(code=exc.code, message=exc.message, status=exc.status_code, detail=exc.detail)}

    return wrapper


def as_error(failed: Failure) -> AppError:
    return AppError(failed["message"], failed["detail"], status_code=failed["status"], code=failed["code"])
