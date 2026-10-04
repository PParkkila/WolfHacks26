from datetime import UTC, datetime, timedelta

import jwt
import pytest
from support import PID

from agent.auth import (
    CLINICIAN,
    InvalidTokenError,
    TokenSigner,
    patient,
    persona,
    personas,
)
from agent.domain.errors import PersonNotFoundError

IDS = [PID, "demo:imu50:00"]
SECRET = "test-secret-that-is-at-least-32-bytes"
OTHER_SECRET = "another-secret-that-is-at-least-32-b"


def test_personas_are_the_clinician_plus_every_participant():
    found = personas(IDS)
    assert [p.user_id for p in found] == [
        "clinician:demo",
        f"patient:{PID}",
        "patient:demo:imu50:00",
    ]
    assert found[2].display_name == "Patient IMU-00"


def test_login_only_for_known_personas():
    assert persona("clinician:demo", IDS) == CLINICIAN
    assert persona(f"patient:{PID}", IDS).participant_id == PID
    with pytest.raises(PersonNotFoundError):
        persona("patient:demo:big_ideas:099", IDS)
    with pytest.raises(PersonNotFoundError):
        persona("admin", IDS)


def test_tokens_round_trip_per_role():
    signer = TokenSigner(SECRET)
    assert signer.verify(signer.issue(CLINICIAN)) == CLINICIAN
    assert signer.verify(signer.issue(patient(PID))) == patient(PID)


def test_tampered_foreign_and_expired_tokens_are_rejected():
    signer = TokenSigner(SECRET)
    token = signer.issue(patient(PID))
    with pytest.raises(InvalidTokenError):
        signer.verify(token[:-2] + ("AA" if token[-2:] != "AA" else "BB"))
    with pytest.raises(InvalidTokenError):
        TokenSigner(OTHER_SECRET).verify(token)
    forged = jwt.encode(
        {
            "sub": "x",
            "role": "clinician",
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        OTHER_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        signer.verify(forged)
    old = TokenSigner(
        SECRET, ttl=timedelta(hours=1), now=lambda: datetime(2020, 1, 1, tzinfo=UTC)
    )
    with pytest.raises(InvalidTokenError):
        signer.verify(old.issue(CLINICIAN))


def test_patient_token_without_participant_is_rejected():
    token = jwt.encode(
        {"sub": "p", "role": "patient", "exp": datetime.now(UTC) + timedelta(hours=1)},
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        TokenSigner(SECRET).verify(token)
