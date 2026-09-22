from __future__ import annotations

import asyncpg
import httpx
import pytest
from conftest import SeededTenants, make_test_email
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.sessions import SessionService
from app.auth.settings import AuthSettings

TENANT_TABLES = (
    "clinics",
    "memberships",
    "clinic_settings",
    "clinic_feature_flags",
    "membership_invitations",
    "clinic_audit_events",
)

TENANT_SCOPED_TABLES = (
    "clinic_settings",
    "clinic_feature_flags",
    "membership_invitations",
    "clinic_audit_events",
)

CSRF_COOKIE = "easydent_csrf"
SESSION_COOKIE = "easydent_session"
ORIGIN = "http://testserver"


@pytest.mark.anyio
async def test_rls_is_forced_and_roles_cannot_bypass(
    admin_connection: asyncpg.Connection,
) -> None:
    rows = await admin_connection.fetch(
        """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'app' AND c.relname = ANY($1::text[])
        """,
        list(TENANT_TABLES),
    )
    state = {row["relname"]: (row["relrowsecurity"], row["relforcerowsecurity"]) for row in rows}

    assert set(state) == set(TENANT_TABLES)
    for table, (enabled, forced) in state.items():
        assert enabled is True, table
        assert forced is True, table

    roles = await admin_connection.fetch(
        "SELECT rolname, rolbypassrls FROM pg_roles WHERE rolname = ANY($1::text[])",
        ["easydentist_app", "easydentist_migrator"],
    )
    assert {row["rolname"] for row in roles} == {"easydentist_app", "easydentist_migrator"}
    assert not any(row["rolbypassrls"] for row in roles)


async def settings_visible_with_context(
    connection: asyncpg.Connection,
    *,
    user_id: object,
    clinic_id: object,
) -> list[object]:
    transaction = connection.transaction()
    await transaction.start()
    try:
        await connection.execute(
            "SELECT set_config('app.current_user_id', $1, true), "
            "set_config('app.current_clinic_id', $2, true)",
            str(user_id),
            str(clinic_id),
        )
        rows = await connection.fetch("SELECT clinic_id FROM app.clinic_settings")
        return [row["clinic_id"] for row in rows]
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_reused_pool_interleaved_contexts_and_fail_closed(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    assert await app_connection.fetchval("SELECT count(*) FROM app.clinic_settings") == 0, (
        "context-free queries must fail closed"
    )

    for table in TENANT_SCOPED_TABLES:
        count = await app_connection.fetchval(f"SELECT count(*) FROM app.{table}")
        assert count == 0, table

    for _ in range(2):
        assert await settings_visible_with_context(
            app_connection, user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a
        ) == [seeded_tenants.clinic_a]
        assert await settings_visible_with_context(
            app_connection, user_id=seeded_tenants.user_b, clinic_id=seeded_tenants.clinic_b
        ) == [seeded_tenants.clinic_b]

    mismatched = await settings_visible_with_context(
        app_connection, user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_b
    )
    assert mismatched == []


@pytest.mark.anyio
async def test_api_hides_foreign_clinic_and_revocation_is_immediate(
    api_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    seeded_tenants: SeededTenants,
    migrator_connection: asyncpg.Connection,
) -> None:
    sessions = SessionService(session_factory, auth_settings)
    try:
        _, token = await sessions.create(seeded_tenants.user_a)
        api_client.cookies.set(auth_settings.session_cookie_name, token)

        own = await api_client.get(f"/api/v1/clinics/{seeded_tenants.clinic_a}")
        assert own.status_code == 200

        for path in (
            f"/api/v1/clinics/{seeded_tenants.clinic_b}",
            f"/api/v1/clinics/{seeded_tenants.clinic_b}/settings",
            f"/api/v1/clinics/{seeded_tenants.clinic_b}/memberships",
        ):
            response = await api_client.get(path)
            assert response.status_code == 404, path
            assert str(seeded_tenants.clinic_b) not in response.text, path

        listing = await api_client.get("/api/v1/clinics")
        assert listing.status_code == 200
        assert [row["id"] for row in listing.json()] == [str(seeded_tenants.clinic_a)]

        await migrator_connection.execute(
            "DELETE FROM app.membership_invitations WHERE membership_id = $1",
            seeded_tenants.membership_a,
        )
        await migrator_connection.execute(
            "DELETE FROM app.memberships WHERE id = $1", seeded_tenants.membership_a
        )
        revoked = await api_client.get(f"/api/v1/clinics/{seeded_tenants.clinic_a}")
        assert revoked.status_code == 404
    finally:
        api_client.cookies.clear()
        await sessions.revoke_all(seeded_tenants.user_a)
        await migrator_connection.execute(
            "DELETE FROM app.auth_sessions WHERE user_id = $1", seeded_tenants.user_a
        )


def cookie_attributes(response: httpx.Response, name: str) -> dict[str, str]:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{name}="):
            parts = [part.strip() for part in header.split(";")[1:]]
            attributes: dict[str, str] = {}
            for part in parts:
                key, _, value = part.partition("=")
                attributes[key.lower()] = value
            return attributes
    raise AssertionError(f"missing Set-Cookie for {name}")


@pytest.mark.anyio
async def test_cookie_contract_session_is_httponly_and_csrf_is_readable(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    email = make_test_email("m16-cookie")
    password = "m16-cookie-password"
    await seed_user_with_password(email=email, password=password)

    csrf_response = await api_client.get("/api/v1/auth/csrf")
    csrf_attributes = cookie_attributes(csrf_response, CSRF_COOKIE)
    assert "httponly" not in csrf_attributes
    assert csrf_attributes.get("samesite", "").lower() == "lax"
    assert csrf_attributes.get("path") == "/"
    csrf = csrf_response.json()["csrf_token"]

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"Cookie": f"{CSRF_COOKIE}={csrf}", "X-CSRF-Token": csrf, "Origin": ORIGIN},
    )
    assert login_response.status_code == 200
    session_attributes = cookie_attributes(login_response, SESSION_COOKIE)
    assert "httponly" in session_attributes
    assert session_attributes.get("samesite", "").lower() == "lax"
    assert session_attributes.get("path") == "/"
    assert "domain" not in session_attributes
    api_client.cookies.clear()
