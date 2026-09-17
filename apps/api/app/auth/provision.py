from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from app.auth.emails import EmailSender, SmtpEmailSender
from app.auth.provisioning import DEFAULT_TIMEZONE, ProvisionService
from app.auth.settings import AuthSettings
from app.core.database import DatabaseSettings, create_database_engine, create_session_factory
from app.core.errors import ConflictError, DomainError


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.auth.provision",
        description="Provisiona uma clínica com um convite OWNER de uso único.",
    )
    parser.add_argument("--email", required=True, help="e-mail do futuro OWNER")
    parser.add_argument("--name", required=True, help="razão social da clínica")
    parser.add_argument("--slug", required=True, help="slug único da clínica")
    parser.add_argument("--display-name", default=None, help="nome comercial (default: --name)")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help="timezone IANA")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace, *, sender: EmailSender | None = None) -> int:
    database_settings = DatabaseSettings.from_environment()
    auth_settings = AuthSettings.from_environment()
    engine = create_database_engine(database_settings.database_url)
    try:
        service = ProvisionService(
            create_session_factory(engine),
            auth_settings,
            sender if sender is not None else SmtpEmailSender(auth_settings),
        )
        try:
            provisioned = await service.provision(
                email=args.email,
                name=args.name,
                slug=args.slug,
                display_name=args.display_name,
                timezone=args.timezone,
            )
        except ConflictError:
            print("erro: conflito — já existe uma clínica com este slug", file=sys.stderr)
            return 1
        except DomainError as error:
            print(f"erro: {error}", file=sys.stderr)
            return 1
    finally:
        await engine.dispose()

    print(f"user_id={provisioned.user_id}")
    print(f"clinic_id={provisioned.clinic_id}")
    print(f"slug={provisioned.slug}")
    print(f"email={provisioned.recipient}")
    print(f"invitation_expires_at={provisioned.invitation_expires_at.isoformat()}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
