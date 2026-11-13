#!/usr/bin/env python3
"""Radar Precatório — site + API de consulta das bases da prova de conceito."""
from __future__ import annotations

import csv
import gzip
import io
import json
import os
import shutil
import sqlite3
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Any, Iterable

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
PACKED_DB = ROOT / "data" / "precatorios.sqlite.gz"
MANIFEST_PATH = ROOT / "data" / "manifest.json"
STATS_PATH = ROOT / "data" / "stats.json"
STATIC = ROOT / "static"
DB_PATH = Path(os.environ.get("DB_PATH", "/tmp/radar-precatorio/precatorios.sqlite"))

PAGE_DEFAULT = 25
PAGE_MAX = 100

MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
STATS = json.loads(STATS_PATH.read_text(encoding="utf-8"))


def ensure_db() -> Path:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists() and DB_PATH.stat().st_size > 1_000_000:
        return DB_PATH
    if not PACKED_DB.exists():
        raise RuntimeError(f"Base compactada não encontrada: {PACKED_DB}")
    tmp = DB_PATH.with_suffix(".sqlite.partial")
    with gzip.open(PACKED_DB, "rb") as src, open(tmp, "wb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    tmp.replace(DB_PATH)
    return DB_PATH


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_db()
    yield


app = FastAPI(
    title="Radar Precatório",
    version="0.1.0",
    lifespan=lifespan,
)
app.mount("/eda", StaticFiles(directory=str(STATIC / "eda")), name="eda")


def json_safe(val: Any) -> Any:
    if isinstance(val, bytes):
        return val.decode("utf-8", "replace")
    return val


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [{k: json_safe(r[k]) for k in r.keys()} for r in rows]


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = min(PAGE_MAX, max(1, page_size))
    return page, page_size


def like(term: str) -> str:
    return f"%{term.replace('%', '').replace('_', ' ').strip()}%"


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    ok = DB_PATH.exists()
    n = None
    if ok:
        with closing(connect()) as con:
            n = con.execute("SELECT COUNT(*) FROM siop").fetchone()[0]
    return {"ok": ok, "db": str(DB_PATH.name), "siop": n, "testado_em": "12/11/2026"}


@app.get("/api/bases")
def bases():
    return MANIFEST


@app.get("/api/stats")
def stats():
    return {
        "fonte": "SIOP / Ministério do Planejamento, expedidos_2026.csv",
        "testado_em": "12/11/2026",
        "graficos": [
            {"id": "01", "arquivo": "/eda/01_valor_por_ramo.png", "titulo": "Valor por ramo da Justiça"},
            {"id": "02", "arquivo": "/eda/02_valor_por_tribunal.png", "titulo": "Valor por tribunal"},
            {"id": "03", "arquivo": "/eda/03_top_uos.png", "titulo": "Principais unidades orçamentárias"},
            {"id": "04", "arquivo": "/eda/04_classificacao_nfgc.png", "titulo": "Classificação NFGC"},
            {"id": "05", "arquivo": "/eda/05_faixa_de_valor.png", "titulo": "Faixa de valor"},
            {"id": "06", "arquivo": "/eda/06_concentracao_valor.png", "titulo": "Concentração de valor"},
        ],
        "stats": STATS,
    }


@app.get("/api/siop/facets")
def siop_facets():
    with closing(connect()) as con:
        tribunais = [r[0] for r in con.execute(
            "SELECT nome_tribunal, COUNT(*) n FROM siop GROUP BY 1 ORDER BY n DESC"
        )]
        nfgc = [r[0] for r in con.execute(
            "SELECT class_nfgc, COUNT(*) n FROM siop WHERE class_nfgc IS NOT NULL GROUP BY 1 ORDER BY n DESC"
        )]
        faixas = [r[0] for r in con.execute(
            "SELECT faixa_valor, COUNT(*) n FROM siop WHERE faixa_valor IS NOT NULL GROUP BY 1 ORDER BY n DESC"
        )]
        uos = [r[0] for r in con.execute(
            "SELECT nome_uo FROM siop WHERE nome_uo IS NOT NULL GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 200"
        )]
    return {"tribunais": tribunais, "nfgc": nfgc, "faixas": faixas, "uos": uos}


def siop_where(tribunal, uo, nfgc, min_valor, max_valor, q):
    clauses = []
    params: list[Any] = []
    if tribunal:
        clauses.append("nome_tribunal = ?")
        params.append(tribunal)
    if uo:
        clauses.append("nome_uo = ?")
        params.append(uo)
    if nfgc:
        clauses.append("class_nfgc = ?")
        params.append(nfgc)
    if min_valor is not None:
        clauses.append("valor_atualizado >= ?")
        params.append(min_valor)
    if max_valor is not None:
        clauses.append("valor_atualizado <= ?")
        params.append(max_valor)
    if q:
        clauses.append(
            "(chave LIKE ? OR nome_uo LIKE ? OR tipo_causa LIKE ? OR nome_tribunal LIKE ? OR tribunal_expedidor LIKE ?)"
        )
        pat = like(q)
        params.extend([pat] * 5)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


@app.get("/api/siop")
def api_siop(
    tribunal: str | None = None,
    uo: str | None = None,
    nfgc: str | None = None,
    min_valor: float | None = None,
    max_valor: float | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = PAGE_DEFAULT,
):
    page, page_size = clamp_page(page, page_size)
    where, params = siop_where(tribunal, uo, nfgc, min_valor, max_valor, q)
    offset = (page - 1) * page_size
    sql = f"""
        SELECT chave, exercicio, nome_tribunal, tribunal_expedidor, data_ajuizamento, data_autuacao,
               tributario, nome_uo, tipo_causa, valor_original, fundef, anos_decorridos,
               class_tempo, class_tribunais, class_nfgc, valor_atualizado, faixa_valor
        FROM siop {where}
        ORDER BY valor_atualizado DESC
        LIMIT ? OFFSET ?
    """
    count_sql = f"SELECT COUNT(*) FROM siop {where}"
    sum_sql = f"SELECT COALESCE(SUM(valor_atualizado),0), COALESCE(SUM(valor_original),0) FROM siop {where}"
    with closing(connect()) as con:
        total = con.execute(count_sql, params).fetchone()[0]
        sum_atu, sum_orig = con.execute(sum_sql, params).fetchone()
        rows = con.execute(sql, [*params, page_size, offset]).fetchall()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 0,
        "soma_valor_atualizado": sum_atu,
        "soma_valor_original": sum_orig,
        "rows": rows_to_dicts(rows),
    }


@app.get("/api/trf/pagos")
def api_trf_pagos(
    tribunal: str | None = None,
    proposta: int | None = None,
    min_valor: float | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = PAGE_DEFAULT,
):
    page, page_size = clamp_page(page, page_size)
    clauses = []
    params: list[Any] = []
    if tribunal:
        clauses.append("tribunal = ?")
        params.append(tribunal.upper())
    if proposta is not None:
        clauses.append("proposta = ?")
        params.append(proposta)
    if min_valor is not None:
        clauses.append("valor_pago >= ?")
        params.append(min_valor)
    if q:
        clauses.append(
            "(numero_precatorio LIKE ? OR cpf_cnpj_parcial LIKE ? OR base_legal LIKE ?)"
        )
        pat = like(q)
        params.extend([pat] * 3)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size
    with closing(connect()) as con:
        total = con.execute(f"SELECT COUNT(*) FROM trf_pagos {where}", params).fetchone()[0]
        soma = con.execute(f"SELECT COALESCE(SUM(valor_pago),0) FROM trf_pagos {where}", params).fetchone()[0]
        rows = con.execute(
            f"""SELECT tribunal, ordem, proposta, base_legal, numero_precatorio, cpf_cnpj_parcial,
                       data_autuacao, atualizado_ate, parcela_devida, valor_original_pago,
                       data_pagamento, valor_pago
                FROM trf_pagos {where}
                ORDER BY proposta DESC, ordem ASC
                LIMIT ? OFFSET ?""",
            [*params, page_size, offset],
        ).fetchall()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 0,
        "soma_valor_pago": soma,
        "rows": rows_to_dicts(rows),
    }


@app.get("/api/trf/mapas")
def api_trf_mapas(
    tribunal: str | None = None,
    uf: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = PAGE_DEFAULT,
):
    page, page_size = clamp_page(page, page_size)
    clauses = []
    params: list[Any] = []
    if tribunal:
        clauses.append("tribunal = ?")
        params.append(tribunal.upper())
    if uf:
        clauses.append("uf = ?")
        params.append(uf.upper())
    if q:
        clauses.append("(nome_entidade LIKE ? OR cnpj LIKE ?)")
        pat = like(q)
        params.extend([pat, pat])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size
    with closing(connect()) as con:
        total = con.execute(f"SELECT COUNT(*) FROM trf_mapas {where}", params).fetchone()[0]
        soma = con.execute(
            f"SELECT COALESCE(SUM(pago_no_ano),0), COALESCE(SUM(saldo_devedor),0) FROM trf_mapas {where}",
            params,
        ).fetchone()
        rows = con.execute(
            f"""SELECT tribunal, ano, esfera, uf, regime, tipo_entidade, cnpj, nome_entidade,
                       expedidos_ate_ano_anterior, pago_no_ano, saldo_devedor, expedidos_no_ano
                FROM trf_mapas {where}
                ORDER BY COALESCE(saldo_devedor, pago_no_ano) DESC
                LIMIT ? OFFSET ?""",
            [*params, page_size, offset],
        ).fetchall()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 0,
        "soma_pago_no_ano": soma[0],
        "soma_saldo_devedor": soma[1],
        "rows": rows_to_dicts(rows),
    }


@app.get("/api/trf/extra")
def api_trf_extra(
    q: str | None = None,
    page: int = 1,
    page_size: int = PAGE_DEFAULT,
):
    page, page_size = clamp_page(page, page_size)
    clauses = []
    params: list[Any] = []
    if q:
        clauses.append("(entidade_devedora LIKE ? OR numero_precatorio LIKE ? OR natureza LIKE ?)")
        pat = like(q)
        params.extend([pat] * 3)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size
    with closing(connect()) as con:
        total = con.execute(f"SELECT COUNT(*) FROM trf2_extra {where}", params).fetchone()[0]
        soma = con.execute(f"SELECT COALESCE(SUM(valor_depositado),0) FROM trf2_extra {where}", params).fetchone()[0]
        rows = con.execute(
            f"""SELECT entidade_devedora, numero_precatorio, proposta, valor_depositado,
                       parcela, natureza, data_deposito
                FROM trf2_extra {where}
                ORDER BY valor_depositado DESC
                LIMIT ? OFFSET ?""",
            [*params, page_size, offset],
        ).fetchall()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 0,
        "soma_valor_depositado": soma,
        "rows": rows_to_dicts(rows),
    }


def stream_csv(filename: str, headers: list[str], iterator):
    def gen():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        for row in iterator:
            writer.writerow([row[h] if not isinstance(row, (list, tuple)) else row[i] if False else row[h] for h in headers] if not isinstance(row, sqlite3.Row) else [row[h] for h in headers])
            data = buf.getvalue()
            if data:
                yield data
                buf.seek(0)
                buf.truncate(0)

    return StreamingResponse(
        gen(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/download/siop.csv")
def download_siop(
    tribunal: str | None = None,
    uo: str | None = None,
    nfgc: str | None = None,
    min_valor: float | None = None,
    max_valor: float | None = None,
    q: str | None = None,
):
    headers = [
        "chave", "exercicio", "nome_tribunal", "tribunal_expedidor", "data_ajuizamento",
        "data_autuacao", "tributario", "nome_uo", "tipo_causa", "valor_original", "fundef",
        "anos_decorridos", "class_tempo", "class_tribunais", "class_nfgc", "valor_atualizado",
        "faixa_valor",
    ]
    where, params = siop_where(tribunal, uo, nfgc, min_valor, max_valor, q)
    con = connect()

    def iterator():
        try:
            cur = con.execute(
                f"SELECT {', '.join(headers)} FROM siop {where} ORDER BY valor_atualizado DESC",
                params,
            )
            while True:
                chunk = cur.fetchmany(1000)
                if not chunk:
                    break
                for row in chunk:
                    yield row
        finally:
            con.close()

    return stream_csv("siop_expedidos_2026.csv", headers, iterator())


@app.get("/api/download/trf_pagos.csv")
def download_pagos(tribunal: str | None = None, proposta: int | None = None, q: str | None = None, min_valor: float | None = None):
    headers = [
        "tribunal", "ordem", "proposta", "base_legal", "numero_precatorio", "cpf_cnpj_parcial",
        "data_autuacao", "atualizado_ate", "parcela_devida", "valor_original_pago",
        "data_pagamento", "valor_pago",
    ]
    clauses, params = [], []
    if tribunal:
        clauses.append("tribunal = ?")
        params.append(tribunal.upper())
    if proposta is not None:
        clauses.append("proposta = ?")
        params.append(proposta)
    if min_valor is not None:
        clauses.append("valor_pago >= ?")
        params.append(min_valor)
    if q:
        clauses.append("(numero_precatorio LIKE ? OR cpf_cnpj_parcial LIKE ? OR base_legal LIKE ?)")
        pat = like(q)
        params.extend([pat] * 3)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    con = connect()

    def iterator():
        try:
            cur = con.execute(f"SELECT {', '.join(headers)} FROM trf_pagos {where} ORDER BY tribunal, proposta, ordem", params)
            while True:
                chunk = cur.fetchmany(1000)
                if not chunk:
                    break
                yield from chunk
        finally:
            con.close()

    return stream_csv("trf_pagos.csv", headers, iterator())


@app.get("/api/download/trf_mapas.csv")
def download_mapas(tribunal: str | None = None, q: str | None = None):
    headers = [
        "tribunal", "ano", "esfera", "uf", "regime", "tipo_entidade", "cnpj", "nome_entidade",
        "expedidos_ate_ano_anterior", "pago_no_ano", "saldo_devedor", "expedidos_no_ano",
    ]
    clauses, params = [], []
    if tribunal:
        clauses.append("tribunal = ?")
        params.append(tribunal.upper())
    if q:
        clauses.append("(nome_entidade LIKE ? OR cnpj LIKE ?)")
        pat = like(q)
        params.extend([pat, pat])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    con = connect()

    def iterator():
        try:
            cur = con.execute(f"SELECT {', '.join(headers)} FROM trf_mapas {where}", params)
            yield from cur
        finally:
            con.close()

    return stream_csv("trf_mapas.csv", headers, iterator())


@app.get("/{path:path}")
def spa_fallback(path: str):
    # Keep deep links like /#bases working; unknown files 404.
    candidate = STATIC / path
    if candidate.is_file() and candidate.resolve().is_relative_to(STATIC.resolve()):
        return FileResponse(candidate)
    return JSONResponse({"detail": "Não encontrado"}, status_code=404)
