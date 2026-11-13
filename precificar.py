#!/usr/bin/env python3
"""Calculadora de precificação v0: prefill a partir das bases e fórmula explícita.

Não é laudo, parecer ou recomendação de investimento. Números só saem das
bases quando há casamento claro de fonte; o restante é hipótese do usuário.
"""
from __future__ import annotations

import math
import re
import sqlite3
import unicodedata
from contextlib import closing
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Query
from fastapi.responses import JSONResponse

AVISO_V0 = (
    "Esta é uma calculadora experimental (v0). Não é laudo, não é parecer "
    "e não é recomendação de investimento. Os parâmetros são hipóteses a validar."
)

# Presets e defaults: hipóteses desta v0, não dados de mercado nem score do ente.
HIPOTESES_PADRAO = {
    "correcao_aa": 0.0,
    "correcao_label": (
        "Hipótese inicial: 0% a.a. (sem correção). Não é a Selic nem a taxa "
        "oficial de atualização. Informe a taxa que você quer usar."
    ),
    "p_presets": {
        "baixo": 0.05,
        "medio": 0.15,
        "alto": 0.35,
        "aviso": (
            "Presets ilustrativos desta v0. Não são probabilidade histórica, "
            "rating nem score do ente."
        ),
    },
    "p_padrao": 0.15,
    "p_padrao_label": "Hipótese inicial: preset médio (15%).",
    "r_aa": 0.10,
    "r_label": (
        "Hipótese inicial: 10% a.a. de retorno exigido. Não é taxa de mercado medida."
    ),
}

CENARIOS_REGRA = {
    "aviso": (
        "Os cenários otimista e pessimista só deslocam T, p e r por fatores "
        "fixos desta v0. Não são um modelo estatístico."
    ),
    "otimista": {"t_fator": 0.7, "p_fator": 0.5, "r_delta": -0.02},
    "base": {"t_fator": 1.0, "p_fator": 1.0, "r_delta": 0.0},
    "pessimista": {"t_fator": 1.5, "p_fator": 1.5, "r_delta": 0.03, "p_teto": 0.95},
}

ENTE_FEDERAL_AGREGADO = "Fazenda Pública Federal (União, autarquias e fundações)"
MAPA_FEDERAL_CONTEXTO = (
    "UNIÃO FEDERAL",
    "INSTITUTO NACIONAL DO SEGURO SOCIAL - INSS",
)
TZ_SP = ZoneInfo("America/Sao_Paulo")
# T mínimo quando o prazo constitucional do exercício já venceu.
# Não usamos zero: prazo vencido não é pagamento imediato. Hipótese desta v0.
T_MINIMO_ATRASADO = 0.25
DIAS_POR_ANO = 365.25


def norm_name(s: str | None) -> str:
    if not s:
        return ""
    text = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    text = text.upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def money_round(v: float | None) -> float | None:
    if v is None:
        return None
    return round(float(v), 2)


def hoje_sp() -> date:
    return datetime.now(TZ_SP).date()


def t_prazo_orcamentario(ano: int, hoje: date | None = None) -> dict:
    """T até 31/dez do ano orçamentário/proposta (hipótese, CF art. 100 § 5º).

    Se o campo é o ano da proposta/orçamento, o prazo de pagamento federal
    é o último dia desse ano. Se essa data já passou, T = T_MINIMO_ATRASADO.
    """
    hoje = hoje or hoje_sp()
    prazo = date(int(ano), 12, 31)
    base = {
        "ano": int(ano),
        "prazo": prazo.isoformat(),
        "prazo_br": prazo.strftime("%d/%m/%Y"),
        "hoje": hoje.isoformat(),
        "hoje_br": hoje.strftime("%d/%m/%Y"),
    }
    if prazo < hoje:
        base.update({
            "t": T_MINIMO_ATRASADO,
            "atrasado": True,
            "dias": (hoje - prazo).days,
        })
        return base
    dias = (prazo - hoje).days
    base.update({
        "t": dias / DIAS_POR_ANO,
        "atrasado": False,
        "dias": dias,
    })
    return base


def calcular(
    valor_atual: float,
    t: float,
    p: float,
    r: float,
    correcao_aa: float = 0.0,
    ir: float = 0.0,
    honorarios: float = 0.0,
) -> dict[str, Any]:
    """Aplica a fórmula v0. Taxas em decimal (0.10 = 10%). T em anos."""
    if valor_atual < 0:
        raise ValueError("valor_atual não pode ser negativo")
    if t < 0:
        raise ValueError("T não pode ser negativo")
    if not (0 <= p <= 1):
        raise ValueError("p deve estar entre 0 e 1")
    if r <= -1:
        raise ValueError("r deve ser maior que -100%")
    if correcao_aa <= -1:
        raise ValueError("correção deve ser maior que -100%")
    descontos = ir + honorarios
    if descontos >= 1:
        raise ValueError("IR + honorários não podem somar 100% ou mais")
    if ir < 0 or honorarios < 0:
        raise ValueError("descontos não podem ser negativos")

    valor_corrigido = valor_atual * ((1 + correcao_aa) ** t)
    valor_no_pagamento = valor_corrigido * (1 - descontos)
    fator_desconto = (1 + r) ** t
    preco = valor_no_pagamento * (1 - p) / fator_desconto if fator_desconto else 0.0
    if valor_atual == 0:
        desagio = None
    else:
        desagio = 1.0 - (preco / valor_atual)

    return {
        "valor_atual": money_round(valor_atual),
        "t": t,
        "p": p,
        "r": r,
        "correcao_aa": correcao_aa,
        "ir": ir,
        "honorarios": honorarios,
        "descontos": descontos,
        "valor_corrigido": money_round(valor_corrigido),
        "valor_no_pagamento": money_round(valor_no_pagamento),
        "fator_desconto": fator_desconto,
        "preco": money_round(preco),
        "desagio": None if desagio is None else desagio,
        "agio": bool(desagio is not None and desagio < 0),
    }


def aplicar_cenario(t: float, p: float, r: float, nome: str) -> tuple[float, float, float]:
    regra = CENARIOS_REGRA[nome]
    t2 = max(0.0, t * regra["t_fator"])
    p2 = p * regra["p_fator"]
    teto = regra.get("p_teto", 1.0)
    p2 = min(teto, max(0.0, p2))
    r2 = r + regra["r_delta"]
    if r2 <= -0.999:
        r2 = -0.999
    return t2, p2, r2


def calcular_cenarios(
    valor_atual: float,
    t: float,
    p: float,
    r: float,
    correcao_aa: float = 0.0,
    ir: float = 0.0,
    honorarios: float = 0.0,
) -> dict[str, Any]:
    out: dict[str, Any] = {"cenarios": {}, "faixa_desagio": None, "aviso": CENARIOS_REGRA["aviso"]}
    desagios = []
    for nome in ("otimista", "base", "pessimista"):
        t2, p2, r2 = aplicar_cenario(t, p, r, nome)
        calc = calcular(valor_atual, t2, p2, r2, correcao_aa, ir, honorarios)
        calc["nome"] = nome
        out["cenarios"][nome] = calc
        if calc["desagio"] is not None:
            desagios.append(calc["desagio"])
    if desagios:
        out["faixa_desagio"] = {"min": min(desagios), "max": max(desagios)}
    return out


def _connect(db_path, pendentes_db) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute(f"ATTACH DATABASE 'file:{pendentes_db}?mode=ro' AS pend")
    return con


def _busca_credito(con: sqlite3.Connection, numero: str) -> sqlite3.Row | None:
    numero = (numero or "").strip()
    if not numero:
        return None
    row = con.execute(
        """
        SELECT
          p.numero_precatorio, p.tribunal, p.ente_devedor, p.valor, p.natureza,
          p.ordem, p.tipo_lista, p.regime, p.ano_orcamento, p.situacao,
          p.coletado_em, p.atualizado_ate, p.data_apresentacao, p.prioridade,
          f.creditos_a_frente, f.valor_a_frente
        FROM pend.trf4_pendentes p
        LEFT JOIN pend.trf4_fila f
          ON f.tipo_lista = p.tipo_lista
         AND f.ente_devedor = p.ente_devedor
         AND f.ordem = p.ordem
        WHERE p.numero_precatorio = ?
        LIMIT 1
        """,
        (numero,),
    ).fetchone()
    if row:
        return row
    # Permite busca sem pontuação, ainda assim só na coluna de número.
    compact = re.sub(r"\D", "", numero)
    if len(compact) < 8:
        return None
    return con.execute(
        """
        SELECT
          p.numero_precatorio, p.tribunal, p.ente_devedor, p.valor, p.natureza,
          p.ordem, p.tipo_lista, p.regime, p.ano_orcamento, p.situacao,
          p.coletado_em, p.atualizado_ate, p.data_apresentacao, p.prioridade,
          f.creditos_a_frente, f.valor_a_frente
        FROM pend.trf4_pendentes p
        LEFT JOIN pend.trf4_fila f
          ON f.tipo_lista = p.tipo_lista
         AND f.ente_devedor = p.ente_devedor
         AND f.ordem = p.ordem
        WHERE replace(replace(replace(p.numero_precatorio, '-', ''), '.', ''), '/', '') = ?
        LIMIT 1
        """,
        (compact,),
    ).fetchone()


def _mapa_exato(con: sqlite3.Connection, ente: str, tribunal: str | None) -> dict[str, Any] | None:
    """Casa só nome normalizado + tribunal (se houver) no ano mais recente do mapa."""
    alvo = norm_name(ente)
    if not alvo:
        return None
    rows = list(
        con.execute(
            """
            SELECT tribunal, ano, nome_entidade, cnpj, esfera, regime,
                   pago_no_ano, saldo_devedor, expedidos_no_ano
            FROM trf_mapas
            ORDER BY ano DESC
            """
        )
    )
    if not rows:
        return None
    ano_max = max(r["ano"] for r in rows if r["ano"] is not None)
    candidatos = []
    for r in rows:
        if r["ano"] != ano_max:
            continue
        if norm_name(r["nome_entidade"]) != alvo:
            continue
        if tribunal and r["tribunal"] and r["tribunal"].upper() != tribunal.upper():
            continue
        candidatos.append(r)
    if len(candidatos) != 1:
        return None
    r = candidatos[0]
    pago = r["pago_no_ano"]
    if pago is None:
        return None
    return {
        "tipo": "mapa_divida",
        "tribunal": r["tribunal"],
        "ano": r["ano"],
        "campo": "pago_no_ano",
        "nome_entidade": r["nome_entidade"],
        "cnpj": r["cnpj"],
        "esfera": r["esfera"],
        "regime_mapa": r["regime"],
        "pago_no_ano": money_round(pago),
        "saldo_devedor": money_round(r["saldo_devedor"]),
        "expedidos_no_ano": money_round(r["expedidos_no_ano"]),
        "label": (
            f"Mapa da dívida do {r['tribunal']}, ano {r['ano']}, "
            f"campo pago_no_ano da entidade {r['nome_entidade']}."
        ),
    }


def _contexto_federal(con: sqlite3.Connection, tribunal: str | None) -> list[dict[str, Any]]:
    """Ente agregados da fila O: mostra União e INSS no mapa, sem usá-los no T."""
    tribunal = (tribunal or "TRF4").upper()
    nomes = MAPA_FEDERAL_CONTEXTO
    placeholders = ",".join("?" * len(nomes))
    rows = list(
        con.execute(
            f"""
            SELECT tribunal, ano, nome_entidade, cnpj, esfera, regime,
                   pago_no_ano, saldo_devedor
            FROM trf_mapas
            WHERE tribunal = ? AND nome_entidade IN ({placeholders})
            ORDER BY ano DESC, pago_no_ano DESC
            """,
            (tribunal, *nomes),
        )
    )
    if not rows:
        return []
    ano_max = max(r["ano"] for r in rows)
    out = []
    vistos = set()
    for r in rows:
        if r["ano"] != ano_max:
            continue
        if r["nome_entidade"] in vistos:
            continue
        vistos.add(r["nome_entidade"])
        out.append(
            {
                "tribunal": r["tribunal"],
                "ano": r["ano"],
                "nome_entidade": r["nome_entidade"],
                "cnpj": r["cnpj"],
                "pago_no_ano": money_round(r["pago_no_ano"]),
                "saldo_devedor": money_round(r["saldo_devedor"]),
                "regime_mapa": r["regime"],
            }
        )
    return out


def prefill(db_path, pendentes_db, numero: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "v0": True,
        "aviso": AVISO_V0,
        "credito": None,
        "pagamento_anual": None,
        "pagamento_anual_fonte": None,
        "pagamento_anual_aviso": None,
        "t_calculado": None,
        "t_origem": None,
        "t_atrasado": False,
        "t_observacao": None,
        "mapa_contexto": [],
        "hipoteses_padrao": HIPOTESES_PADRAO,
        "cenarios_regra": {
            "aviso": CENARIOS_REGRA["aviso"],
            "otimista": CENARIOS_REGRA["otimista"],
            "pessimista": CENARIOS_REGRA["pessimista"],
        },
        "listas_pagos_nao_usadas": (
            "As listas de pagos do TRF2 e do TRF4 não trazem o ente no item "
            "da lista federal; por isso não foram usadas para estimar o "
            "pagamento anual do devedor."
        ),
    }
    if not numero or not numero.strip():
        payload["pagamento_anual_aviso"] = (
            "Sem número de precatório: informe o valor, o valor à frente e o "
            "pagamento anual (ou o T) manualmente. Nada aqui foi lido das bases."
        )
        return payload

    with closing(_connect(db_path, pendentes_db)) as con:
        row = _busca_credito(con, numero)
        if not row:
            payload["ok"] = False
            payload["erro"] = (
                "Não localizamos este número na fila pendente do TRF4. "
                "A calculadora pode ser preenchida à mão."
            )
            return payload

        credito = {
            "numero_precatorio": row["numero_precatorio"],
            "tribunal": row["tribunal"],
            "ente_devedor": row["ente_devedor"],
            "valor": money_round(row["valor"]),
            "natureza": row["natureza"],
            "ordem": row["ordem"],
            "tipo_lista": row["tipo_lista"],
            "regime": row["regime"],
            "ano_orcamento": row["ano_orcamento"],
            "situacao": row["situacao"],
            "creditos_a_frente": row["creditos_a_frente"],
            "valor_a_frente": money_round(row["valor_a_frente"]),
            "coletado_em": row["coletado_em"],
            "atualizado_ate": row["atualizado_ate"] or None,
            "data_apresentacao": row["data_apresentacao"],
            "prioridade": row["prioridade"] or None,
            "fonte": "trf4_pendentes",
        }
        payload["credito"] = credito

        ente = row["ente_devedor"] or ""
        if ente == ENTE_FEDERAL_AGREGADO or row["tipo_lista"] == "O":
            payload["mapa_contexto"] = _contexto_federal(con, row["tribunal"])
            payload["pagamento_anual_aviso"] = (
                "A fila federal do TRF4 (lista O) agrega União, autarquias e "
                "fundações. O mapa da dívida descreve cada ente à parte. Não "
                "atribuímos um pagamento anual único a esta fila, e o T não "
                "é valor à frente dividido por pagamento anual. Os valores "
                "de União e INSS no mapa aparecem só como contexto — não "
                "entram no T."
            )
            ano = row["ano_orcamento"]
            if not ano:
                payload["t_observacao"] = (
                    "Este crédito federal não tem ano orçamentário/proposta "
                    "na base, então não calculamos o T pelo prazo do "
                    "exercício. Informe o T manualmente."
                )
                return payload
            prazo = t_prazo_orcamentario(int(ano))
            payload["t_calculado"] = prazo["t"]
            payload["t_origem"] = "orcamento_federal"
            payload["t_atrasado"] = prazo["atrasado"]
            payload["prazo_pagamento"] = {
                "ano_orcamento": prazo["ano"],
                "data_limite": prazo["prazo"],
                "hoje": prazo["hoje"],
                "atrasado": prazo["atrasado"],
                "regra": (
                    "Hipótese desta v0, editável, inspirada no art. 100, § 5º, "
                    "da Constituição: precatórios federais apresentados até "
                    "2 de abril do ano N devem ser pagos até 31 de dezembro "
                    "do ano N+1. Tomamos o campo ano_orcamento/proposta como "
                    "o ano do exercício de pagamento e o prazo como 31 de "
                    "dezembro desse ano. Não é data oficial de depósito."
                ),
            }
            if prazo["atrasado"]:
                payload["t_observacao"] = (
                    f"Atrasado / prazo vencido. O 31/12/{prazo['ano']} "
                    f"(fim do ano orçamentário/proposta {prazo['ano']} "
                    f"deste crédito) já passou em relação a hoje "
                    f"({prazo['hoje_br']}). Hipótese desta v0: usamos um T "
                    f"mínimo de {T_MINIMO_ATRASADO:.2f} ano (cerca de três "
                    f"meses), não zero — prazo vencido não é pagamento "
                    f"imediato. A regra de referência é o art. 100, § 5º, "
                    f"da Constituição. Você pode informar outro T."
                )
            else:
                payload["t_observacao"] = (
                    f"T sugerido (hipótese, editável): prazo até "
                    f"{prazo['prazo_br']}, último dia do ano "
                    f"orçamentário/proposta {prazo['ano']} que consta neste "
                    f"crédito. Hoje é {prazo['hoje_br']}; faltam "
                    f"{prazo['dias']} dias. T = {prazo['dias']}/{DIAS_POR_ANO:g} "
                    f"= {prazo['t']:.4f} anos. A regra de referência é o "
                    f"art. 100, § 5º, da Constituição: precatórios federais "
                    f"apresentados até 2 de abril do ano N devem ser pagos "
                    f"até 31 de dezembro do ano N+1. Nesta v0 o campo "
                    f"ano_orcamento/proposta é o ano do exercício de "
                    f"pagamento. Isso não é uma data oficial de depósito e "
                    f"não considera atraso do ente. Você pode informar outro T."
                )
            return payload

        fonte = _mapa_exato(con, ente, row["tribunal"])
        if not fonte:
            payload["pagamento_anual_aviso"] = (
                f"Não encontramos no mapa da dívida um ente com o mesmo nome "
                f"que «{ente}» no {row['tribunal'] or 'tribunal'} (ano mais "
                f"recente disponível). Não inventamos o pagamento anual. "
                f"Informe o valor ou o T manualmente."
            )
            payload["t_observacao"] = "T não foi calculado: sem pagamento anual casado no mapa."
            return payload

        payload["pagamento_anual"] = fonte["pago_no_ano"]
        payload["pagamento_anual_fonte"] = fonte
        pago = fonte["pago_no_ano"] or 0
        frente = row["valor_a_frente"]
        if frente is None:
            payload["t_observacao"] = (
                "Há pagamento anual no mapa, mas esta linha não tem valor à "
                "frente na fila. Informe o T manualmente."
            )
            return payload
        if pago <= 0:
            payload["pagamento_anual_aviso"] = (
                fonte["label"] + " O campo pago_no_ano é zero ou negativo neste ano, "
                "então não usamos como denominador do T. Informe o T ou outro "
                "pagamento anual."
            )
            payload["t_observacao"] = "T não foi calculado: pago_no_ano ≤ 0 no mapa."
            return payload

        t = float(frente) / float(pago)
        payload["t_calculado"] = t
        payload["t_origem"] = "mapa_fila"
        avisos = [fonte["label"] + f" T provisório = valor à frente / pago_no_ano = {t:.4f} anos."]
        if t >= 20:
            avisos.append(
                "Este T é muito longo porque o pago_no_ano do mapa é pequeno "
                "diante do valor à frente. Um único ano do mapa pode não "
                "representar o ritmo futuro (por exemplo em regime especial). "
                "Confira e, se for o caso, informe o T manualmente."
            )
        if frente == 0:
            avisos.append(
                "Valor à frente é zero, então o T calculado é 0 anos. Isso não "
                "significa pagamento imediato — informe um T se quiser incorporar "
                "o prazo residual."
            )
        payload["t_observacao"] = " ".join(avisos)
        return payload


def register(app, db_path_getter, pendentes_db_getter) -> None:
    @app.get("/api/precificar")
    def api_precificar(numero: str | None = None):
        payload = prefill(db_path_getter(), pendentes_db_getter(), numero)
        if not payload.get("ok"):
            return JSONResponse(payload, status_code=404)
        return payload

    @app.get("/api/precificar/calcular")
    def api_calcular(
        valor: float = Query(...),
        t: float = Query(...),
        p: float = Query(...),
        r: float = Query(...),
        correcao: float = Query(0),
        ir: float = Query(0),
        honorarios: float = Query(0),
    ):
        try:
            base = calcular(valor, t, p, r, correcao, ir, honorarios)
            cenarios = calcular_cenarios(valor, t, p, r, correcao, ir, honorarios)
        except ValueError as exc:
            return JSONResponse({"ok": False, "v0": True, "erro": str(exc), "aviso": AVISO_V0}, status_code=400)
        return {
            "ok": True,
            "v0": True,
            "aviso": AVISO_V0,
            "base": base,
            "cenarios": cenarios["cenarios"],
            "faixa_desagio": cenarios["faixa_desagio"],
            "aviso_cenarios": cenarios["aviso"],
            "formula": {
                "valor_no_pagamento": "ValorAtualHoje × (1 + c)^T × (1 − IR − honorários)",
                "preco": "ValorNoPagamento × (1 − p) / (1 + r)^T",
                "desagio": "1 − Preço / ValorAtualHoje",
            },
        }
