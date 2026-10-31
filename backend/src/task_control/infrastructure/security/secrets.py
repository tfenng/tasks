from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from task_control.config import get_settings


class SecretError(ValueError):
    pass


@dataclass(frozen=True)
class SecretBox:
    key_ring: dict[int, bytes]
    active_version: int

    def encrypt(self, plaintext: str, *, aad: str) -> dict[str, object]:
        key = self.key_ring[self.active_version]
        nonce = os.urandom(12)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), aad.encode("utf-8"))
        return {
            "__enc__": base64.b64encode(nonce + ciphertext).decode("ascii"),
            "key_version": self.active_version,
        }

    def decrypt(self, payload: dict[str, object], *, aad: str) -> str:
        version = int(payload.get("key_version", 0))
        encoded = payload.get("__enc__")
        if version not in self.key_ring or not isinstance(encoded, str):
            raise SecretError("invalid encrypted payload")
        raw = base64.b64decode(encoded)
        plaintext = AESGCM(self.key_ring[version]).decrypt(raw[:12], raw[12:], aad.encode("utf-8"))
        return plaintext.decode("utf-8")


@lru_cache
def get_secret_box() -> SecretBox:
    settings = get_settings()
    return SecretBox(settings.secret_key_ring, settings.secret_active_version)


def _is_secret(definition: object) -> bool:
    return isinstance(definition, dict) and bool(
        definition.get("x-secret") or definition.get("writeOnly")
    )


def encrypt_parameters(
    schema: dict, parameters: dict, *, run_id: str, box: SecretBox | None = None
) -> dict:
    box = box or get_secret_box()
    result = json.loads(json.dumps(parameters))
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return result
    for name, definition in properties.items():
        if name in result and _is_secret(definition):
            result[name] = box.encrypt(
                json.dumps(result[name], ensure_ascii=False),
                aad=f"run:{run_id}:param:{name}",
            )
    return result


def decrypt_parameters(schema: dict, parameters: dict, *, run_id: str) -> dict:
    box = get_secret_box()
    result = json.loads(json.dumps(parameters))
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return result
    for name, _definition in properties.items():
        payload = result.get(name)
        if isinstance(payload, dict) and "__enc__" in payload:
            result[name] = json.loads(box.decrypt(payload, aad=f"run:{run_id}:param:{name}"))
    return result
