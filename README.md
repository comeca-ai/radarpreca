# Radar Precatório

Site e API da prova de conceito: bases públicas de precatórios (SIOP, TRF2, TRF4 e TRF5), com busca, filtros e a análise exploratória do SIOP 2026.

Testado em 12/11/2026 (America/Sao_Paulo).

## Como rodar

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Na primeira subida o app descompacta `data/precatorios.sqlite.gz` para `/tmp/radar-precatorio/precatorios.sqlite`.

## Endpoints

- `GET /` — site (abas Aprendizado, Projeto e Bases)
- `GET /api/health`
- `GET /api/bases` — fontes, datas e limites
- `GET /api/stats` — resumo da análise do SIOP
- `GET /api/siop?tribunal=&uo=&nfgc=&min_valor=&q=&page=`
- `GET /api/trf/pagos?tribunal=&proposta=&min_valor=&q=&page=`
- `GET /api/trf/mapas?tribunal=&q=&page=`
- `GET /api/trf/extra?q=&page=`
- `GET /api/download/siop.csv` (e equivalentes para pagos e mapas)

Os CPF/CNPJ de beneficiários entram só na forma parcial já publicada pelas listas dos tribunais.
