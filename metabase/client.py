"""Small Metabase 0.63.2 API compatibility boundary."""

from __future__ import annotations

from typing import Any

import httpx


class MetabaseAPIError(RuntimeError):
    pass


class MetabaseClient:
    def __init__(self, base_url: str, *, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def request(self, method: str, path: str, *, json: Any = None) -> Any:
        try:
            response = self._client.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise MetabaseAPIError(f"{method} {path} failed: {exc}") from exc
        if not response.is_success:
            body = response.text[:1000].replace("\n", " ")
            raise MetabaseAPIError(f"{method} {path} returned HTTP {response.status_code}: {body}")
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise MetabaseAPIError(f"{method} {path} returned non-JSON content") from exc

    def ready(self) -> bool:
        try:
            body = self.request("GET", "/api/health")
            return isinstance(body, dict) and body.get("status") == "ok"
        except MetabaseAPIError:
            return False

    def setup_properties(self) -> dict:
        return self.request("GET", "/api/session/properties")

    def initial_setup(self, payload: dict) -> dict:
        return self.request("POST", "/api/setup", json=payload)

    def login(self, email: str, password: str) -> None:
        body = self.request("POST", "/api/session", json={"username": email, "password": password})
        token = body.get("id") if isinstance(body, dict) else None
        if not token:
            raise MetabaseAPIError("Metabase login response did not contain a session id")
        self._client.headers["X-Metabase-Session"] = token

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, payload: dict) -> Any:
        return self.request("POST", path, json=payload)

    def put(self, path: str, payload: dict) -> Any:
        return self.request("PUT", path, json=payload)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)
