from __future__ import annotations

import ipaddress
from collections.abc import Iterable

from fastapi import Request


def is_trusted_proxy(peer: str, trusted_proxies: Iterable[str]) -> bool:
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    for entry in trusted_proxies:
        try:
            if "/" in entry:
                if address in ipaddress.ip_network(entry, strict=False):
                    return True
            elif address == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


def client_ip(request: Request, trusted_proxies: tuple[str, ...]) -> str:
    peer = request.client.host if request.client is not None else "unknown"
    if not trusted_proxies or not is_trusted_proxy(peer, trusted_proxies):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return peer
