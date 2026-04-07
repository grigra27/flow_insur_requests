"""
Security helpers for login attempts: rate limiting and lockouts.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Tuple

from django.conf import settings
from django.core.cache import cache


@dataclass(frozen=True)
class LoginLockState:
    """Represents current lock state for a login attempt."""

    is_locked: bool
    remaining_seconds: int = 0
    scope: str = ""


def _is_enabled() -> bool:
    return bool(getattr(settings, "LOGIN_RATE_LIMIT_ENABLED", True))


def _get_client_ip(request) -> str:
    """
    Returns client IP.

    If LOGIN_RATE_LIMIT_TRUST_X_FORWARDED_FOR=True, takes first IP from
    X-Forwarded-For header. Otherwise uses REMOTE_ADDR.
    """
    trust_forwarded_for = bool(
        getattr(settings, "LOGIN_RATE_LIMIT_TRUST_X_FORWARDED_FOR", False)
    )
    if trust_forwarded_for:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
            if ip:
                return ip

    return request.META.get("REMOTE_ADDR", "unknown")


def _normalize_username(username: str | None) -> str:
    if not username:
        return "_empty"
    return username.strip().lower()


def _build_scopes(request, username: str | None) -> Tuple[Tuple[str, str], ...]:
    ip = _get_client_ip(request)
    normalized_username = _normalize_username(username)
    return (
        ("ip_user", f"ip_user:{ip}:{normalized_username}"),
        ("ip", f"ip:{ip}"),
    )


def _attempts_key(scope_value: str) -> str:
    return f"auth_login_attempts:{scope_value}"


def _lock_key(scope_value: str) -> str:
    return f"auth_login_lock:{scope_value}"


def get_login_lock_state(request, username: str | None) -> LoginLockState:
    """
    Checks lock state for username+ip and ip scopes.
    Returns active lock with the longest remaining time.
    """
    if not _is_enabled():
        return LoginLockState(is_locked=False)

    now = time.time()
    max_remaining = 0
    active_scope = ""

    for scope_name, scope_value in _build_scopes(request, username):
        lock_until = cache.get(_lock_key(scope_value))
        if lock_until is None:
            continue

        try:
            lock_until_ts = float(lock_until)
        except (TypeError, ValueError):
            cache.delete(_lock_key(scope_value))
            continue

        remaining = int(lock_until_ts - now)
        if remaining <= 0:
            cache.delete(_lock_key(scope_value))
            continue

        if remaining > max_remaining:
            max_remaining = remaining
            active_scope = scope_name

    if max_remaining > 0:
        return LoginLockState(
            is_locked=True,
            remaining_seconds=max_remaining,
            scope=active_scope,
        )
    return LoginLockState(is_locked=False)


def register_failed_login_attempt(request, username: str | None) -> LoginLockState:
    """
    Registers failed login attempt for:
    - username+ip scope
    - ip scope

    If threshold reached, creates lock for LOGIN_LOCKOUT_SECONDS.
    """
    if not _is_enabled():
        return LoginLockState(is_locked=False)

    now = time.time()
    attempt_window = int(getattr(settings, "LOGIN_ATTEMPT_WINDOW_SECONDS", 900))
    lockout_seconds = int(getattr(settings, "LOGIN_LOCKOUT_SECONDS", 900))
    max_attempts = int(getattr(settings, "LOGIN_MAX_ATTEMPTS", 5))
    max_attempts_per_ip = int(getattr(settings, "LOGIN_MAX_ATTEMPTS_PER_IP", 20))

    if attempt_window <= 0 or lockout_seconds <= 0:
        return LoginLockState(is_locked=False)

    scope_limits = {
        "ip_user": max_attempts,
        "ip": max_attempts_per_ip,
    }

    for scope_name, scope_value in _build_scopes(request, username):
        scope_limit = int(scope_limits.get(scope_name, 0))
        if scope_limit <= 0:
            continue

        attempts_cache_key = _attempts_key(scope_value)
        attempts_payload = cache.get(attempts_cache_key)
        if not isinstance(attempts_payload, dict):
            attempts_payload = {"count": 0, "first_attempt_at": now}

        first_attempt_at = float(attempts_payload.get("first_attempt_at", now))
        if now - first_attempt_at > attempt_window:
            attempts_payload = {"count": 0, "first_attempt_at": now}

        attempts_payload["count"] = int(attempts_payload.get("count", 0)) + 1
        remaining_window = max(
            1, int(attempt_window - (now - float(attempts_payload["first_attempt_at"])))
        )
        cache.set(attempts_cache_key, attempts_payload, timeout=remaining_window)

        if attempts_payload["count"] >= scope_limit:
            lock_until = now + lockout_seconds
            cache.set(_lock_key(scope_value), lock_until, timeout=lockout_seconds)

    return get_login_lock_state(request, username)


def clear_login_failures(request, username: str | None) -> None:
    """
    Clears failures for username+ip scope after successful login.
    IP-wide counters are intentionally kept to protect against spray attacks.
    """
    if not _is_enabled():
        return

    scope_name, scope_value = _build_scopes(request, username)[0]  # ip_user scope
    if scope_name:
        cache.delete(_attempts_key(scope_value))
        cache.delete(_lock_key(scope_value))


def format_lockout_message(remaining_seconds: int) -> str:
    """Formats a human-readable lockout message in Russian."""
    minutes = max(1, math.ceil(max(0, remaining_seconds) / 60))
    return (
        "Слишком много неудачных попыток входа. "
        f"Попробуйте снова через {minutes} мин."
    )


def get_login_client_ip(request) -> str:
    """Public helper for logging in views."""
    return _get_client_ip(request)

