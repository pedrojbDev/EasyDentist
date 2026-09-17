from __future__ import annotations

from types import SimpleNamespace

from app.platform.network import client_ip, is_trusted_proxy


def fake_request(peer: str, headers: dict[str, str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        client=SimpleNamespace(host=peer),
        headers=headers if headers is not None else {},
    )


def test_untrusted_peer_ignores_forwarded_header() -> None:
    request = fake_request("203.0.113.9", {"x-forwarded-for": "198.51.100.7"})

    assert client_ip(request, ("10.0.0.1",)) == "203.0.113.9"  # type: ignore[arg-type]


def test_trusted_exact_peer_honors_first_forwarded_entry() -> None:
    request = fake_request("10.0.0.1", {"x-forwarded-for": "198.51.100.7, 10.0.0.2"})

    assert client_ip(request, ("10.0.0.1",)) == "198.51.100.7"  # type: ignore[arg-type]


def test_trusted_cidr_peer_honors_forwarded_header() -> None:
    request = fake_request("10.1.2.3", {"x-forwarded-for": "198.51.100.7"})

    assert client_ip(request, ("10.0.0.0/8",)) == "198.51.100.7"  # type: ignore[arg-type]


def test_trusted_peer_without_header_returns_peer() -> None:
    request = fake_request("10.0.0.1")

    assert client_ip(request, ("10.0.0.1",)) == "10.0.0.1"  # type: ignore[arg-type]


def test_empty_trusted_list_returns_peer() -> None:
    request = fake_request("10.0.0.1", {"x-forwarded-for": "198.51.100.7"})

    assert client_ip(request, ()) == "10.0.0.1"  # type: ignore[arg-type]


def test_invalid_entries_are_ignored() -> None:
    request = fake_request("10.0.0.1", {"x-forwarded-for": "198.51.100.7"})

    assert client_ip(request, ("not-an-ip", "10.0.0.1")) == "198.51.100.7"  # type: ignore[arg-type]


def test_blank_forwarded_header_falls_back_to_peer() -> None:
    request = fake_request("10.0.0.1", {"x-forwarded-for": "   "})

    assert client_ip(request, ("10.0.0.1",)) == "10.0.0.1"  # type: ignore[arg-type]


def test_is_trusted_proxy_rejects_malformed_peer() -> None:
    assert is_trusted_proxy("not-an-ip", ("10.0.0.1",)) is False
