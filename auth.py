"""Autenticação do Radar Precatório: usuários, sessão e proteção de rotas."""
from __future__ import annotations

import logging
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("radar.auth")

ROOT = Path(__file__).resolve().parent
USERS_DB = Path(os.environ.get("USERS_DB", str(ROOT / "data" / "users.sqlite")))

COOKIE_NAME = "radar_session"
SESSION_SALT = "radar-session-v1"
SESSION_MAX_AGE = int(os.environ.get("SESSION_MAX_AGE", str(14 * 24 * 60 * 60)))
DEV_SECRET_FALLBACK = "radar-precatorio-dev-only-nao-usar-em-producao"
PASSWORD_MAX_BYTES = 72

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# APIs e arquivos da Consulta, Precificação e Bases.
PROTECTED_PREFIXES = (
    "/api/consulta",
    "/api/precificar",
    "/api/download",
    "/api/trf4",
    "/api/siop",
    "/api/trf/",
    "/api/bases",
    "/api/stats",
    "/api/admin",
    "/eda/",
)

PUBLIC_EXACT = frozenset(
    {
        "/",
        "/api/health",
        "/api/login",
        "/api/logout",
        "/api/me",
    }
)

PUBLIC_SUFFIXES = frozenset({".css", ".js", ".woff", ".woff2", ".ttf", ".map", ".ico", ".txt"})


@dataclass(frozen=True)
class User:
    email: str
    role: str
    password_hash: str | None = None


def secret_key() -> str:
    key = (os.environ.get("SECRET_KEY") or "").strip()
    if key:
        return key
    logger.warning(
        "SECRET_KEY não definida; usando chave insegura só para desenvolvimento. "
        "Defina SECRET_KEY no ambiente antes de publicar."
    )
    return DEV_SECRET_FALLBACK


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key(), salt=SESSION_SALT)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(normalize_email(email)))


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > PASSWORD_MAX_BYTES:
        raise ValueError("A senha deve ter no máximo 72 bytes.")
    if len(password) < 8:
        raise ValueError("A senha deve ter pelo menos 8 caracteres.")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        raw = password.encode("utf-8")
        if len(raw) > PASSWORD_MAX_BYTES:
            return False
        return bcrypt.checkpw(raw, password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def ensure_users_db() -> Path:
    USERS_DB.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(USERS_DB)) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL
            )
            """
        )
        con.commit()
    _sync_admin_from_env()
    return USERS_DB


def _connect() -> sqlite3.Connection:
    ensure_users_db()
    con = sqlite3.connect(USERS_DB)
    con.row_factory = sqlite3.Row
    return con


def _sync_admin_from_env() -> None:
    """No plano free do Render o SQLite some no redeploy. O admin pode vir do ambiente."""
    email = normalize_email(os.environ.get("ADMIN_EMAIL", ""))
    password_hash = (os.environ.get("ADMIN_PASSWORD_HASH") or "").strip()
    if not email or not password_hash:
        return
    if not valid_email(email):
        logger.warning("ADMIN_EMAIL inválido; ignorando usuário do ambiente.")
        return
    if not password_hash.startswith("$2"):
        logger.warning("ADMIN_PASSWORD_HASH não parece um hash bcrypt; ignorando.")
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(sqlite3.connect(USERS_DB)) as con:
        con.execute(
            """
            INSERT INTO users (email, password_hash, role, created_at)
            VALUES (?, ?, 'admin', ?)
            ON CONFLICT(email) DO UPDATE SET
                password_hash = excluded.password_hash,
                role = 'admin'
            """,
            (email, password_hash, now),
        )
        con.commit()
    logger.info("Administrador sincronizado a partir de ADMIN_EMAIL.")


def get_user(email: str) -> User | None:
    email = normalize_email(email)
    if not email:
        return None
    with closing(_connect()) as con:
        row = con.execute(
            "SELECT email, password_hash, role FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    if not row:
        # Mesmo sem linha no SQLite, aceita o admin do ambiente (disco efêmero).
        env_email = normalize_email(os.environ.get("ADMIN_EMAIL", ""))
        env_hash = (os.environ.get("ADMIN_PASSWORD_HASH") or "").strip()
        if email == env_email and env_hash.startswith("$2"):
            return User(email=email, role="admin", password_hash=env_hash)
        return None
    return User(email=row["email"], role=row["role"], password_hash=row["password_hash"])


def create_user(email: str, password: str, role: str = "user") -> User:
    email = normalize_email(email)
    if not valid_email(email):
        raise ValueError("Informe um e-mail válido.")
    role = role if role in {"admin", "user"} else "user"
    password_hash = hash_password(password)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(_connect()) as con:
        try:
            con.execute(
                "INSERT INTO users (email, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (email, password_hash, role, now),
            )
            con.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("Já existe um usuário com este e-mail.") from exc
    return User(email=email, role=role, password_hash=password_hash)


def authenticate(email: str, password: str) -> User | None:
    user = get_user(email)
    if not user or not user.password_hash:
        # Compara com um hash dummy para não vazar a existência do e-mail pelo tempo.
        dummy = bcrypt.hashpw(b"dummy-timing", bcrypt.gensalt(rounds=4))
        bcrypt.checkpw(b"dummy-timing", dummy)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def session_token(user: User) -> str:
    return _serializer().dumps({"email": user.email, "role": user.role})


def user_from_token(token: str | None) -> User | None:
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None
    email = normalize_email(str(data.get("email") or ""))
    if not email:
        return None
    user = get_user(email)
    if not user:
        return None
    return User(email=user.email, role=user.role)


def current_user(request: Request) -> User | None:
    return user_from_token(request.cookies.get(COOKIE_NAME))


def cookie_secure(request: Request) -> bool:
    flag = (os.environ.get("COOKIE_SECURE") or "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return True
    if flag in {"0", "false", "no"}:
        return False
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return proto.split(",")[0].strip() == "https"


def set_session_cookie(response: Response, request: Request, user: User) -> None:
    response.set_cookie(
        COOKIE_NAME,
        session_token(user),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(request),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def is_public_path(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    if path.startswith("/api/") or path.startswith("/eda/"):
        return any(path == p or path.startswith(p) for p in ("/api/health", "/api/login", "/api/logout", "/api/me"))
    suffix = Path(path).suffix.lower()
    if suffix in PUBLIC_SUFFIXES:
        return True
    return False


def is_protected_path(path: str) -> bool:
    if is_public_path(path):
        return False
    return any(path == prefix or path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if is_protected_path(path) and current_user(request) is None:
        return JSONResponse({"detail": "Não autenticado."}, status_code=401)
    return await call_next(request)
