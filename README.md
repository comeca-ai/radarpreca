# Radar Precatório

Site e API da prova de conceito: bases públicas de precatórios (SIOP, TRF2, TRF4 e TRF5), inclusive a fila pendente do TRF4, com busca, filtros e a análise exploratória do SIOP 2026.

Testado em 12/11/2026 (America/Sao_Paulo).

## Como rodar

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Na primeira subida o app descompacta `data/precatorios.sqlite.gz` para `/tmp/radar-precatorio/precatorios.sqlite`.

## Endpoints

- `GET /` — site (abas Consulta, Precificação, Bases, Aprendizado e Projeto)
- `GET /api/consulta?q=&fonte=&tribunal=&ente=&natureza=&status=&ano_orcamento=&min_valor=&max_valor=&sort=valor|posicao&order=asc|desc&page=`
- `GET /api/health`
- `GET /api/bases` — fontes, datas e limites
- `GET /api/stats` — resumo da análise do SIOP
- `GET /api/siop?tribunal=&uo=&nfgc=&min_valor=&q=&page=`
- `GET /api/trf/pagos?tribunal=&proposta=&min_valor=&q=&page=`
- `GET /api/trf4/pendentes?ente=&natureza=&tipo_lista=&ano_orcamento=&min_valor=&q=&page=`
- `GET /api/trf/mapas?tribunal=&q=&page=`
- `GET /api/trf/extra?q=&page=`
- `GET /api/download/siop.csv` (e equivalentes para pagos, mapas e `trf4_pendentes.csv`)

A fila pendente do TRF4 entra como `data/trf4_pendentes.csv.gz` e é carregada à parte, em `/tmp/radar-precatorio/trf4_pendentes.sqlite`. Para atualizar: `python scripts/trf4_pendentes.py --out /tmp/trf4_pendentes.csv` e compactar o CSV para `data/trf4_pendentes.csv.gz`.

Os CPF/CNPJ de beneficiários entram só na forma parcial já publicada pelas listas dos tribunais.

## Autenticação

Consulta, Precificação e Bases — e as APIs correspondentes — exigem login. Aprendizado, Projeto e `GET /api/health` continuam abertos.

A sessão vai num cookie HttpOnly assinado (`radar_session`). A senha é guardada só como hash bcrypt.

Crie o primeiro administrador com:

```bash
python scripts/criar_usuario.py SEU_EMAIL --admin
```

A senha é gerada e gravada em `~/.config/radarpreca/admin_credentials.txt` (chmod 600). Não há cadastro público; usuários extras saem do mesmo script (`--senha`) ou de `POST /api/admin/usuarios`, que só um administrador autenticado pode chamar.

### Disco efêmero no Render

O plano free do Render não preserva arquivos entre redeploys. O SQLite de usuários (`data/users.sqlite`, ou o caminho em `USERS_DB`) some quando o serviço é publicado de novo. Para o login sobreviver, defina no painel do Render:

- `SECRET_KEY` — chave longa e aleatória para assinar o cookie de sessão. Sem ela, o app usa uma chave insegura só adequada ao desenvolvimento local.
- `ADMIN_EMAIL` — e-mail do administrador.
- `ADMIN_PASSWORD_HASH` — hash bcrypt da senha (o script grava esse valor no arquivo de credenciais, campo `password_hash`). Não coloque a senha em texto claro no ambiente.

Na subida, o app recria o administrador a partir dessas variáveis. Opcional: `COOKIE_SECURE=true` força o cookie `Secure` (no Render, atrás de HTTPS, isso já é detectado). `SESSION_MAX_AGE` é a validade da sessão em segundos (padrão: 14 dias).

## Endpoints de sessão

- `POST /api/login` — corpo JSON `{ "email", "senha" }`
- `POST /api/logout`
- `GET /api/me`
- `POST /api/admin/usuarios` — corpo `{ "email", "senha", "role" }`, só admin
