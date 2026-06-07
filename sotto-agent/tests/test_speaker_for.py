"""Tests for mapping a (unique) participant identity to its consult role."""

from __future__ import annotations

import pytest

from sotto_agent import speaker_for


@pytest.mark.parametrize(
    "identity,expected",
    [
        ("doctor", "doctor"),
        ("patient", "patient"),
        ("doctor-a1b2c3", "doctor"),
        ("patient-zz99", "patient"),
        ("doctor-", "doctor"),
        ("observer", None),
        ("doctorish", None),  # must not match a non-hyphen prefix
        ("", None),
        ("voice_assistant_user_123", None),
    ],
)
def test_speaker_for(identity, expected):
    assert speaker_for(identity) == expected
