from __future__ import annotations

import pytest

from task_control.domain.parameters import (
    ParameterValidationError,
    redact_parameters,
    validate_parameters,
    validate_schema,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "count": {"type": "integer", "minimum": 1, "default": 1},
        "token": {"type": "string", "x-secret": True, "writeOnly": True},
    },
    "required": ["name"],
    "additionalProperties": False,
}


def test_validate_parameters_accepts_valid_input():
    assert validate_parameters(SCHEMA, {"name": "alice", "count": 2})["name"] == "alice"


def test_validate_parameters_rejects_missing_required():
    with pytest.raises(ParameterValidationError) as exc:
        validate_parameters(SCHEMA, {"count": 2})
    assert exc.value.errors


def test_validate_schema_rejects_remote_ref():
    with pytest.raises(ParameterValidationError):
        validate_schema({"type": "object", "properties": {"x": {"$ref": "https://example.com"}}})


def test_redact_parameters_masks_secret_fields():
    assert redact_parameters(SCHEMA, {"name": "a", "token": "secret"})["token"] == "***"
