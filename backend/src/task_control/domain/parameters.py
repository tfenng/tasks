"""Parameter schema validation and normalization."""

from __future__ import annotations

import json
from copy import deepcopy

import jsonschema

MAX_PARAMETER_BYTES = 256 * 1024
MAX_DEPTH = 8

SUPPORTED_TYPES = {"string", "integer", "number", "boolean", "object", "array"}
SUPPORTED_FORMATS = {"date-time", "password", "secret"}


class ParameterValidationError(ValueError):
    def __init__(self, errors: list[dict]) -> None:
        super().__init__("invalid parameters")
        self.errors = errors


def _walk(schema: object, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise ParameterValidationError(
            [{"field": "$", "code": "max_depth", "message": "schema too deep"}]
        )
    if isinstance(schema, dict):
        if "$ref" in schema:
            ref = schema["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#"):
                raise ParameterValidationError(
                    [
                        {
                            "field": "$ref",
                            "code": "remote_ref",
                            "message": "remote $ref is not allowed",
                        }
                    ]
                )
        schema_type = schema.get("type")
        if schema_type is not None:
            types = schema_type if isinstance(schema_type, list) else [schema_type]
            for item in types:
                if item not in SUPPORTED_TYPES and item != "null":
                    raise ParameterValidationError(
                        [
                            {
                                "field": "type",
                                "code": "unsupported_type",
                                "message": f"unsupported type {item}",
                            }
                        ]
                    )
        schema_format = schema.get("format")
        if schema_format is not None and schema_format not in SUPPORTED_FORMATS:
            raise ParameterValidationError(
                [
                    {
                        "field": "format",
                        "code": "unsupported_format",
                        "message": f"unsupported format {schema_format}",
                    }
                ]
            )
        for value in schema.values():
            _walk(value, depth + 1)
    elif isinstance(schema, list):
        for item in schema:
            _walk(item, depth + 1)


def validate_schema(schema: dict) -> None:
    if not isinstance(schema, dict):
        raise ParameterValidationError(
            [{"field": "$", "code": "type", "message": "schema must be object"}]
        )
    _walk(schema)
    encoded = json.dumps(schema, ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_PARAMETER_BYTES:
        raise ParameterValidationError(
            [{"field": "$", "code": "too_large", "message": "schema too large"}]
        )
    jsonschema.Draft202012Validator.check_schema(schema)


def validate_parameters(schema: dict, parameters: dict) -> dict:
    validate_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(parameters), key=lambda item: list(item.path))
    if errors:
        raise ParameterValidationError(
            [
                {
                    "field": ".".join(str(part) for part in error.path) or "$",
                    "code": error.validator or "invalid",
                    "message": error.message,
                }
                for error in errors
            ]
        )
    return deepcopy(parameters)


def redact_parameters(schema: dict, parameters: dict) -> dict:
    redacted = deepcopy(parameters)
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return redacted
    for name, definition in properties.items():
        if (
            isinstance(definition, dict)
            and (definition.get("x-secret") or definition.get("writeOnly"))
            and name in redacted
        ):
            redacted[name] = "***"
    return redacted
