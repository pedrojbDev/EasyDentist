from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import ConflictError, DomainError, NotFoundError

PROBLEM_CONTENT_TYPE = "application/problem+json"

TITLES: dict[int, str] = {
    400: "Requisição inválida",
    401: "Não autenticado",
    403: "Acesso negado",
    404: "Recurso não encontrado",
    405: "Método não permitido",
    409: "Conflito",
    422: "Dados inválidos",
    429: "Muitas tentativas",
    500: "Erro interno",
}


def request_id_from(request: Request) -> str:
    return str(getattr(request.state, "request_id", ""))


def problem_response(
    *,
    status: int,
    request_id: str = "",
    title: str | None = None,
    detail: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, str | int] = {
        "type": "about:blank",
        "title": title if title is not None else TITLES.get(status, "Erro"),
        "status": status,
        "request_id": request_id,
    }
    if detail is not None:
        body["detail"] = detail
    return JSONResponse(
        status_code=status,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=dict(headers) if headers is not None else None,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    http_error = cast(StarletteHTTPException, exc)
    return problem_response(
        status=http_error.status_code,
        request_id=request_id_from(request),
        headers=http_error.headers,
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return problem_response(status=422, request_id=request_id_from(request))


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, NotFoundError):
        status = 404
    elif isinstance(exc, ConflictError):
        status = 409
    else:
        status = 500
    return problem_response(status=status, request_id=request_id_from(request))


def register_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(DomainError, domain_error_handler)
