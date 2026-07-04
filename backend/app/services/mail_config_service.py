"""Effective mail (SMTP / IMAP) configuration, per company.

The main mailbox config is stored per-company in ``app_settings`` (a per-schema
table) under the ``mail_config`` key, with passwords encrypted at rest via
``core.secret_crypto``. Reads fall back to the env ``settings.*`` values for the
default (public) schema, so the existing mailbox keeps working untouched until an
admin edits it. A non-default company with no stored config is treated as "not
configured" (its fetch is skipped and its send reports disabled).

Workers read the effective config through :func:`get_smtp_config` /
:func:`get_imap_config`; the settings API writes via the ``set_*`` helpers and
surfaces masked snapshots via the ``*_masked`` helpers (passwords never leave the
backend in plaintext).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..core import secret_crypto
from ..core.config import settings as env_settings
from ..core.tenant import DEFAULT_SCHEMA, get_current_schema
from ..models.app_setting import AppSetting

MAIL_CONFIG_KEY = "mail_config"


@dataclass
class SmtpConfig:
    enabled: bool
    host: str
    port: int
    user: str
    password: str
    from_addr: str

    def ready(self) -> tuple[bool, str]:
        """Whether this config can be used to send. Mirrors the old worker gate."""
        if not self.enabled:
            return False, "SMTP is disabled"
        if not self.host or not self.from_addr:
            return False, "SMTP host/from are missing"
        if bool(self.user) != bool(self.password):
            return False, "SMTP user and password must both be set"
        return True, ""


@dataclass
class ImapConfig:
    enabled: bool
    protocol: str
    use_ssl: bool
    host: str
    port: int
    user: str
    password: str
    folder: str

    def ready(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "Mailbox is disabled"
        if not self.host or not self.user or not self.password:
            return False, "Mailbox credentials are missing"
        return True, ""


# ── env fallbacks (default schema only) ──────────────────────────────────────
def _env_smtp() -> SmtpConfig:
    return SmtpConfig(
        enabled=bool(getattr(env_settings, "SMTP_ENABLED", False)),
        host=env_settings.SMTP_HOST or "",
        port=int(env_settings.SMTP_PORT or 587),
        user=env_settings.SMTP_USER or "",
        password=env_settings.SMTP_PASSWORD or "",
        from_addr=env_settings.SMTP_FROM or "",
    )


def _env_imap() -> ImapConfig:
    return ImapConfig(
        enabled=bool(getattr(env_settings, "MAIL_INBOX_ENABLED", False)),
        protocol=env_settings.MAIL_FETCH_PROTOCOL or "IMAP",
        use_ssl=bool(env_settings.MAIL_INBOX_USE_SSL),
        host=env_settings.IMAP_HOST or "",
        port=int(env_settings.IMAP_PORT or 0),
        user=env_settings.IMAP_USER or "",
        password=env_settings.IMAP_PASSWORD or "",
        folder=env_settings.IMAP_FOLDER or "INBOX",
    )


def env_smtp_config() -> SmtpConfig:
    """The env-var SMTP config (no DB). Used as the default for system mail and as
    the fallback on the default company schema."""
    return _env_smtp()


def env_imap_config() -> ImapConfig:
    return _env_imap()


def _on_default_schema() -> bool:
    return (get_current_schema() or DEFAULT_SCHEMA) == DEFAULT_SCHEMA


def _raw_config(db: Session) -> dict:
    row = db.get(AppSetting, MAIL_CONFIG_KEY)
    if row is None or not isinstance(row.value, dict):
        return {}
    return row.value


def _write(db: Session, raw: dict) -> None:
    row = db.get(AppSetting, MAIL_CONFIG_KEY)
    if row is None:
        db.add(AppSetting(key=MAIL_CONFIG_KEY, value=raw))
    else:
        row.value = raw  # reassign a fresh dict so SQLAlchemy sees the JSON change
    db.commit()


# ── reads (effective, decrypted) ─────────────────────────────────────────────
def get_smtp_config(db: Session) -> SmtpConfig:
    raw = _raw_config(db).get("smtp")
    if isinstance(raw, dict):
        return SmtpConfig(
            enabled=bool(raw.get("enabled", False)),
            host=str(raw.get("host") or ""),
            port=int(raw.get("port") or 587),
            user=str(raw.get("user") or ""),
            password=secret_crypto.decrypt(raw.get("password_enc")),
            from_addr=str(raw.get("from") or ""),
        )
    if _on_default_schema():
        return _env_smtp()
    return SmtpConfig(enabled=False, host="", port=587, user="", password="", from_addr="")


def get_imap_config(db: Session) -> ImapConfig:
    raw = _raw_config(db).get("imap")
    if isinstance(raw, dict):
        return ImapConfig(
            enabled=bool(raw.get("enabled", False)),
            protocol=str(raw.get("protocol") or "IMAP").upper(),
            use_ssl=bool(raw.get("use_ssl", False)),
            host=str(raw.get("host") or ""),
            port=int(raw.get("port") or 0),
            user=str(raw.get("user") or ""),
            password=secret_crypto.decrypt(raw.get("password_enc")),
            folder=str(raw.get("folder") or "INBOX"),
        )
    if _on_default_schema():
        return _env_imap()
    return ImapConfig(
        enabled=False, protocol="IMAP", use_ssl=False,
        host="", port=0, user="", password="", folder="INBOX",
    )


# ── writes (encrypt password; blank password keeps existing) ─────────────────
def set_smtp_config(
    db: Session, *, enabled: bool, host: str, port: int, user: str, from_addr: str,
    password: str | None = None,
) -> SmtpConfig:
    raw = dict(_raw_config(db))
    smtp = dict(raw.get("smtp") or {})
    smtp["enabled"] = bool(enabled)
    smtp["host"] = (host or "").strip()
    smtp["port"] = int(port or 587)
    smtp["user"] = (user or "").strip()
    smtp["from"] = (from_addr or "").strip()
    if password:
        smtp["password_enc"] = secret_crypto.encrypt(password)
    elif "password_enc" not in smtp and _on_default_schema():
        # First save on the default company with no new password entered:
        # inherit the env password so existing auth keeps working.
        smtp["password_enc"] = secret_crypto.encrypt(env_settings.SMTP_PASSWORD or "")
    raw["smtp"] = smtp
    _write(db, raw)
    return get_smtp_config(db)


def set_imap_config(
    db: Session, *, enabled: bool, protocol: str, use_ssl: bool, host: str, port: int,
    user: str, folder: str, password: str | None = None,
) -> ImapConfig:
    raw = dict(_raw_config(db))
    imap = dict(raw.get("imap") or {})
    imap["enabled"] = bool(enabled)
    imap["protocol"] = (protocol or "IMAP").strip().upper()
    imap["use_ssl"] = bool(use_ssl)
    imap["host"] = (host or "").strip()
    imap["port"] = int(port or 0)
    imap["user"] = (user or "").strip()
    imap["folder"] = (folder or "INBOX").strip()
    if password:
        imap["password_enc"] = secret_crypto.encrypt(password)
    elif "password_enc" not in imap and _on_default_schema():
        imap["password_enc"] = secret_crypto.encrypt(env_settings.IMAP_PASSWORD or "")
    raw["imap"] = imap
    _write(db, raw)
    return get_imap_config(db)


# ── masked snapshots for the API ─────────────────────────────────────────────
def _mask(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + "*" * (len(value) - 2) + value[-1]


def smtp_masked(db: Session) -> dict:
    cfg = get_smtp_config(db)
    return {
        "enabled": cfg.enabled,
        "host": cfg.host,
        "port": cfg.port,
        "user": cfg.user,
        "from": cfg.from_addr,
        "password_masked": _mask(cfg.password),
        "password_set": bool(cfg.password),
    }


def imap_masked(db: Session) -> dict:
    cfg = get_imap_config(db)
    return {
        "enabled": cfg.enabled,
        "protocol": cfg.protocol,
        "use_ssl": cfg.use_ssl,
        "host": cfg.host,
        "port": cfg.port,
        "user": cfg.user,
        "folder": cfg.folder,
        "password_masked": _mask(cfg.password),
        "password_set": bool(cfg.password),
    }
