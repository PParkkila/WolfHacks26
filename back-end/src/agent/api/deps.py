"""Request dependencies: the runtime, who is calling, and shared error handling."""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agent.auth import InvalidTokenError, Principal
from agent.bootstrap import Runtime
from agent.domain.errors import (
    AmbiguousPersonError,
    ForbiddenError,
    PersonNotFoundError,
    QueryError,
)
from agent.query import QueryService

_bearer = HTTPBearer(auto_error=False)


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def current_principal(runtime: RuntimeDep, credentials: Credentials) -> Principal:
    if credentials is None:
        raise HTTPException(
            401,
            "Please choose a profile to continue.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return runtime.signer.verify(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(
            401,
            "Your session has ended. Please choose a profile again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def query_service(runtime: RuntimeDep, principal: CurrentPrincipal) -> QueryService:
    return runtime.queries(principal)


Queries = Annotated[QueryService, Depends(query_service)]


def install_error_handlers(app: FastAPI) -> None:
    """Domain errors become JSON with a stable `code` the UI can switch on."""

    def body(status: int, code: str, message: str, **extra: object) -> JSONResponse:
        return JSONResponse({"detail": message, "code": code, **extra}, status)

    @app.exception_handler(PersonNotFoundError)
    async def not_found(_: Request, exc: PersonNotFoundError) -> JSONResponse:
        return body(
            404,
            "not_found",
            f"We couldn't find a patient matching {exc.ref!r}.",
            suggestions=exc.suggestions,
        )

    @app.exception_handler(AmbiguousPersonError)
    async def ambiguous(_: Request, exc: AmbiguousPersonError) -> JSONResponse:
        return body(
            409,
            "ambiguous",
            f"{exc.ref!r} matches more than one patient.",
            candidates=exc.candidates,
        )

    @app.exception_handler(ForbiddenError)
    async def forbidden(_: Request, exc: ForbiddenError) -> JSONResponse:
        return body(403, "not_permitted", str(exc))

    @app.exception_handler(QueryError)
    async def bad_query(_: Request, exc: QueryError) -> JSONResponse:
        return body(400, "bad_query", str(exc), **exc.details)
