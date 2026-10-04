"""Persona picker and demo login. No passwords: the signed token is the identity."""

from fastapi import APIRouter, HTTPException

from agent.api.deps import CurrentPrincipal, RuntimeDep
from agent.api.schemas import LoginRequest, LoginResponse, PrincipalOut
from agent.auth import persona, personas
from agent.domain.errors import PersonNotFoundError

router = APIRouter(tags=["auth"])


@router.get("/personas")
def list_personas(runtime: RuntimeDep) -> list[PrincipalOut]:
    return [PrincipalOut.of(p) for p in personas(runtime.store.participants())]


@router.post("/auth/login")
def login(request: LoginRequest, runtime: RuntimeDep) -> LoginResponse:
    try:
        principal = persona(request.persona_id, runtime.store.participants())
    except PersonNotFoundError as exc:
        raise HTTPException(
            404, f"We couldn't find a profile called {request.persona_id!r}."
        ) from exc
    return LoginResponse(
        token=runtime.signer.issue(principal),
        expires_in=int(runtime.settings.token_ttl_hours * 3600),
        principal=PrincipalOut.of(principal),
    )


@router.get("/me")
def me(principal: CurrentPrincipal) -> PrincipalOut:
    return PrincipalOut.of(principal)
