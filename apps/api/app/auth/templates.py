from __future__ import annotations

from app.auth.settings import AuthSettings
from app.auth.tokens import token_digest

EMAIL_VERIFICATION_TEMPLATE = "email-verification"
PASSWORD_RESET_TEMPLATE = "password-reset"
INVITATION_TEMPLATE = "invitation"

EMAIL_VERIFICATION_PATH = "/verify-email"
PASSWORD_RESET_PATH = "/reset-password"
INVITATION_PATH = "/accept-invitation"


def email_idempotency_key(template: str, token: str) -> str:
    return f"{template}:{token_digest(token).hex()}"


def _link(settings: AuthSettings, path: str, token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}{path}#token={token}"


def email_verification_message(settings: AuthSettings, token: str) -> tuple[str, str]:
    link = _link(settings, EMAIL_VERIFICATION_PATH, token)
    subject = "Confirme seu e-mail — EasyDentist"
    body = (
        "Olá!\n\n"
        "Confirme seu e-mail para ativar sua conta no EasyDentist:\n"
        f"{link}\n\n"
        "O link é de uso único e expira em 24 horas.\n"
        "Se você não reconhece este cadastro, ignore esta mensagem.\n"
    )
    return subject, body


def password_reset_message(settings: AuthSettings, token: str) -> tuple[str, str]:
    link = _link(settings, PASSWORD_RESET_PATH, token)
    subject = "Recuperação de senha — EasyDentist"
    body = (
        "Olá!\n\n"
        "Recebemos um pedido de recuperação de senha da sua conta no EasyDentist:\n"
        f"{link}\n\n"
        "O link é de uso único e expira em 30 minutos. Por segurança, "
        "a recuperação revoga todas as sessões ativas.\n"
        "Se não foi você, ignore esta mensagem.\n"
    )
    return subject, body


def invitation_message(settings: AuthSettings, token: str, *, clinic_name: str) -> tuple[str, str]:
    link = _link(settings, INVITATION_PATH, token)
    subject = f"Convite para {clinic_name} — EasyDentist"
    body = (
        f"Olá!\n\n"
        f"Você foi convidado a administrar a clínica {clinic_name} no EasyDentist.\n"
        f"Defina sua senha e ative a conta pelo link:\n"
        f"{link}\n\n"
        "O link é de uso único e expira em 72 horas.\n"
        "Se você não esperava este convite, ignore esta mensagem.\n"
    )
    return subject, body
