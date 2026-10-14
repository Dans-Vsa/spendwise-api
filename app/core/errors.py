"""One error format for every failure the API returns.

Every error response looks like::

    {"error": {"status": 404, "code": "not_found", "message": "Transaction not found",
               "fields": []}}

`fields` lists per-field problems for validation errors (location + message), so clients
can show them next to the right input.
"""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("spendwise.errors")

# Status codes that get a friendlier code than the generic HTTP phrase.
_CODES = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_413_CONTENT_TOO_LARGE: "payload_too_large",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_error",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_error",
}


class FieldError(BaseModel):
    location: str
    message: str


class ErrorBody(BaseModel):
    status: int
    code: str
    message: str
    fields: list[FieldError] = []


class ErrorResponse(BaseModel):
    """Schema of every error response (documented in OpenAPI)."""

    error: ErrorBody


def error_code(status_code: int) -> str:
    if status_code in _CODES:
        return _CODES[status_code]
    try:
        return HTTPStatus(status_code).phrase.lower().replace(" ", "_").replace("-", "_")
    except ValueError:
        return "error"


def error_response(
    status_code: int,
    message: str,
    fields: list[FieldError] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            status=status_code,
            code=error_code(status_code),
            message=message,
            fields=fields or [],
        )
    )
    return JSONResponse(body.model_dump(), status_code=status_code, headers=headers)


def _location(loc: tuple) -> str:
    # ("body", "items", 0, "amount") -> "body.items[0].amount"
    text = ""
    for part in loc:
        text += f"[{part}]" if isinstance(part, int) else (f".{part}" if text else str(part))
    return text


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, str):
        return error_response(exc.status_code, detail, headers=exc.headers)
    if isinstance(detail, dict):
        # Structured details, e.g. {"message": ..., "fields": [...]} from the CSV import.
        fields = [FieldError(**item) for item in detail.get("fields", [])]
        return error_response(exc.status_code, detail.get("message", ""), fields, exc.headers)
    return error_response(exc.status_code, str(detail), headers=exc.headers)


async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    fields = [
        FieldError(location=_location(tuple(err.get("loc", ()))), message=err.get("msg", ""))
        for err in jsonable_encoder(exc.errors())
    ]
    return error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "Request validation failed", fields
    )


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", exc_info=exc)
    return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
