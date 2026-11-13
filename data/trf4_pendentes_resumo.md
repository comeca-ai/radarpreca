# Fila pendente do TRF4 — resumo da coleta

Coletado em **12/11/2026, 22:25:45 (America/Sao_Paulo)**.
Fonte: [Consulta precatórios por ordem cronológica](https://www.trf4.jus.br/trf4/controlador.php?acao=consulta_precatorios_ordem_cronologica_externa).

## Como o dado é obtido

Sem login e sem captcha. O formulário público `frmProcListas` faz POST em `controlador.php?acao=consulta_precatorios_ordem_cronologica_externa` com `rdoTipo`:

- `O` — Fazenda Pública Federal (União, autarquias e fundações)
- `E` — entidades extraorçamentárias, regime geral
- `EE` — entidades extraorçamentárias, regime especial

A resposta HTML abre `salvar_como_txt.php?arq=precatorios_ordem_cronologica_{O|E|EE}_AAAAMMDD.csv`. O download precisa da mesma sessão (`PHPSESSID`) do POST. O coletor é `/workspace/precatorios/coletores/trf4_pendentes.py`.

Arquivos brutos (latin-1, ponto-e-vírgula) em `/workspace/precatorios/poc/trf/raw/`. Normalizado em `/workspace/precatorios/poc/trf/trf4_pendentes.csv` (UTF-8).

## Totais

| Recorte | Linhas | Valor (R$) |
| --- | ---: | ---: |
| Total | 62.993 | 8.732.690.205,97 |
| O — Fazenda Pública Federal | 62.147 | 7.839.244.083,69 |
| E — extraorçamentário, regime geral | 232 | 89.278.023,20 |
| EE — extraorçamentário, regime especial | 614 | 804.168.099,08 |
| Natureza alimentar | 61.047 | 6.345.914.071,70 |
| Natureza comum | 1.946 | 2.386.776.134,27 |

Todas as 62.993 linhas estão com situação `pendente` e com valor preenchido. Há 30.061 números de precatório distintos (na lista federal um crédito pode aparecer mais de uma vez quando o valor ultrapassa 180 salários mínimos ou há honorários destacados, conforme as notas do próprio arquivo). Nenhum registro traz `processo_origem`.

Valores: na lista O, a *Parcela Devida* atualizada até 02/2026; nas listas E e EE, o *Saldo em 11/2026*. A lista O está inteira na proposta orçamentária 2027. As listas extraorçamentárias espalham propostas de 2006 a 2027.

## Top 10 entes por valor

| # | Ente devedor | Linhas | Valor (R$) |
| ---: | --- | ---: | ---: |
| 1 | Fazenda Pública Federal (União, autarquias e fundações) | 62.147 | 7.839.244.083,69 |
| 2 | ESTADO DE SANTA CATARINA | 163 | 302.535.288,27 |
| 3 | ESTADO DO PARANÁ | 9 | 234.443.780,15 |
| 4 | ESTADO DO RIO GRANDE DO SUL | 136 | 135.143.761,47 |
| 5 | MUNICÍPIO DE BUTIÁ/RS | 26 | 25.263.087,67 |
| 6 | FUNDAÇÃO HOSPITALAR SANTA TEREZINHA DE ERECHIM | 2 | 21.301.329,90 |
| 7 | MUNICÍPIO DE FLORIANÓPOLIS/SC | 16 | 17.678.792,68 |
| 8 | MUNICÍPIO DE FOZ DO IGUAÇU/PR | 5 | 12.477.555,00 |
| 9 | MUNICÍPIO DE CURITIBA/PR | 22 | 10.393.267,33 |
| 10 | EMPRESA BRASILEIRA DE INFRA-ESTRUTURA AEROPORTUÁRIA - INFRAERO | 4 | 9.334.390,44 |

172 entes no total: o ente federal agregado mais 171 entes das listas E e EE.

## Limitações

- A lista O **não discrimina** INSS, União ou autarquia; o tribunal publica um bloco único. O rótulo `ente_devedor` dessa fatia é o do próprio formulário.
- A lista federal, segundo nota do arquivo, cobre precatórios **recebidos no TRF4 a partir de 03/04/2023**. Estoque anterior não pago, se existir, não está neste recorte. Os já pagos saem desta lista e vão para a planilha própria do portal.
- Não há número do processo de origem. CPF/CNPJ do beneficiário só aparece, e só parcial, na lista O. Uma linha da lista EE trazia data de nascimento; esse campo **não foi** incorporado (minimização LGPD).
- A "ordem" é por fila (por ente nas listas E/EE; única fila federal na lista O), não uma ordem global do tribunal.
- Datas de autuação antigas na lista O (há registros com 2006, 2009 etc., ainda na proposta 2027) são as que o tribunal publicou; o coletor não corrige.
