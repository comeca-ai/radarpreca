#!/usr/bin/env python3
"""Compact official public sources into a single SQLite database."""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

POC = Path("/workspace/precatorios/poc")
OUT_DIR = Path("/workspace/radar-precatorio/data")
OUT_DB = OUT_DIR / "precatorios.sqlite"
MANIFEST = OUT_DIR / "manifest.json"
TESTED = "12/11/2026"

MONEY_RE = re.compile(r"[^\d,.-]")


def parse_date(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if hasattr(val, "strftime"):
        try:
            return val.strftime("%Y-%m-%d")
        except Exception:
            return None
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none", "nat"}:
        return None
    s = s.replace(" 00:00:00,000", "").replace(" 00:00:00.000", "").replace(" 00:00:00", "")
    # 15/04/2022 19:05 or 15/04/2022
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return s[:10]
    # abr/23, dez/23
    months = {
        "jan": "01", "fev": "02", "mar": "03", "abr": "04", "mai": "05", "jun": "06",
        "jul": "07", "ago": "08", "set": "09", "out": "10", "nov": "11", "dez": "12",
    }
    m = re.match(r"([a-z]{3})/(\d{2})$", s.lower())
    if m:
        mo, yy = m.groups()
        if mo in months:
            year = 2000 + int(yy)
            return f"{year}-{months[mo]}-01"
    return s[:19] if s else None


def parse_money(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none", "-", "r$ -", "r$ -   "}:
        return None
    s = s.replace("R$", "").replace("\xa0", " ").strip()
    if s in {"-", "–", "—"}:
        return None
    # 110.649,95 or 3.735.767.318,00
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(" ", "")
    s = MONEY_RE.sub("", s)
    if s in {"", ".", "-", "-."}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def clean_text(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none"}:
        return None
    return s


def mask_doc(val):
    """Keep already-partial documents; never expand or invent digits."""
    s = clean_text(val)
    if not s:
        return None
    if "*" in s:
        return s
    digits = re.sub(r"\D", "", s)
    # Public entity CNPJ in official mapas may be complete; keep as published.
    # Beneficiary CPF/CNPJ in payment lists should already be partial.
    if len(digits) == 11 and "*" not in s:
        return digits[:3] + "********"
    return s


def connect():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if OUT_DB.exists():
        OUT_DB.unlink()
    con = sqlite3.connect(OUT_DB)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA temp_store=MEMORY")
    return con


def load_siop(con):
    path = POC / "dados_abertos" / "siop_expedidos_2026.csv"
    print("Loading SIOP", path)
    df = pd.read_csv(
        path,
        sep=";",
        encoding="utf-8-sig",
        decimal=",",
        dtype=str,
        low_memory=False,
    )
    df.columns = [c.strip() for c in df.columns]
    rename = {
        "Chave": "chave",
        "Exercício": "exercicio",
        "Código do Tribunal": "cod_tribunal",
        "Nome do Tribunal": "nome_tribunal",
        "Tribunal Expedidor": "tribunal_expedidor",
        "Data de Ajuizamento da Ação Originária": "data_ajuizamento",
        "Data da Autuação": "data_autuacao",
        "Tipo de Despesa": "tipo_despesa",
        "Tributário": "tributario",
        "Código da UO Executada": "cod_uo",
        "Nome da UO Executada": "nome_uo",
        "Natureza de Despesa": "natureza_despesa",
        "Tipo de Causa": "tipo_causa",
        "Valor Original do Precatório": "valor_original",
        "Fundef": "fundef",
        "Anos_Decorridos": "anos_decorridos",
        "Class_Tempo": "class_tempo",
        "Class_Tribunais": "class_tribunais",
        "Class_NFGC": "class_nfgc",
        "DataInicio": "data_inicio",
        "DataFim": "data_fim",
        "IndiceAtualizacao": "indice_atualizacao",
        "Valor Atualizado": "valor_atualizado",
        "FaixaValor": "faixa_valor",
    }
    df = df.rename(columns=rename)
    for col in ("data_ajuizamento", "data_autuacao", "data_inicio", "data_fim"):
        df[col] = df[col].map(parse_date)
    for col in ("valor_original", "valor_atualizado", "indice_atualizacao", "anos_decorridos"):
        df[col] = pd.to_numeric(df[col].str.replace(",", ".", regex=False), errors="coerce")
    for col in ("exercicio", "cod_tribunal", "cod_uo", "tipo_despesa", "natureza_despesa"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(lambda x: None if (isinstance(x, str) and x.strip() == "") else (x if pd.notna(x) else None))
    con.execute(
        """
        CREATE TABLE siop (
            chave TEXT PRIMARY KEY,
            exercicio INTEGER,
            cod_tribunal INTEGER,
            nome_tribunal TEXT,
            tribunal_expedidor TEXT,
            data_ajuizamento TEXT,
            data_autuacao TEXT,
            tipo_despesa INTEGER,
            tributario TEXT,
            cod_uo INTEGER,
            nome_uo TEXT,
            natureza_despesa INTEGER,
            tipo_causa TEXT,
            valor_original REAL,
            fundef TEXT,
            anos_decorridos REAL,
            class_tempo TEXT,
            class_tribunais TEXT,
            class_nfgc TEXT,
            data_inicio TEXT,
            data_fim TEXT,
            indice_atualizacao REAL,
            valor_atualizado REAL,
            faixa_valor TEXT
        )
        """
    )
    df.to_sql("siop", con, if_exists="append", index=False)
    con.execute("CREATE INDEX idx_siop_tribunal ON siop(nome_tribunal)")
    con.execute("CREATE INDEX idx_siop_uo ON siop(nome_uo)")
    con.execute("CREATE INDEX idx_siop_nfgc ON siop(class_nfgc)")
    con.execute("CREATE INDEX idx_siop_valor ON siop(valor_atualizado)")
    con.execute("CREATE INDEX idx_siop_faixa ON siop(faixa_valor)")
    n = con.execute("SELECT COUNT(*) FROM siop").fetchone()[0]
    soma = con.execute("SELECT SUM(valor_atualizado) FROM siop").fetchone()[0]
    print(f"  SIOP rows={n} sum_atu={soma}")
    return n, soma


def _read_csv_skip_notes(path, encoding="latin-1", sep=";"):
    raw = Path(path).read_bytes()
    for enc in (encoding, "utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if "Nº de Ordem" in line or "N° de Ordem" in line or "Numero do Precat" in line:
            header_idx = i
            break
    if header_idx is None:
        raise RuntimeError(f"header not found in {path}")
    # rebuild as csv from header
    from io import StringIO
    buf = StringIO("\n".join(lines[header_idx:]))
    df = pd.read_csv(buf, sep=sep, dtype=str, encoding=None)
    df.columns = [c.strip() for c in df.columns]
    # drop empty unnamed
    df = df.loc[:, [c for c in df.columns if c and not c.startswith("Unnamed")]]
    return df


def normalize_pagos(df, tribunal):
    df = df.drop(columns=[c for c in df.columns if not str(c).strip()], errors="ignore")
    colmap = {}
    for c in df.columns:
        k = re.sub(r"\s+", " ", str(c)).strip().lower()
        if k.startswith("n") and "ordem cronol" in k:
            colmap[c] = "ordem"
        elif k == "proposta":
            colmap[c] = "proposta"
        elif "base legal" in k:
            colmap[c] = "base_legal"
        elif "precat" in k and "n" in k[:3]:
            colmap[c] = "numero_precatorio"
        elif "cpf" in k or "cnpj" in k:
            colmap[c] = "cpf_cnpj_parcial"
        elif "autua" in k:
            colmap[c] = "data_autuacao"
        elif "atualizado" in k:
            colmap[c] = "atualizado_ate"
        elif "parcela devida" in k:
            colmap[c] = "parcela_devida"
        elif "valor original" in k:
            colmap[c] = "valor_original_pago"
        elif "data pagamento" in k or "data de pagamento" in k:
            colmap[c] = "data_pagamento"
        elif "valor pago" in k:
            colmap[c] = "valor_pago"
    df = df.rename(columns=colmap)
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()].copy()
    keep = [
        "ordem", "proposta", "base_legal", "numero_precatorio", "cpf_cnpj_parcial",
        "data_autuacao", "atualizado_ate", "parcela_devida", "valor_original_pago",
        "data_pagamento", "valor_pago",
    ]
    for c in keep:
        if c not in df.columns:
            df[c] = None
        elif not isinstance(df[c], pd.Series):
            df[c] = df[c].iloc[:, 0]
    df = df[keep].copy()
    df["tribunal"] = tribunal
    df["cpf_cnpj_parcial"] = df["cpf_cnpj_parcial"].map(mask_doc)
    for c in ("data_autuacao", "atualizado_ate", "data_pagamento"):
        df[c] = df[c].map(parse_date)
    for c in ("parcela_devida", "valor_original_pago", "valor_pago"):
        df[c] = df[c].map(parse_money)
    df["ordem"] = pd.to_numeric(df["ordem"], errors="coerce").astype("Int64")
    df["proposta"] = pd.to_numeric(df["proposta"], errors="coerce").astype("Int64")
    df = df[df["numero_precatorio"].notna() & (df["numero_precatorio"].astype(str).str.strip() != "")]
    return df


def load_trf_pagos(con):
    print("Loading TRF2 pagos 2024")
    df2 = _read_csv_skip_notes(POC / "trf" / "trf2_lista_ordem_cronologica_pagos_2024.csv")
    df2 = normalize_pagos(df2, "TRF2")
    print("Loading TRF4 pagos 2022-2025 xlsx")
    df4 = pd.read_excel(
        POC / "trf" / "trf4_precatorios_pagos_ordem_cronologica_2022-2025.xlsx",
        dtype=str,
    )
    df4.columns = [c.strip() for c in df4.columns]
    df4 = normalize_pagos(df4, "TRF4")
    df = pd.concat([df2, df4], ignore_index=True)
    con.execute(
        """
        CREATE TABLE trf_pagos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tribunal TEXT,
            ordem INTEGER,
            proposta INTEGER,
            base_legal TEXT,
            numero_precatorio TEXT,
            cpf_cnpj_parcial TEXT,
            data_autuacao TEXT,
            atualizado_ate TEXT,
            parcela_devida REAL,
            valor_original_pago REAL,
            data_pagamento TEXT,
            valor_pago REAL
        )
        """
    )
    df.to_sql("trf_pagos", con, if_exists="append", index=False)
    con.execute("CREATE INDEX idx_pagos_trf ON trf_pagos(tribunal)")
    con.execute("CREATE INDEX idx_pagos_num ON trf_pagos(numero_precatorio)")
    con.execute("CREATE INDEX idx_pagos_valor ON trf_pagos(valor_pago)")
    con.execute("CREATE INDEX idx_pagos_prop ON trf_pagos(proposta)")
    counts = dict(con.execute("SELECT tribunal, COUNT(*) FROM trf_pagos GROUP BY tribunal"))
    print("  trf_pagos", counts)
    return counts


def load_trf2_extra(con):
    path = POC / "trf" / "trf2_pagos_extraorcamentarios_2026.csv"
    print("Loading TRF2 extra 2026")
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    lines = text.splitlines()
    header_idx = next(i for i, l in enumerate(lines) if l.startswith("ENTIDADE DEVEDORA"))
    from io import StringIO
    df = pd.read_csv(StringIO("\n".join(lines[header_idx:])), dtype=str)
    df.columns = [c.strip() for c in df.columns]
    rename = {
        "ENTIDADE DEVEDORA": "entidade_devedora",
        "PRECATÓRIO": "numero_precatorio",
        "PROPOSTA": "proposta",
        "VALOR DEPOSITADO": "valor_depositado",
        "PARCELA": "parcela",
        "NATUREZA CRÉDITO": "natureza",
        "DATA DEPÓSITO": "data_deposito",
    }
    df = df.rename(columns=rename)
    df = df[df["numero_precatorio"].notna() & (df["numero_precatorio"].astype(str).str.strip() != "")]
    df["valor_depositado"] = df["valor_depositado"].map(parse_money)
    df["proposta"] = pd.to_numeric(df["proposta"], errors="coerce").astype("Int64")
    for c in ("entidade_devedora", "numero_precatorio", "parcela", "natureza", "data_deposito"):
        df[c] = df[c].map(clean_text)
    con.execute(
        """
        CREATE TABLE trf2_extra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entidade_devedora TEXT,
            numero_precatorio TEXT,
            proposta INTEGER,
            valor_depositado REAL,
            parcela TEXT,
            natureza TEXT,
            data_deposito TEXT
        )
        """
    )
    df.to_sql("trf2_extra", con, if_exists="append", index=False)
    n = con.execute("SELECT COUNT(*) FROM trf2_extra").fetchone()[0]
    print("  trf2_extra", n)
    return n


def normalize_mapa(df, tribunal):
    colmap = {}
    for c in df.columns:
        k = re.sub(r"\s+", " ", str(c)).strip().lower()
        if k.startswith("sigla do tribunal"):
            colmap[c] = "tribunal"
        elif k.startswith("ano de refer"):
            colmap[c] = "ano"
        elif k.startswith("esfera"):
            colmap[c] = "esfera"
        elif k.startswith("sigla do estado"):
            colmap[c] = "uf"
        elif "município devedor" in k or "municipio devedor" in k:
            colmap[c] = "cod_municipio"
        elif k.startswith("regime de pagamento"):
            colmap[c] = "regime"
        elif k.startswith("tipo de entidade"):
            colmap[c] = "tipo_entidade"
        elif k.startswith("cnpj"):
            colmap[c] = "cnpj"
        elif k.startswith("nome da entidade"):
            colmap[c] = "nome_entidade"
        elif "expedidos até o ano anterior" in k or "expedidos ate o ano anterior" in k:
            colmap[c] = "expedidos_ate_ano_anterior"
        elif k.startswith("montante pago"):
            colmap[c] = "pago_no_ano"
        elif k.startswith("saldo devedor"):
            colmap[c] = "saldo_devedor"
        elif "expedidos no ano de refer" in k:
            colmap[c] = "expedidos_no_ano"
    df = df.rename(columns=colmap)
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()].copy()
    keep = [
        "tribunal", "ano", "esfera", "uf", "cod_municipio", "regime", "tipo_entidade",
        "cnpj", "nome_entidade", "expedidos_ate_ano_anterior", "pago_no_ano",
        "saldo_devedor", "expedidos_no_ano",
    ]
    for c in keep:
        if c not in df.columns:
            df[c] = None
        elif not isinstance(df[c], pd.Series):
            df[c] = df[c].iloc[:, 0]
    df = df[keep].copy()
    if tribunal:
        df["tribunal"] = df["tribunal"].fillna(tribunal)
        df["tribunal"] = df["tribunal"].map(lambda x: tribunal if not clean_text(x) else clean_text(x))
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    # entity CNPJ is published in official mapas; normalize digits only, do not invent.
    def norm_cnpj(v):
        s = clean_text(v)
        if not s:
            return None
        digits = re.sub(r"\D", "", s.split(".")[0] if s.endswith(".0") else s)
        # pandas may have read as 15461510000133.0
        if not digits:
            return None
        return digits
    df["cnpj"] = df["cnpj"].map(norm_cnpj)
    for c in ("expedidos_ate_ano_anterior", "pago_no_ano", "saldo_devedor", "expedidos_no_ano"):
        df[c] = df[c].map(parse_money)
    for c in ("esfera", "uf", "cod_municipio", "regime", "tipo_entidade", "nome_entidade"):
        df[c] = df[c].map(clean_text)
    # drop fully empty names and values
    df = df[df["nome_entidade"].notna() | df["pago_no_ano"].notna() | df["expedidos_no_ano"].notna()]
    return df


def load_mapas(con):
    print("Loading mapas")
    frames = []
    # TRF2 csv is semicolon latin/utf with R$ values
    p2 = POC / "trf" / "trf2_mapa_anual_divida_2025.csv"
    def read_csv_any(path, **kwargs):
        raw = Path(path).read_bytes()
        last = None
        for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                return pd.read_csv(path, dtype=str, encoding=enc, **kwargs)
            except Exception as e:
                last = e
        raise last

    df2 = read_csv_any(p2, sep=";")
    frames.append(normalize_mapa(df2, "TRF2"))
    p4 = POC / "trf" / "trf4_mapa_de_precatorios_2025.csv"
    df4 = read_csv_any(p4)
    frames.append(normalize_mapa(df4, "TRF4"))
    p5 = POC / "trf" / "trf5_mapa_anual_divida_2025.csv"
    df5 = read_csv_any(p5)
    frames.append(normalize_mapa(df5, "TRF5"))
    df = pd.concat(frames, ignore_index=True)
    con.execute(
        """
        CREATE TABLE trf_mapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tribunal TEXT,
            ano INTEGER,
            esfera TEXT,
            uf TEXT,
            cod_municipio TEXT,
            regime TEXT,
            tipo_entidade TEXT,
            cnpj TEXT,
            nome_entidade TEXT,
            expedidos_ate_ano_anterior REAL,
            pago_no_ano REAL,
            saldo_devedor REAL,
            expedidos_no_ano REAL
        )
        """
    )
    df.to_sql("trf_mapas", con, if_exists="append", index=False)
    con.execute("CREATE INDEX idx_mapa_trf ON trf_mapas(tribunal)")
    counts = dict(con.execute("SELECT tribunal, COUNT(*) FROM trf_mapas GROUP BY tribunal"))
    print("  mapas", counts)
    return counts


def main():
    con = connect()
    n_siop, soma_siop = load_siop(con)
    pagos = load_trf_pagos(con)
    n_extra = load_trf2_extra(con)
    mapas = load_mapas(con)
    con.execute("VACUUM")
    con.close()
    size = OUT_DB.stat().st_size
    print("DB size_mb", round(size / 1024 / 1024, 2))

    manifest = {
        "atualizado_em": TESTED,
        "fuso": "America/Sao_Paulo",
        "arquivo": "data/precatorios.sqlite",
        "tamanho_bytes": size,
        "bases": [
            {
                "id": "siop",
                "nome": "SIOP — precatórios federais expedidos para 2026",
                "tabela": "siop",
                "registros": n_siop,
                "soma_valor_atualizado": soma_siop,
                "fonte": "Secretaria de Orçamento Federal / SIOP (Ministério do Planejamento)",
                "url": "https://www.gov.br/planejamento/pt-br/assuntos/orcamento/precatorios-content/painel-precatorios/dados-abertos",
                "arquivo_origem": "expedidos_2026.csv",
                "testado_em": TESTED,
                "limites": "Não traz número do precatório, processo nem credor. O valor atualizado usa correção única pelo IPCA.",
            },
            {
                "id": "trf2_pagos",
                "nome": "TRF2 — lista de ordem cronológica (pagos, proposta 2024)",
                "tabela": "trf_pagos",
                "filtro": {"tribunal": "TRF2"},
                "registros": pagos.get("TRF2"),
                "fonte": "Tribunal Regional Federal da 2ª Região",
                "url": "https://www.trf2.jus.br/trf2/consultas-e-servicos/precatorios-federais-requisicoes-de-pequeno-valor-rpvs",
                "arquivo_origem": "lista de ordem cronológica de precatórios pagos 2024 (CSV)",
                "testado_em": TESTED,
                "limites": "Arquivo de precatórios já pagos. CPF/CNPJ do beneficiário vem parcial na origem.",
            },
            {
                "id": "trf4_pagos",
                "nome": "TRF4 — precatórios pagos na ordem cronológica (2022–2025)",
                "tabela": "trf_pagos",
                "filtro": {"tribunal": "TRF4"},
                "registros": pagos.get("TRF4"),
                "fonte": "Tribunal Regional Federal da 4ª Região",
                "url": "https://consulta.trf4.jus.br/trf4/controlador.php?acao=pagina_precatorios",
                "arquivo_origem": "precatórios pagos ordem cronológica 2022-2025 (XLSX)",
                "testado_em": TESTED,
                "limites": "Arquivo de precatórios já pagos. CPF/CNPJ do beneficiário vem parcial na origem.",
            },
            {
                "id": "trf2_extra",
                "nome": "TRF2 — pagos extraorçamentários (exercício 2026)",
                "tabela": "trf2_extra",
                "registros": n_extra,
                "fonte": "Tribunal Regional Federal da 2ª Região",
                "url": "https://www.trf2.jus.br/trf2/consultas-e-servicos/precatorios-federais-requisicoes-de-pequeno-valor-rpvs",
                "arquivo_origem": "pagos extraorçamentários 2026 (CSV)",
                "testado_em": TESTED,
            },
            {
                "id": "trf2_mapa",
                "nome": "TRF2 — mapa anual da dívida (2025)",
                "tabela": "trf_mapas",
                "filtro": {"tribunal": "TRF2"},
                "registros": mapas.get("TRF2"),
                "fonte": "Tribunal Regional Federal da 2ª Região / CNJ (mapa da dívida)",
                "url": "https://www.trf2.jus.br/trf2/consultas-e-servicos/precatorios-federais-requisicoes-de-pequeno-valor-rpvs",
                "arquivo_origem": "mapa anual da dívida 2025 (CSV)",
                "testado_em": TESTED,
            },
            {
                "id": "trf4_mapa",
                "nome": "TRF4 — mapa de precatórios (2025)",
                "tabela": "trf_mapas",
                "filtro": {"tribunal": "TRF4"},
                "registros": mapas.get("TRF4"),
                "fonte": "Tribunal Regional Federal da 4ª Região / CNJ (mapa da dívida)",
                "url": "https://consulta.trf4.jus.br/trf4/controlador.php?acao=pagina_precatorios",
                "arquivo_origem": "mapa de precatórios 2025 (CSV)",
                "testado_em": TESTED,
            },
            {
                "id": "trf5_mapa",
                "nome": "TRF5 — mapa anual da dívida (2025)",
                "tabela": "trf_mapas",
                "filtro": {"tribunal": "TRF5"},
                "registros": mapas.get("TRF5"),
                "fonte": "Tribunal Regional Federal da 5ª Região / CNJ (mapa da dívida)",
                "url": "https://www.trf5.jus.br/",
                "arquivo_origem": "mapa anual da dívida 2025 (CSV)",
                "testado_em": TESTED,
            },
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Wrote", MANIFEST)


if __name__ == "__main__":
    main()
