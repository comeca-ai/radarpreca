#!/usr/bin/env python3
"""Consulta unificada das bases públicas do Radar Precatório."""
from __future__ import annotations

import re
import sqlite3
import time
from contextlib import closing
from typing import Any

from fastapi import APIRouter, Query

PAGE_DEFAULT = 20
PAGE_MAX = 50

PRECAT_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
FONTES = {"trf4_pendentes", "pagos", "siop"}
STATUS = {"pendente", "pago", "expedido"}
NATUREZAS = {"alimentar", "comum"}

NATUREZA_PAGOS = """
CASE
  WHEN base_legal LIKE '%Não Alimentar%' OR base_legal LIKE '%Nao Alimentar%' THEN 'comum'
  WHEN base_legal LIKE '%Alimentar%' THEN 'alimentar'
  ELSE NULL
END
"""

NATUREZA_EXTRA = """
CASE
  WHEN lower(natureza) LIKE '%comum%' THEN 'comum'
  WHEN lower(natureza) LIKE '%alimentar%' THEN 'alimentar'
  ELSE NULL
END
"""

LABELS = {
    "trf4_pendentes": "TRF4 pendentes",
    "pagos": "Pagos TRF2/TRF4",
    "siop": "SIOP expedidos",
}

router = APIRouter()


def digits_only(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def mask_doc(value: str | None) -> str | None:
    """Never return a full CPF/CNPJ. Keep already-partial values as published."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if "*" in raw or "•" in raw:
        return raw
    digits = digits_only(raw)
    if len(digits) == 11:
        return digits[:3] + "********"
    if len(digits) == 14:
        return digits[:4] + "**********"
    if len(digits) >= 6:
        return digits[:3] + ("*" * (len(digits) - 3))
    if digits:
        return "*" * len(digits)
    return None


def like(term: str) -> str:
    return f"%{term.replace('%', '').replace('_', ' ').strip()}%"


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    return max(1, page), min(PAGE_MAX, max(1, page_size))


def parse_fontes(fonte: str | None) -> set[str]:
    if not fonte or not fonte.strip():
        return set(FONTES)
    out = set()
    for part in re.split(r"[,\s]+", fonte.strip().lower()):
        if part in {"trf_pagos", "trf2_pagos", "trf4_pagos", "pago"}:
            part = "pagos"
        if part in FONTES:
            out.add(part)
    return out or set(FONTES)


def ensure_indexes(db_path) -> None:
    con = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        statements = [
            "CREATE INDEX IF NOT EXISTS idx_pagos_cpf ON trf_pagos(cpf_cnpj_parcial)",
            "CREATE INDEX IF NOT EXISTS idx_extra_ent ON trf2_extra(entidade_devedora)",
            "CREATE INDEX IF NOT EXISTS idx_extra_num ON trf2_extra(numero_precatorio)",
            "CREATE INDEX IF NOT EXISTS idx_extra_valor ON trf2_extra(valor_depositado)",
            "CREATE INDEX IF NOT EXISTS idx_mapa_cnpj ON trf_mapas(cnpj)",
            "CREATE INDEX IF NOT EXISTS idx_mapa_nome ON trf_mapas(nome_entidade)",
            "CREATE INDEX IF NOT EXISTS idx_siop_chave ON siop(chave)",
        ]
        for sql in statements:
            con.execute(sql)
        con.commit()
    finally:
        con.close()


def ensure_fila(pendentes_db) -> None:
    con = sqlite3.connect(str(pendentes_db), check_same_thread=False)
    try:
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "trf4_fila" in names:
            n = con.execute("SELECT COUNT(*) FROM trf4_fila").fetchone()[0]
            p = con.execute("SELECT COUNT(*) FROM trf4_pendentes").fetchone()[0]
            if n == p and n > 0:
                return
            con.execute("DROP TABLE IF EXISTS trf4_fila")
        con.execute(
            """
            CREATE TABLE trf4_fila AS
            SELECT
              tipo_lista,
              ente_devedor,
              ordem,
              COALESCE(
                COUNT(*) OVER (
                  PARTITION BY tipo_lista, ente_devedor
                  ORDER BY ordem
                  ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                ), 0
              ) AS creditos_a_frente,
              COALESCE(
                SUM(valor) OVER (
                  PARTITION BY tipo_lista, ente_devedor
                  ORDER BY ordem
                  ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                ), 0
              ) AS valor_a_frente
            FROM trf4_pendentes
            """
        )
        con.execute(
            "CREATE UNIQUE INDEX idx_trf4_fila ON trf4_fila(tipo_lista, ente_devedor, ordem)"
        )
        con.commit()
    finally:
        con.close()


def connect_consulta(db_path, pendentes_db) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute(f"ATTACH DATABASE 'file:{pendentes_db}?mode=ro' AS pend")
    return con


def entes_por_cnpj(con: sqlite3.Connection, fragmento: str) -> list[str]:
    digits = digits_only(fragmento)
    if len(digits) < 4:
        return []
    rows = con.execute(
        """
        SELECT DISTINCT nome_entidade
        FROM trf_mapas
        WHERE cnpj IS NOT NULL
          AND replace(replace(replace(cnpj, '.', ''), '/', ''), '-', '') LIKE ?
          AND nome_entidade IS NOT NULL
          AND trim(nome_entidade) != ''
        LIMIT 50
        """,
        (f"%{digits}%",),
    ).fetchall()
    return [r[0] for r in rows if r[0]]


def fonte_enabled(fontes: set[str], name: str, status: str | None) -> bool:
    if name not in fontes:
        return False
    if status == "pendente":
        return name == "trf4_pendentes"
    if status == "pago":
        return name == "pagos"
    if status == "expedido":
        return name == "siop"
    return True


def build_consulta(
    con: sqlite3.Connection,
    *,
    q: str | None,
    fontes: set[str],
    tribunal: str | None,
    ente: str | None,
    natureza: str | None,
    min_valor: float | None,
    max_valor: float | None,
    ano: int | None,
    status: str | None,
    sort: str,
    order: str,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    q = (q or "").strip()
    ente = (ente or "").strip()
    tribunal = (tribunal or "").strip()
    natureza = (natureza or "").strip().lower() or None
    if natureza not in NATUREZAS:
        natureza = None
    status = (status or "").strip().lower() or None
    if status not in STATUS:
        status = None
    sort = "posicao" if sort == "posicao" else "valor"
    order_sql = "ASC" if order == "asc" else "DESC"

    precat = None
    if q:
        found = PRECAT_RE.findall(q)
        if found:
            precat = found[0]

    digits = digits_only(q) if q else ""
    entes_cnpj = entes_por_cnpj(con, q) if q and len(digits) >= 4 else []

    parts: list[tuple[str, list[Any]]] = []

    def add_filters(clauses: list[str], params: list[Any], valor_col: str, ano_col: str, nat_expr: str | None = None) -> None:
        if min_valor is not None:
            clauses.append(f"{valor_col} >= ?")
            params.append(min_valor)
        if max_valor is not None:
            clauses.append(f"{valor_col} <= ?")
            params.append(max_valor)
        if ano is not None:
            clauses.append(f"{ano_col} = ?")
            params.append(ano)
        if natureza and nat_expr:
            clauses.append(f"({nat_expr}) = ?")
            params.append(natureza)

    # --- TRF4 pendentes ---
    if fonte_enabled(fontes, "trf4_pendentes", status):
        clauses: list[str] = []
        params: list[Any] = []
        if tribunal and tribunal.upper() not in {"TRF4", "TODAS"}:
            clauses.append("1 = 0")
        if ente:
            clauses.append("p.ente_devedor LIKE ?")
            params.append(like(ente))
        if q:
            ors = ["p.numero_precatorio LIKE ?", "p.ente_devedor LIKE ?", "p.cpf_cnpj_parcial LIKE ?"]
            params.extend([like(precat or q), like(q), like(q)])
            if digits:
                ors.append("p.cpf_cnpj_parcial LIKE ?")
                params.append(like(digits[:8]))
            if entes_cnpj:
                ors.append("p.ente_devedor IN (%s)" % ",".join("?" * len(entes_cnpj)))
                params.extend(entes_cnpj)
            clauses.append("(" + " OR ".join(ors) + ")")
        add_filters(clauses, params, "p.valor", "p.ano_orcamento", "p.natureza")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        parts.append(
            (
                f"""
                SELECT
                  'trf4_pendentes' AS fonte,
                  p.tribunal AS tribunal,
                  p.ente_devedor AS ente_devedor,
                  p.numero_precatorio AS numero_precatorio,
                  p.natureza AS natureza,
                  p.valor AS valor,
                  p.ano_orcamento AS ano_orcamento,
                  p.situacao AS status,
                  p.ordem AS ordem,
                  f.creditos_a_frente AS creditos_a_frente,
                  f.valor_a_frente AS valor_a_frente,
                  p.cpf_cnpj_parcial AS cpf_cnpj_parcial,
                  p.tipo_lista AS tipo_lista,
                  NULL AS chave,
                  p.prioridade AS detalhe
                FROM pend.trf4_pendentes p
                LEFT JOIN pend.trf4_fila f
                  ON f.tipo_lista = p.tipo_lista
                 AND f.ente_devedor = p.ente_devedor
                 AND f.ordem = p.ordem
                {where}
                """,
                params,
            )
        )

    # --- Pagos TRF2/TRF4 ---
    if fonte_enabled(fontes, "pagos", status):
        clauses = []
        params = []
        if tribunal:
            t = tribunal.upper()
            if t in {"TRF2", "TRF4"}:
                clauses.append("tribunal = ?")
                params.append(t)
        if ente:
            # Listas de pagos federais não trazem o nome do ente.
            clauses.append("1 = 0")
        if q:
            ors = ["numero_precatorio LIKE ?", "cpf_cnpj_parcial LIKE ?"]
            params.extend([like(precat or q), like(q)])
            if digits:
                ors.append("cpf_cnpj_parcial LIKE ?")
                params.append(like(digits[:8]))
            clauses.append("(" + " OR ".join(ors) + ")")
        add_filters(clauses, params, "valor_pago", "proposta", NATUREZA_PAGOS)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        parts.append(
            (
                f"""
                SELECT
                  'pagos' AS fonte,
                  tribunal AS tribunal,
                  NULL AS ente_devedor,
                  numero_precatorio AS numero_precatorio,
                  {NATUREZA_PAGOS} AS natureza,
                  valor_pago AS valor,
                  proposta AS ano_orcamento,
                  'pago' AS status,
                  ordem AS ordem,
                  NULL AS creditos_a_frente,
                  NULL AS valor_a_frente,
                  cpf_cnpj_parcial AS cpf_cnpj_parcial,
                  NULL AS tipo_lista,
                  NULL AS chave,
                  base_legal AS detalhe
                FROM trf_pagos
                {where}
                """,
                params,
            )
        )

        # TRF2 extraorçamentários pagos
        clauses = []
        params = []
        if tribunal and tribunal.upper() not in {"TRF2", "TODAS"}:
            clauses.append("1 = 0")
        if ente:
            clauses.append("entidade_devedora LIKE ?")
            params.append(like(ente))
        if q:
            ors = ["numero_precatorio LIKE ?", "entidade_devedora LIKE ?"]
            params.extend([like(precat or q), like(q)])
            if entes_cnpj:
                ors.append("entidade_devedora IN (%s)" % ",".join("?" * len(entes_cnpj)))
                params.extend(entes_cnpj)
            clauses.append("(" + " OR ".join(ors) + ")")
        add_filters(clauses, params, "valor_depositado", "proposta", NATUREZA_EXTRA)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        parts.append(
            (
                f"""
                SELECT
                  'pagos' AS fonte,
                  'TRF2' AS tribunal,
                  entidade_devedora AS ente_devedor,
                  numero_precatorio AS numero_precatorio,
                  {NATUREZA_EXTRA} AS natureza,
                  valor_depositado AS valor,
                  proposta AS ano_orcamento,
                  'pago' AS status,
                  NULL AS ordem,
                  NULL AS creditos_a_frente,
                  NULL AS valor_a_frente,
                  NULL AS cpf_cnpj_parcial,
                  'extra' AS tipo_lista,
                  NULL AS chave,
                  parcela AS detalhe
                FROM trf2_extra
                {where}
                """,
                params,
            )
        )

    # --- SIOP expedidos ---
    if fonte_enabled(fontes, "siop", status) and not natureza and not (q and precat and not ente):
        # SIOP não tem número de precatório nem natureza alimentar/comum.
        # Se a busca é claramente um número de precatório (sem outro filtro de ente),
        # pular o SIOP evita um scan inútil.
        clauses = []
        params = []
        skip_siop = bool(q and precat and not ente)
        if not skip_siop:
            if tribunal:
                clauses.append("(nome_tribunal LIKE ? OR tribunal_expedidor LIKE ?)")
                params.extend([like(tribunal), like(tribunal)])
            if ente:
                clauses.append("nome_uo LIKE ?")
                params.append(like(ente))
            if q and not precat:
                ors = ["nome_uo LIKE ?", "chave LIKE ?", "tipo_causa LIKE ?", "nome_tribunal LIKE ?"]
                params.extend([like(q), like(q), like(q), like(q)])
                if entes_cnpj:
                    ors.append("nome_uo IN (%s)" % ",".join("?" * len(entes_cnpj)))
                    params.extend(entes_cnpj)
                clauses.append("(" + " OR ".join(ors) + ")")
            elif q and precat and ente:
                clauses.append("nome_uo LIKE ?")
                params.append(like(ente))
            add_filters(clauses, params, "valor_atualizado", "exercicio", None)
            where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
            parts.append(
                (
                    f"""
                    SELECT
                      'siop' AS fonte,
                      nome_tribunal AS tribunal,
                      nome_uo AS ente_devedor,
                      NULL AS numero_precatorio,
                      NULL AS natureza,
                      valor_atualizado AS valor,
                      exercicio AS ano_orcamento,
                      'expedido' AS status,
                      NULL AS ordem,
                      NULL AS creditos_a_frente,
                      NULL AS valor_a_frente,
                      NULL AS cpf_cnpj_parcial,
                      NULL AS tipo_lista,
                      chave AS chave,
                      tipo_causa AS detalhe
                    FROM siop
                    {where}
                    """,
                    params,
                )
            )

    if not parts:
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "pages": 0,
            "soma_valor": 0,
            "rows": [],
        }

    union = " UNION ALL ".join(sql for sql, _ in parts)
    all_params: list[Any] = []
    for _, p in parts:
        all_params.extend(p)

    count_sql = f"SELECT COUNT(*) AS n, COALESCE(SUM(valor), 0) AS soma FROM ({union}) AS u"
    total, soma = con.execute(count_sql, all_params).fetchone()

    if sort == "posicao":
        order_by = f"""
            CASE WHEN fonte = 'trf4_pendentes' THEN 0 ELSE 1 END ASC,
            ordem {order_sql} NULLS LAST,
            valor DESC
        """
    else:
        order_by = f"valor {order_sql} NULLS LAST, ordem ASC"

    offset = (page - 1) * page_size
    list_sql = f"""
        SELECT * FROM ({union}) AS u
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
    """
    rows = con.execute(list_sql, [*all_params, page_size, offset]).fetchall()

    out_rows = []
    for r in rows:
        item = {k: r[k] for k in r.keys()}
        item["fonte_label"] = LABELS.get(item.get("fonte") or "", item.get("fonte"))
        item["cpf_cnpj_parcial"] = mask_doc(item.get("cpf_cnpj_parcial"))
        # never leak unexpected personal fields
        item.pop("data_nascimento", None)
        out_rows.append(item)

    return {
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
        "pages": (int(total or 0) + page_size - 1) // page_size if page_size else 0,
        "soma_valor": float(soma or 0),
        "rows": out_rows,
    }


def register(app, db_path_getter, pendentes_db_getter) -> None:
    @app.get("/api/consulta")
    def api_consulta(
        q: str | None = None,
        fonte: str | None = None,
        tribunal: str | None = None,
        ente: str | None = None,
        natureza: str | None = None,
        min_valor: float | None = Query(default=None),
        max_valor: float | None = Query(default=None),
        ano_orcamento: int | None = Query(default=None),
        status: str | None = None,
        sort: str = "valor",
        order: str = "desc",
        page: int = 1,
        page_size: int = PAGE_DEFAULT,
    ):
        page, page_size = clamp_page(page, page_size)
        t0 = time.perf_counter()
        fontes = parse_fontes(fonte)
        with closing(connect_consulta(db_path_getter(), pendentes_db_getter())) as con:
            payload = build_consulta(
                con,
                q=q,
                fontes=fontes,
                tribunal=tribunal,
                ente=ente,
                natureza=natureza,
                min_valor=min_valor,
                max_valor=max_valor,
                ano=ano_orcamento,
                status=status,
                sort=sort,
                order=order,
                page=page,
                page_size=page_size,
            )
        payload["ms"] = int((time.perf_counter() - t0) * 1000)
        payload["fontes"] = sorted(fontes)
        return payload
