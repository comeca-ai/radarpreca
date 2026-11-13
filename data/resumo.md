# EDA — precatórios federais expedidos para 2026 (SIOP/MPO)

Fonte: `/workspace/precatorios/poc/dados_abertos/siop_expedidos_2026.csv` (Secretaria de Orçamento Federal / SIOP, arquivo `expedidos_2026.csv`).  
Leitura em 12/11/2026, por volta das 21:24 (horário de Brasília). 164.012 linhas, 24 colunas, separador `;`, decimal `,`. Exercício único: 2026.

Colunas reais do arquivo (nenhum campo foi inventado): `Chave`, `Exercício`, `Código do Tribunal`, `Nome do Tribunal`, `Tribunal Expedidor`, `Data de Ajuizamento da Ação Originária`, `Data da Autuação`, `Tipo de Despesa`, `Tributário`, `Código da UO Executada`, `Nome da UO Executada`, `Natureza de Despesa`, `Tipo de Causa`, `Valor Original do Precatório`, `Fundef`, `Anos_Decorridos`, `Class_Tempo`, `Class_Tribunais`, `Class_NFGC`, `DataInicio`, `DataFim`, `IndiceAtualizacao`, `Valor Atualizado`, `FaixaValor`.

**Não existem** neste arquivo: número do precatório, número do processo, nome ou CPF/CNPJ do credor, ordem cronológica, nem uma coluna de natureza alimentar versus comum.

## Qualidade dos dados

- `Chave` é única em todas as 164.012 linhas; não há linhas duplicadas, valores negativos nem zeros nos dois campos de valor.
- Única coluna com vazio: `Tribunal Expedidor`, em 148.678 registros (90,65%). Nos 15.334 restantes, o `Nome do Tribunal` é sempre “Conselho Nacional de Justiça” e o expedidor é um TJ estadual (TJSP sozinho aparece 8.020 vezes). São precatórios contra a União expedidos por tribunais de Justiça (competência delegada / registro no CNJ).
- `Valor Atualizado` = `Valor Original do Precatório` × `IndiceAtualizacao` em **todas** as 164.012 linhas. O índice é constante (1,0315237099479411). `DataInicio` e `DataFim` também são constantes (01/04/2025 e 01/02/2026). Ou seja, a atualização é um fator único do SIOP no período, não a correção Selic processo a processo.
- `FaixaValor` casa exatamente com o `Valor Atualizado` (0 divergências).
- `Anos_Decorridos` é o piso (anos completos) do intervalo entre ajuizamento e autuação em 163.985 registros.
- Datas de ajuizamento vão de 29/12/1899 a 27/03/2025. Há 1 registro com data 29/12/1899 (`Chave` 0940528) — sentinela típica de data ausente — e 1 com 31/10/1918 (`Chave` 0818952). 2.141 casos têm ajuizamento até 1988.
- Autuação: 83.636 em 2024 e 80.373 em 2025 (163.999 registros). Só 3 ficam fora (2021, 2022 e 2023, um em cada ano). Máximo em 14/04/2025, coerente com a janela orçamentária do exercício 2026.
- `Tipo de Causa` tem 1.750 textos distintos, com grafias duplicadas do mesmo tema (por exemplo, duas formas de “Reajuste da Tabela do SUS” e duas de FUNDEF). Isso fragmenta totais se a análise for só por texto.

## Totais e estatística de valor

| Indicador | Valor original | Valor atualizado |
|---|---:|---:|
| Soma | R$ 69.667.793.659,80 | R$ 71.863.980.979,84 |
| Mínimo | — | R$ 0,01 |
| P10 | — | R$ 50.556,53 |
| P25 | — | R$ 113.509,11 |
| Mediana | R$ 154.320,28 | R$ 159.185,03 |
| P75 | — | R$ 265.787,91 |
| P90 | R$ 456.169,96 | R$ 470.550,13 |
| P95 | — | R$ 690.233,96 |
| P99 | R$ 1.674.775,31 | R$ 1.727.570,44 |
| Máximo | R$ 1.472.489.475,24 | R$ 1.518.907.806,36 |
| Média | R$ 424.772,54 | R$ 438.162,95 |

A média é 2,75 vezes a mediana. O precatório típico está na casa de R$ 160 mil; a média é puxada por poucos tickets enormes.

**Concentração** (sobre o valor atualizado, do maior para o menor):

- Os 1% mais altos (1.641 precatórios) somam **R$ 35.822.339.789,55** — **49,85%** do estoque.
- Os 10% mais altos (16.402 precatórios) somam **R$ 46.800.779.975,83** — **65,12%** do estoque.

## Por ramo da Justiça (`Class_Tribunais`)

| Ramo | Qtde | Valor atualizado | % qtde | % valor |
|---|---:|---:|---:|---:|
| Justiça Federal | 143.007 | R$ 66.334.120.785,24 | 87,19% | 92,31% |
| Justiça Estadual | 15.426 | R$ 3.260.811.757,10 | 9,41% | 4,54% |
| Justiça do Trabalho | 4.469 | R$ 1.244.217.673,53 | 2,72% | 1,73% |
| STF | 32 | R$ 694.015.711,04 | 0,02% | 0,97% |
| STJ | 1.078 | R$ 330.815.052,93 | 0,66% | 0,46% |

A Justiça Estadual aqui não é dívida de estado ou município: são 15.334 registros do CNJ (TJs como expedidores) mais 92 do TJDFT, todos contra UOs da União.

## Por tribunal (`Nome do Tribunal`)

34 tribunais no arquivo. Os sete primeiros respondem por quase todo o valor:

| Tribunal | Qtde | Valor atualizado | % valor |
|---|---:|---:|---:|
| TRF da 1ª Região | 31.032 | R$ 26.107.804.199,75 | 36,33% |
| TRF da 3ª Região | 39.330 | R$ 16.979.424.123,09 | 23,63% |
| TRF da 4ª Região | 37.676 | R$ 9.680.842.283,60 | 13,47% |
| TRF da 2ª Região | 13.400 | R$ 6.447.309.471,42 | 8,97% |
| TRF da 5ª Região | 11.042 | R$ 4.977.509.452,51 | 6,93% |
| Conselho Nacional de Justiça | 15.334 | R$ 3.245.547.240,87 | 4,52% |
| TRF da 6ª Região | 10.527 | R$ 2.141.231.254,88 | 2,98% |

O TRF1 tem menos processos que o TRF3 e o TRF4, mas concentra mais de um terço do valor (tickets grandes de FUNDEF, Tabela SUS e tributário). O STF tem só 32 precatórios e quase 1% do estoque (ticket médio muito alto).

## Top 20 UOs / entes devedores

144 UOs. Só as duas primeiras concentram **90,02%** do valor atualizado.

| # | Código | Nome da UO Executada | Qtde | Valor atualizado | % valor |
|---|---:|---|---:|---:|---:|
| 1 | 71103 | Encargos Financeiros da União - Pagamento de Sentenças Judiciais | 31.212 | R$ 40.319.046.980,71 | 56,10% |
| 2 | 33904 | Fundo do Regime Geral de Previdência Social | 112.125 | R$ 24.370.117.774,16 | 33,91% |
| 3 | 33201 | Instituto Nacional do Seguro Social | 6.526 | R$ 1.869.819.523,51 | 2,60% |
| 4 | 49201 | Instituto Nacional de Colonização e Reforma Agrária - INCRA | 732 | R$ 1.508.418.106,05 | 2,10% |
| 5 | 55901 | Fundo Nacional de Assistência Social | 4.048 | R$ 541.881.322,03 | 0,75% |
| 6 | 56202 | Companhia Brasileira de Trens Urbanos - CBTU | 7 | R$ 314.761.003,01 | 0,44% |
| 7 | 36211 | Fundação Nacional de Saúde | 1.276 | R$ 260.219.466,54 | 0,36% |
| 8 | 26244 | Universidade Federal do Rio Grande do Sul | 735 | R$ 249.051.468,46 | 0,35% |
| 9 | 39252 | Departamento Nacional de Infraestrutura de Transportes - DNIT | 515 | R$ 235.200.350,26 | 0,33% |
| 10 | 26242 | Universidade Federal de Pernambuco | 562 | R$ 192.450.468,44 | 0,27% |
| 11 | 24204 | Comissão Nacional de Energia Nuclear | 192 | R$ 129.797.149,84 | 0,18% |
| 12 | 36213 | Agência Nacional de Saúde Suplementar - ANS | 68 | R$ 116.282.532,71 | 0,16% |
| 13 | 28233 | Superintendência da Zona Franca de Manaus - SUFRAMA | 36 | R$ 112.241.176,11 | 0,16% |
| 14 | 44201 | Instituto Brasileiro do Meio Ambiente e dos Recursos Naturais Renováveis - IBAMA | 332 | R$ 106.405.430,64 | 0,15% |
| 15 | 36210 | Hospital Nossa Senhora da Conceição S.A. - CONCEIÇÃO | 462 | R$ 99.966.375,57 | 0,14% |
| 16 | 83201 | Banco Central do Brasil - BACEN | 204 | R$ 92.434.305,80 | 0,13% |
| 17 | 26245 | Universidade Federal do Rio de Janeiro | 362 | R$ 92.200.261,05 | 0,13% |
| 18 | 47205 | Fundação Instituto Brasileiro de Geografia e Estatística | 336 | R$ 80.197.198,18 | 0,11% |
| 19 | 26231 | Universidade Federal de Alagoas | 162 | R$ 61.890.150,15 | 0,09% |
| 20 | 26236 | Universidade Federal Fluminense | 131 | R$ 53.187.317,87 | 0,07% |

O Fundo do RGPS coincide 1 a 1 com a classificação `Previdência` (112.125 registros). O FNAS coincide com `LOAS/FNAS`. A UO “Encargos Financeiros da União” é o balde orçamentário dos grandes precatórios de OCC (tributário, FUNDEF, Tabela SUS, desapropriação etc.).

## Classificação (`Class_NFGC`), causa, Fundef e tributário

Não há campo de natureza alimentar/comum. O que o arquivo oferece é `Class_NFGC`:

| Class_NFGC | Qtde | Valor atualizado | % qtde | % valor |
|---|---:|---:|---:|---:|
| OCC | 15.055 | R$ 37.811.519.417,66 | 9,18% | 52,62% |
| Previdência | 112.125 | R$ 24.370.117.774,16 | 68,36% | 33,91% |
| Pessoal | 32.783 | R$ 9.140.348.203,66 | 19,99% | 12,72% |
| LOAS/FNAS | 4.048 | R$ 541.881.322,03 | 2,47% | 0,75% |
| FAT | 1 | R$ 114.262,32 | 0,00% | 0,00% |

`Natureza de Despesa` (código orçamentário) tem só três valores: `31909100` (32.783 linhas, casa 1 a 1 com Pessoal), `33909100` (130.597 linhas) e `45909100` (632 linhas, R$ 3.211.532.675,33). `Tipo de Despesa` `11` também casa 1 a 1 com Pessoal; o tipo `41` casa 1 a 1 com a flag `Fundef`.

- `Fundef` = “Fundef”: **211** precatórios, **R$ 7.758.321.879,89** (10,80% do estoque).
- `Tributário` = “Sim”: **4.555** precatórios, **R$ 14.101.281.398,40** (19,62% do estoque).

Principais `Tipo de Causa` por valor (textos como estão no arquivo):

1. FUNDEF/… Direito Tributário — 141 precatórios, R$ 6.200.050.260,88 (8,63%).
2. Reajuste da Tabela do SUS - Saúde - Serviços - Administrativo — 28, R$ 4.070.746.471,32 (5,66%).
3. Entidades sem Fins Lucrativos - Imunidade - … Direito Tributario — 6, R$ 2.828.200.082,79 (3,94%).
4. Aposentadoria por Tempo de Contribuição (Art. 55/6) — 13.407, R$ 2.748.494.287,20 (3,82%).
5. Aposentadoria Especial (Art. 57/8) — 8.767, R$ 2.657.163.399,66 (3,70%).
6. Reajuste da Tabela do SUS (outra grafia) — 31, R$ 2.204.600.480,21 (3,07%).

Somando as duas grafias, a Tabela SUS aparece em 59 precatórios e **R$ 6.275.346.951,53** (8,73% do estoque). As grafias de FUNDEF + o registro do STF (“COMUM – Precatório referente à complementação da União ao FUNDEF.”) fecham os 211 da flag `Fundef`.

O maior precatório individual (`Chave` 0843066, TRF3) vale **R$ 1.518.907.806,36** (imunidade tributária de entidade sem fins lucrativos). Os quatro acima de R$ 1 bilhão somam R$ 5.153.385.953,95.

## Faixa de valor (`FaixaValor`)

| Faixa | Qtde | Valor atualizado | % qtde | % valor |
|---|---:|---:|---:|---:|
| Até R$ 1 milhão | 160.087 | R$ 33.218.524.069,28 | 97,61% | 46,22% |
| Acima de R$ 1 milhão e até R$ 10 milhões | 3.547 | R$ 7.301.943.652,14 | 2,16% | 10,16% |
| Acima de R$ 10 milhões e até R$ 100 milhões | 302 | R$ 9.091.150.233,50 | 0,18% | 12,65% |
| Acima de R$ 100 milhões e até R$ 500 milhões | 67 | R$ 13.486.043.684,00 | 0,04% | 18,77% |
| Acima de R$ 500 milhões e até R$ 1 bilhão | 5 | R$ 3.612.933.386,98 | 0,00% | 5,03% |
| Acima de R$ 1 bilhão | 4 | R$ 5.153.385.953,95 | 0,00% | 7,17% |

Os 378 precatórios acima de R$ 10 milhões (0,23% da quantidade) concentram **43,61%** do valor.

## Tempo entre ajuizamento e autuação

Intervalo (`Data da Autuação` − `Data de Ajuizamento da Ação Originária`), sem valores negativos:

- Mediana: 6,67 anos (a coluna `Anos_Decorridos` tem mediana 6, porque é o piso).
- P25: 3,81 anos; P75: 14,50 anos; P90: 25,52 anos; P99: 37,89 anos.
- Média: 10,38 anos. Máximo: 124,95 anos (o registro com data 1899).

`Class_Tempo`:

| Faixa | Qtde | Valor atualizado | % qtde | % valor |
|---|---:|---:|---:|---:|
| Até 5 anos | 59.755 | R$ 16.320.466.038,56 | 36,43% | 22,71% |
| De 5 até 10 anos | 45.826 | R$ 18.620.690.905,86 | 27,94% | 25,91% |
| De 10 até 15 anos | 18.896 | R$ 6.707.552.240,28 | 11,52% | 9,33% |
| De 15 até 20 anos | 13.908 | R$ 8.577.438.348,15 | 8,48% | 11,94% |
| 20 anos ou mais | 25.627 | R$ 21.637.833.446,99 | 15,63% | 30,11% |

Os processos mais antigos pesam desproporcionalmente no valor: 15,6% dos precatórios com 20 anos ou mais carregam 30,1% do estoque.

## Insights para compra e intermediação

1. **Este CSV não basta para fechar uma operação.** Não identifica o crédito (sem número de precatório, processo ou credor). Serve para dimensionar o mercado federal de 2026 e priorizar tribunais, UOs e tipos de causa. Para comprar ou intermediar, é preciso cruzar com as listas dos TRFs (número, ordem, CPF parcial).
2. **Há dois mercados no mesmo arquivo.** O volume é previdenciário: 112.125 precatórios do Fundo do RGPS, ticket típico perto da mediana (R$ 159 mil). O valor, porém, está no OCC (15.055 precatórios, 52,6% do estoque), sobretudo na UO “Encargos Financeiros da União” (56,1%). Quem compra “o precatório médio” e quem compra o estoque em reais está olhando coisas diferentes.
3. **Concentração extrema muda o risco.** 1% dos créditos (1.641) vale quase metade do estoque; 9 créditos na cauda superam R$ 500 milhões, quase todos de tributário, FUNDEF, Tabela SUS ou desapropriação. Esses tickets exigem due diligence jurídica individual; não se precificam como um precatório previdenciário de R$ 160 mil.
4. **FUNDEF e Tabela SUS são o maior risco de tese.** FUNDEF: 211 créditos, R$ 7,76 bilhões (10,8%). Tabela SUS, somando as duas grafias: 59 créditos, R$ 6,28 bilhões (8,7%). São exatamente as teses com maior ruído político e judicial (incluindo a suspensão recente, no STF, dos casos da Tabela SUS). Um deságio “de mercado” genérico não serve aqui.
5. **Tributário é pouco numeroso e muito valioso.** Só 4.555 registros (2,8%) com `Tributário = Sim`, mas 19,6% do valor (R$ 14,10 bilhões). Há ainda risco típico de compensação com dívida fiscal, que este arquivo não mostra.
6. **A União paga o exercício 2026 — o prazo é outro, o risco de fila também.** Quase todo o arquivo foi autuado em 2024–2025, ou seja, entra na proposta orçamentária de 2026 da União, em regra mais pontual do que filas estaduais/municipais. Isso não elimina o risco de tese (SUS, FUNDEF) nem o fato de 30% do valor vir de processos com 20 anos ou mais (herdeiros, cessões, cálculos, ônus).
7. **O valor “atualizado” do SIOP não é o valor de face judicial.** Foi aplicado um IPCA único (cerca de 3,15%) de 01/04/2025 a 01/02/2026. Para negociar, o cálculo tem de ser refeito com a regra vigente (hoje Selic) e a data-base de cada crédito, que este arquivo não traz.

## Gráficos e tabelas

Gráficos (matplotlib, rótulos em pt-BR):

- `/workspace/precatorios/poc/eda/01_valor_por_ramo.png`
- `/workspace/precatorios/poc/eda/02_valor_por_tribunal.png`
- `/workspace/precatorios/poc/eda/03_top_uos.png`
- `/workspace/precatorios/poc/eda/04_classificacao_nfgc.png`
- `/workspace/precatorios/poc/eda/05_faixa_de_valor.png`
- `/workspace/precatorios/poc/eda/06_concentracao_valor.png`

Tabelas auxiliares no mesmo diretório: `tabela_ramo.csv`, `tabela_tribunais.csv`, `tabela_top30_uos.csv`, `tabela_nfgc.csv`, `tabela_faixa.csv`, `tabela_top30_tipo_causa.csv`, `tabela_top10_precatarios.csv`. Script: `analisar.py`.
