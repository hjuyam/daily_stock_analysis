# -*- coding: utf-8 -*-
"""Shared Web/API exposure safeguards."""

from __future__ import annotations

import os


ALLOW_INSECURE_PUBLIC_API_ENV = "DSA_ALLOW_INSECURE_PUBLIC_API"
WEBUI_BOUND_HOST_ENV = "DSA_WEBUI_BOUND_HOST"

_PUBLIC_BIND_HOSTS = frozenset({"0.0.0.0", "::", "[::]", "*"})
_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})


def is_public_bind_host(host: str) -> bool:
    """Return whether a host value binds the service to public interfaces."""
    return (host or "").strip().lower() in _PUBLIC_BIND_HOSTS


def is_insecure_public_api_allowed() -> bool:
    """Return whether the operator explicitly allowed public auth-disabled API."""
    return os.getenv(ALLOW_INSECURE_PUBLIC_API_ENV, "").strip().lower() in _TRUTHY_VALUES


def public_auth_guard_message(host: str) -> str:
    """Build the public-bind/auth-disabled guard error message."""
    return (
        f"WEBUI_HOST={host} binds the Web UI/API to a public interface while "
        "ADMIN_AUTH_ENABLED=false. Enable admin authentication before exposing "
        f"the service, or set {ALLOW_INSECURE_PUBLIC_API_ENV}=true only for a "
        "trusted temporary/local deployment."
    )


def enforce_public_webui_auth_guard(host: str, *, auth_enabled: bool) -> None:
    """Fail closed for public Web/API binds unless auth or explicit override is enabled."""
    if not is_public_bind_host(host):
        return
    if auth_enabled or is_insecure_public_api_allowed():
        return
    raise RuntimeError(public_auth_guard_message(host))


def current_webui_bound_host() -> str:
    """Return the best-known runtime bind host for request-time safeguards."""
    return (
        os.getenv(WEBUI_BOUND_HOST_ENV)
        or os.getenv("WEBUI_HOST")
        or ""
    ).strip()
