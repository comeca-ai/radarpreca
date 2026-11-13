#!/usr/bin/env python3
"""Coletor da fila pendente de precatórios do TRF4 (ordem cronológica).

Fonte oficial, sem login e sem captcha:

  https://www.trf4.jus.br/trf4/controlador.php?acao=consulta_precatorios_ordem_cronologica_externa

Fluxo reproduzido do formulário público:

  1. GET da página (grava PHPSESSID)
  2. POST rdoTipo=O|E|EE  (O = Fazenda Pública Federal; E = extraorçamentárias
     regime geral; EE = extraorçamentárias regime especial)
  3. A resposta HTML dispara window.open('salvar_como_txt.php?arq=...csv')
  4. GET desse arquivo na mesma sessão

A lista orçamentária (O) não discrimina o ente (INSS, União, autarquias).
As listas E e EE trazem a entidade devedora. A lista federal, segundo nota
do próprio arquivo, cobre precatórios recebidos no TRF4 a partir de 03/04/2023;
os já pagos saem desta listagem e vão para planilha própria no portal.

Não inclui data de nascimento (presente em 1 linha da lista EE) — minimização LGPD.
CPF/CNPJ entra só na forma parcial já publicada pelo tribunal, na lista O.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.cookiejar import CookieJar
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
BASE = "https://www.trf4.jus.br/trf4"
FORM_URL = f"{BASE}/controlador.php?acao=consulta_precatorios_ordem_cronologica_externa"
DOWNLOAD_TMPL = f"{BASE}/salvar_como_txt.php?arq={{arq}}"

TIPOS = {
    "O": {
        "regime": "orcamentario",
        "regime_label": "Fazenda Pública Federal (União, autarquias e fundações)",
        "ente_padrao": "Fazenda Pública Federal (União, autarquias e fundações)",
    },
    "E": {
        "regime": "extraorcamentario_geral",
        "regime_label": "Entidades extraorçamentárias, regime geral",
        "ente_padrao": "",
    },
    "EE": {
        "regime": "extraorcamentario_especial",
        "regime_label": "Entidades extraorçamentárias, regime especial",
        "ente_padrao": "",
    },
}

COLUNAS = [
    "tribunal",
    "ente_devedor",
    "numero_precatorio",
    "processo_origem",
    "ano_orcamento",
    "ordem",
    "natureza",
    "valor",
    "data_apresentacao",
    "situacao",
    "fonte_url",
    "coletado_em",
    "tipo_lista",
    "regime",
    "prioridade",
    "base_legal",
    "cpf_cnpj_parcial",
    "uf",
    "parcelado",
    "atualizado_ate",
    "valor_expedido",
]

HEADER_MARK = re.compile(r"^N[ºo°]\s*(de\s+)?Ordem Cronol", re.I)
ARQ_RE = re.compile(r"salvar_como_txt\.php\?arq=([^'\"\s>]+)")


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def br_float(s: str | None) -> float | None:
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_data(s: str | None) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt.endswith("%H:%M:%S") and (dt.hour, dt.minute, dt.second) != (0, 0, 0):
                return dt.strftime("%Y-%m-%dT%H:%M:%S")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def classifica_natureza(base_legal: str, prioridade: str) -> str:
    text = f"{base_legal} {prioridade}".lower()
    text = (
        text.replace("não", "nao")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    if "nao alimentar" in text:
        return "comum"
    if "alimentar" in text:
        return "alimentar"
    if "comum" in text:
        return "comum"
    return ""


def _sem_acento(s: str) -> str:
    table = str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüçñº°",
        "aaaaaeeeeiiiiooooouuuucnoo",
    )
    return s.translate(table)


def norm_header(name: str) -> str:
    h = " ".join((name or "").strip().split()).lower()
    return _sem_acento(h)


def colmap(header: list[str]) -> dict[str, int]:
    idx: dict[str, int] = {}
    for i, raw in enumerate(header):
        h = norm_header(raw)
        if not h:
            continue
        if "ordem" in h and "cronol" in h and "enquadramento" not in h and "base legal" not in h:
            idx["ordem"] = i
        elif "entidade" in h:
            idx["ente"] = i
        elif h == "proposta":
            idx["proposta"] = i
        elif "base legal" in h:
            idx["base_legal"] = i
        elif "precat" in h and ("numero" in h or h.startswith("no ") or h.startswith("n ")):
            idx["precatorio"] = i
        elif "cpf" in h or "cnpj" in h:
            idx["cpf"] = i
        elif "autua" in h:
            idx["autuacao"] = i
        elif "atualizado ate" in h:
            idx["atualizado_ate"] = i
        elif "parcela devida" in h:
            idx["parcela"] = i
        elif h.startswith("saldo"):
            idx["saldo"] = i
        elif "valor_expedido" in h or "valor expedido" in h:
            idx["valor_expedido"] = i
        elif h == "prioridade":
            idx["prioridade"] = i
        elif h == "uf":
            idx["uf"] = i
        elif h == "parcelado":
            idx["parcelado"] = i
    return idx


def get_cell(row: list[str], idx: dict[str, int], key: str) -> str:
    i = idx.get(key)
    if i is None or i >= len(row):
        return ""
    return (row[i] or "").strip()


def read_source_csv(raw: bytes) -> tuple[list[str], list[list[str]]]:
    text = raw.decode("latin-1")
    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if HEADER_MARK.search(line.strip()):
            start = i
            break
    body = "\n".join(lines[start:])
    rows = list(csv.reader(io.StringIO(body), delimiter=";"))
    if not rows:
        return [], []
    header = [c.strip() for c in rows[0]]
    data = [r for r in rows[1:] if any((c or "").strip() for c in r)]
    return header, data


class ClienteTRF4:
    def __init__(self, timeout: int = 180, retries: int = 3) -> None:
        self.timeout = timeout
        self.retries = retries
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )

    def _open(self, url: str, data: bytes | None = None) -> bytes:
        headers = {
            "User-Agent": UA,
            "Referer": FORM_URL,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        last_err: Exception | None = None
        for attempt in range(1, self.retries + 1):
            req = urllib.request.Request(url, data=data, headers=headers)
            try:
                with self.opener.open(req, timeout=self.timeout) as resp:
                    return resp.read()
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_err = exc
                time.sleep(min(2 * attempt, 8))
        raise RuntimeError(f"Falha ao acessar {url}: {last_err}")

    def iniciar_sessao(self) -> None:
        self._open(FORM_URL)

    def baixar_tipo(self, tipo: str) -> tuple[str, bytes]:
        payload = urllib.parse.urlencode({"rdoTipo": tipo}).encode("ascii")
        html = self._open(FORM_URL, data=payload).decode("latin-1", "replace")
        found = ARQ_RE.findall(html)
        if not found:
            raise RuntimeError(
                f"POST rdoTipo={tipo} não devolveu salvar_como_txt.php "
                "(captcha, mudança de formulário ou sessão inválida)."
            )
        arq = found[0]
        blob = self._open(DOWNLOAD_TMPL.format(arq=urllib.parse.quote(arq)))
        if blob.lstrip().lower().startswith(b"<!doctype") or blob.lstrip().lower().startswith(b"<html"):
            raise RuntimeError(f"Download de {arq} devolveu HTML, não CSV.")
        return arq, blob


def normalizar_tipo(
    tipo: str,
    header: list[str],
    rows: list[list[str]],
    coletado_em: str,
    fonte_url: str,
) -> list[dict]:
    meta = TIPOS[tipo]
    idx = colmap(header)
    out: list[dict] = []
    for row in rows:
        ordem_s = get_cell(row, idx, "ordem")
        if not ordem_s:
            continue
        try:
            ordem = int(ordem_s)
        except ValueError:
            continue
        ente = get_cell(row, idx, "ente") or meta["ente_padrao"]
        base_legal = get_cell(row, idx, "base_legal")
        prioridade = get_cell(row, idx, "prioridade")
        valor = br_float(get_cell(row, idx, "saldo"))
        if valor is None:
            valor = br_float(get_cell(row, idx, "parcela"))
        valor_expedido = br_float(get_cell(row, idx, "valor_expedido"))
        proposta = get_cell(row, idx, "proposta")
        ano = None
        if proposta:
            try:
                ano = int(proposta)
            except ValueError:
                ano = proposta
        rec = {
            "tribunal": "TRF4",
            "ente_devedor": ente,
            "numero_precatorio": get_cell(row, idx, "precatorio"),
            "processo_origem": "",
            "ano_orcamento": ano if ano is not None else "",
            "ordem": ordem,
            "natureza": classifica_natureza(base_legal, prioridade),
            "valor": "" if valor is None else round(valor, 2),
            "data_apresentacao": parse_data(get_cell(row, idx, "autuacao")),
            "situacao": "pendente",
            "fonte_url": fonte_url,
            "coletado_em": coletado_em,
            "tipo_lista": tipo,
            "regime": meta["regime"],
            "prioridade": prioridade,
            "base_legal": base_legal,
            "cpf_cnpj_parcial": get_cell(row, idx, "cpf"),
            "uf": get_cell(row, idx, "uf"),
            "parcelado": get_cell(row, idx, "parcelado"),
            "atualizado_ate": get_cell(row, idx, "atualizado_ate"),
            "valor_expedido": "" if valor_expedido is None else round(valor_expedido, 2),
        }
        out.append(rec)
    return out


def escrever_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUNAS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def coletar(raw_dir: Path, from_raw: bool) -> tuple[list[dict], dict[str, str]]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    coletado_em = now_iso()
    arquivos: dict[str, str] = {}
    todos: list[dict] = []
    cliente = None if from_raw else ClienteTRF4()
    if cliente:
        print("Abrindo sessão no formulário do TRF4…", file=sys.stderr)
        cliente.iniciar_sessao()

    for tipo in ("O", "E", "EE"):
        if from_raw:
            existentes = sorted(raw_dir.glob(f"precatorios_ordem_cronologica_{tipo}_*.csv"))
            if not existentes:
                raise FileNotFoundError(
                    f"Não achei CSV bruto de tipo {tipo} em {raw_dir}"
                )
            path = existentes[-1]
            blob = path.read_bytes()
            arq = path.name
            print(f"Lendo bruto {arq} ({len(blob)} bytes)", file=sys.stderr)
        else:
            assert cliente is not None
            print(f"Coletando tipo {tipo} ({TIPOS[tipo]['regime_label']})…", file=sys.stderr)
            arq, blob = cliente.baixar_tipo(tipo)
            path = raw_dir / arq
            path.write_bytes(blob)
            print(f"  salvo {path} ({len(blob)} bytes)", file=sys.stderr)
        arquivos[tipo] = arq
        header, rows = read_source_csv(blob)
        if "precatorio" not in colmap(header):
            raise RuntimeError(f"Cabeçalho inesperado em {arq}: {header}")
        normalizados = normalizar_tipo(tipo, header, rows, coletado_em, FORM_URL)
        print(f"  {len(normalizados)} linhas normalizadas", file=sys.stderr)
        todos.extend(normalizados)
    return todos, arquivos


def main() -> int:
    default_out = Path("/workspace/precatorios/poc/trf/trf4_pendentes.csv")
    default_raw = Path("/workspace/precatorios/poc/trf/raw")
    parser = argparse.ArgumentParser(description="Coleta a fila pendente do TRF4")
    parser.add_argument("--out", type=Path, default=default_out)
    parser.add_argument("--raw-dir", type=Path, default=default_raw)
    parser.add_argument(
        "--from-raw",
        action="store_true",
        help="Não baixa de novo; normaliza CSVs já salvos em --raw-dir",
    )
    args = parser.parse_args()
    rows, arquivos = coletar(args.raw_dir, args.from_raw)
    escrever_csv(args.out, rows)
    print(f"Escreveu {len(rows)} linhas em {args.out}", file=sys.stderr)
    print("Arquivos de origem:", arquivos, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
