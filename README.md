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

- `GET /` — site (abas Consulta, Aprendizado, Projeto e Bases)
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
