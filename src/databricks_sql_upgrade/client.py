"""Minimal Databricks SQL Statements API client.

Uses only the Python standard library. Authentication is a bearer token from
DATABRICKS_TOKEN (a personal access token or a short-lived OAuth token).
"""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class SqlResult:
    ok: bool
    status: str
    error: str | None = None
    error_class: str | None = None


class DatabricksSqlClient:
    def __init__(
        self,
        host: str | None = None,
        token: str | None = None,
        warehouse_id: str | None = None,
    ) -> None:
        self.host = (host or os.environ.get("DATABRICKS_HOST", "")).rstrip("/")
        self.token = token or os.environ.get("DATABRICKS_TOKEN", "")
        self.warehouse_id = warehouse_id or os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
        if self.host and not self.host.startswith("http"):
            self.host = f"https://{self.host}"

    def configured(self) -> bool:
        return bool(self.host and self.token and self.warehouse_id)

    def execute(self, statement: str, wait_timeout: str = "50s") -> SqlResult:
        payload = {
            "statement": statement,
            "warehouse_id": self.warehouse_id,
            "wait_timeout": wait_timeout,
        }
        response = self._request("POST", "/api/2.0/sql/statements", payload)
        status = response.get("status", {})
        state = status.get("state", "UNKNOWN")
        if state == "SUCCEEDED":
            return SqlResult(ok=True, status=state)
        if state in {"PENDING", "RUNNING"}:
            statement_id = response.get("statement_id")
            return self._poll(statement_id)
        return self._result_from_status(status)

    def explain(self, sql: str) -> SqlResult:
        cleaned = sql.strip().rstrip(";")
        if not cleaned:
            return SqlResult(ok=True, status="SKIPPED_EMPTY")
        if cleaned.upper().startswith("EXPLAIN "):
            return self.execute(cleaned)
        return self.execute(f"EXPLAIN {cleaned}")

    def _poll(self, statement_id: str, attempts: int = 30, delay: float = 2.0) -> SqlResult:
        for _ in range(attempts):
            time.sleep(delay)
            response = self._request("GET", f"/api/2.0/sql/statements/{statement_id}")
            status = response.get("status", {})
            state = status.get("state", "UNKNOWN")
            if state in {"SUCCEEDED"}:
                return SqlResult(ok=True, status=state)
            if state in {"FAILED", "CANCELED", "CLOSED"}:
                return self._result_from_status(status)
        return SqlResult(ok=False, status="TIMEOUT", error="Statement polling timed out")

    def _result_from_status(self, status: dict) -> SqlResult:
        error = status.get("error") or {}
        message = error.get("message") or status.get("state", "FAILED")
        error_class = error.get("error_class")
        return SqlResult(ok=False, status=status.get("state", "FAILED"), error=message, error_class=error_class)

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self.host}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        context = _ssl_context()
        try:
            with urllib.request.urlopen(req, timeout=120, context=context) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Databricks API {method} {path} failed ({exc.code}): {detail}") from exc


def _ssl_context() -> ssl.SSLContext:
    if os.environ.get("DATABRICKS_SSL_SKIP_VERIFY", "").lower() in {"1", "true", "yes"}:
        return ssl._create_unverified_context()
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if cafile and os.path.isfile(cafile):
        return ssl.create_default_context(cafile=cafile)
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def classify_compile_error(error: str | None) -> str:
    """Return failure category for gating logic."""
    if not error:
        return "unknown"
    msg = error.lower()
    object_markers = (
        "table or view not found",
        "table_or_view_not_found",
        "unresolved_column",
        "unresolved_table",
        "cannot resolve",
        "does not exist",
        "permission denied",
        "insufficient privileges",
        "not authorized",
    )
    if any(marker in msg for marker in object_markers):
        return "object_or_permission"
    syntax_markers = (
        "parse",
        "syntax",
        "mismatched input",
        "extraneous input",
        "no viable alternative",
        "invalid",
        "unsupported",
        "analysis exception",
    )
    if any(marker in msg for marker in syntax_markers):
        return "syntax"
    return "other"
