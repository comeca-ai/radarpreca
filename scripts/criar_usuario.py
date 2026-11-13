#!/usr/bin/env python3
"""Cria um usuário do Radar Precatório. Sem cadastro público: só este script ou a rota de admin.

Uso:
  python scripts/criar_usuario.py EMAIL
  python scripts/criar_usuario.py EMAIL --senha 'uma-senha-segura'
  python scripts/criar_usuario.py EMAIL --admin

Sem --senha, uma senha aleatória é gerada. A senha inicial do administrador
é gravada em ~/.config/radarpreca/admin_credentials.txt (chmod 600) e não
é impressa no terminal.
"""
from __future__ import annotations

import argparse
import os
import secrets
import stat
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import auth  # noqa: E402

DEFAULT_CREDENTIALS = Path.home() / ".config" / "radarpreca" / "admin_credentials.txt"
SP = timezone(timedelta(hours=-3))


def gerar_senha() -> str:
    # 18 bytes → ~24 caracteres url-safe, acima do mínimo de 8 e abaixo do teto do bcrypt.
    return secrets.token_urlsafe(18)


def gravar_credenciais(path: Path, email: str, password: str, password_hash: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    agora = datetime.now(SP).strftime("%Y-%m-%d %H:%M:%S America/Sao_Paulo")
    corpo = (
        f"email={email}\n"
        f"password={password}\n"
        f"password_hash={password_hash}\n"
        f"criado_em={agora}\n"
        f"plano=Preca\n"
    )
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(corpo)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def main() -> int:
    parser = argparse.ArgumentParser(description="Cria um usuário do Radar Precatório.")
    parser.add_argument("email", help="E-mail do usuário")
    parser.add_argument("--senha", default=None, help="Senha em texto. Se omitida, é gerada.")
    parser.add_argument("--admin", action="store_true", help="Cria com papel de administrador.")
    parser.add_argument(
        "--credenciais",
        default=str(DEFAULT_CREDENTIALS),
        help="Arquivo onde gravar a senha gerada (padrão: ~/.config/radarpreca/admin_credentials.txt)",
    )
    args = parser.parse_args()

    auth.ensure_users_db()
    if args.senha is None and not args.admin:
        print("Erro: informe --senha, ou use --admin para gerar e gravar a senha inicial.", file=sys.stderr)
        return 1
    gerada = args.senha is None
    password = args.senha if args.senha is not None else gerar_senha()
    role = "admin" if args.admin else "user"

    try:
        user = auth.create_user(args.email, password, role=role)
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    cred_path = Path(args.credenciais).expanduser()
    if gerada and args.admin:
        gravar_credenciais(cred_path, user.email, password, user.password_hash or "")
        print(f"Usuário {user.email} ({user.role}) criado.")
        print(f"Senha gerada gravada em {cred_path} (chmod 600).")
        print("A senha não é exibida aqui. Para o Render, use também SECRET_KEY,")
        print("ADMIN_EMAIL e ADMIN_PASSWORD_HASH (o hash está no mesmo arquivo).")
    else:
        print(f"Usuário {user.email} ({user.role}) criado. A senha informada não foi exibida nem gravada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
