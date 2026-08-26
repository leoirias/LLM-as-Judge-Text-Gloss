# Pipelines de regras e validação de glosa (Libras / ASL)

Documenta como funcionam as três etapas construídas: **extração de regras**,
**simplificação** e **avaliação (juiz)**. Escrito em 19/08/2026.

Os dois idiomas têm estrutura espelhada — `libras_pipeline/` e `asl_pipeline/`
—, com o mesmo código e o mesmo formato de CSV. O que muda entre eles é
apenas o `config.yaml` (fontes, prefixo de ID) e o idioma/terminologia dos
prompts. O pipeline de **avaliação existe só para Libras** por enquanto.

```
libras_pipeline/
  extraction/       etapa 1 — documento  ->  regras candidatas
  simplification/   etapa 2 — candidatas -> grupos -> lista final
  evaluation/       etapa 3 — texto+glosa -> válido / inválido / não-coberto
```

Modelo em uso nas três etapas: **Qwen/Qwen3.8-27B** (denso, 27,8B, Apache
2.0), bf16, **thinking desligado**, determinístico (`do_sample: false`).
Ocupa ~54 GB e roda em **1 GPU A100 80GB**. Cada etapa tem seu próprio
`llm.py` e `config.yaml` — os diretórios são autocontidos, sem import
cruzado.

---

## Etapa 1 — Extração (`extraction/`)

Lê PDFs e produz regras candidatas em CSV.

### Como roda

```bash
docker compose exec -e CUDA_VISIBLE_DEVICES=<N> judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/extraction/extract.py'
```

| Flag | Efeito |
|---|---|
| *(sem flag)* | processa **todas** as fontes de `books:` no config |
| `--book "<trecho>"` | só a fonte cujo label contém esse texto |
| `--patch-pages I F` | reprocessa só essa faixa e funde no resultado existente (repetível) |
| `--from-raw` | reconstrói o CSV do `.raw.txt` salvo, **sem GPU** |

### O que acontece por dentro

1. Fatia a faixa `start_page`–`end_page` de cada fonte em **janelas de 15
   páginas** (`window_pages`). Uma chamada de LLM por janela — o texto
   inteiro de um capítulo não cabe num prompt.
2. Extrai o texto com `pypdf`, marcando cada página como `[p.N]` (índice
   0-based do pypdf, **não** o número impresso) para a citação ser rastreável.
3. O modelo devolve JSON com as regras da janela.
4. **Parse tolerante a item**: valida regra por regra, não a lista inteira —
   uma regra com campo faltando é descartada sozinha, sem derrubar as outras
   da mesma janela.
5. Atribui `id` **por código**, sequencial por categoria
   (`LIBRAS.SINTAXE.001`). O modelo escolhe só a `categoria`; o ID não pode
   vir dele porque cada janela é uma chamada isolada e os IDs colidiriam.
6. Salva `<slug>_regras.csv` e `<slug>_regras.raw.txt` (resposta crua, para
   auditoria e para o `--from-raw`).

### Saída

`id · categoria · titulo · descricao · gatilho · verificavel_por_texto ·
exemplos · fonte_livro · fonte_pagina · fonte_citacao`

`verificavel_por_texto` é o campo mais importante: `true` = dá para checar
olhando só o texto da glosa; `false` = depende de canal fora do texto
(expressão facial, articulação-boca, uso do espaço, movimento).

### Fontes configuradas

| Idioma | Fonte | Páginas (0-based) |
|---|---|---|
| Libras | Gramática da Libras Vol.1 (INES/Quadros et al.) — Cap.5 Morfologia | 174–377 |
| Libras | Estudos Linguísticos (Quadros & Karnopp) — Cap.4 Sintaxe espacial | 123–210 |
| Libras | Notas de consultoria (Profa. Tânia, 31/07/2026) | 0–5 |
| ASL | ASL for Dummies — Caps. 1-13 | 16–294 |
| ASL | ASL for Dummies — Cap.19 (expressões populares) | 335–340 |

---

## Etapa 2 — Simplificação (`simplification/`)

Três scripts, aplicados em ordem. Só o segundo e o terceiro usam GPU.

### 2.1 `classify_pipeline.py` — separa por canal (sem GPU)

```bash
docker compose exec judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/simplification/classify_pipeline.py'
```

Lê **todos** os `extraction/output/*_regras.csv` e separa em dois grupos pelo
`verificavel_por_texto`:

- **`voice2sign_candidatas.csv`** — verificável no texto; é o que o juiz usa.
- **`sign2voice_candidatas.csv`** — depende de vídeo; fora do escopo do juiz.

Também **renumera IDs em colisão**: cada livro numera do 1 por categoria, então
duas fontes podem gerar o mesmo `LIBRAS.SINTAXE.002`. Só as categorias que
realmente colidiram são renumeradas.

`--source X` restringe a uma fonte e escreve em arquivo separado
(`X_voice2sign_candidatas.csv`), sem tocar no pool principal — usado para
isolar uma fonte nova e compará-la contra a base já consolidada.

### 2.2 `merge_rules.py` — funde duplicatas (com GPU)

```bash
docker compose exec -e CUDA_VISIBLE_DEVICES=<N> judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/simplification/merge_rules.py'
```

| Flag | Efeito |
|---|---|
| `--group voice2sign\|sign2voice` | qual grupo fundir (default: voice2sign) |
| `--source X` | funde uma fonte isolada (`X_..._candidatas.csv`) |
| `--id-prefix TANIA` | sobrescreve o prefixo do ID, para fontes distintas não colidirem quando unidas |
| `--categoria X` | reprocessa só 1 categoria e **funde no CSV existente**, preservando as outras |

Processa **por categoria, em rodadas**: pega a lista já consolidada (vazia na
1ª) + um lote de 15 candidatas novas e pede a lista atualizada. Categoria com
1 candidata só nem chama o modelo.

Três redes de segurança, todas por causa de falhas observadas na prática:

1. **Item inválido não derruba o lote** — valida regra por regra.
2. **Candidata esquecida volta sozinha** — se o modelo omitir uma candidata da
   resposta, ela entra como entrada própria (aconteceu de verdade).
3. **Dedup de `ids_origem`** — se o modelo reivindicar a mesma candidata em
   duas regras finais, ela fica só na primeira.

Saída: `id · categoria · titulo · descricao · gatilho · exemplos ·
ids_origem · justificativa_fusao · fontes`. `ids_origem` rastreia até as
candidatas da etapa 1.

### 2.3 `compare_rules.py` — compara fonte nova contra a base (com GPU)

```bash
docker compose exec -e CUDA_VISIBLE_DEVICES=<N> judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/simplification/compare_rules.py --source tania'
```

Uma chamada de LLM por candidata, recebendo a base inteira como contexto.
Classifica em `ja_temos` / `nao_temos` / `conflito` / `parcial`. **Não altera a
base** — só produz `<source>_comparacao.csv` para revisão humana.

> **Limite conhecido:** a comparação é estática, regra contra regra. Um
> conflito que só aparece **quando aplicado a uma frase** passa como
> `parcial`. Foi o que aconteceu com "QU pode mover" (livro) × "QU sempre no
> fim" (Tânia): no papel parecem complementares, na prática se contradizem.

---

## Etapa 3 — Avaliação / juiz (`evaluation/`, só Libras)

```bash
docker compose exec -e CUDA_VISIBLE_DEVICES=<N> judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/evaluation/run.py'
```

| Flag | Efeito |
|---|---|
| `--rules <csv>` | qual base de regras usar (default: `voice2sign_final.csv`) |
| `--exp-name X` | grava em `output/resultado_X.csv` em vez de sobrescrever |

Antes da primeira rodada com um modelo novo, rodar o pré-voo:

```bash
... /opt/venv/bin/python libras_pipeline/evaluation/smoke_qwen38.py
```

Ele **falha explicitamente** se detectar peso inicializado aleatoriamente
(risco real ao carregar um checkpoint multimodal como `AutoModelForCausalLM`),
além de checar thinking desligado, VRAM livre e se o prompt do juiz volta JSON
parseável citando IDs que existem.

### Fluxo

Para **cada frase, isoladamente** (prompt novo, sem histórico entre chamadas):

1. Monta o prompt com o bloco de regras + a frase em português + a glosa.
2. O modelo devolve JSON com 6 campos obrigatórios.
3. **Parse tolerante**: aceita sinônimos de veredito (`aprovado` → `valido`) e,
   se o campo `veredito` faltar, deriva das duas dimensões (qualquer "Não" →
   inválido).
4. Se o parse falhar de vez, a linha vira `nao_coberto` com
   `Origem=parse_falhou` — distinto de abstenção por falta de regra.
5. Avisa se o modelo citar ID que não existe na base (alucinação).

### Os três estados

| Estado | Significado |
|---|---|
| `valido` | fidelidade e estrutura OK |
| `invalido` | viola alguma regra citada |
| `nao_coberto` | **nenhuma regra cobre o fenômeno** — abstenção honesta, não reprovação |

`nao_coberto` fica **fora do cálculo de acurácia**: abstenção não é acerto nem
erro. Esse desenho de 3 estados vem do survey que orienta o projeto.

### Saída

`Texto · Glosa · Estado · Fidelidade · Naturalidade · Regras · Problema ·
Sugestao · Esperado · Acertou · Origem`, mais `resultado_*.raw.txt` com a
resposta crua de cada frase.

---

## Armadilhas já encontradas (e como estão tratadas)

| Problema | Sintoma | Estado |
|---|---|---|
| `@{output_rules}` fora do template do prompt | modelo nunca via o schema; `Fidelidade`/`Problema`/`Sugestao` vazios em 8/8 | corrigido |
| Exemplo do prompt continha uma glosa de teste | vazamento de gabarito | corrigido |
| Glosas de teste nos `exemplos` das regras da Tânia | 100% de acurácia inflado (cai para 83% sem os exemplos) | **em aberto** — inerente à fonte |
| IDs colidindo entre livros | mesma ID em 2 regras | corrigido em `classify_pipeline` |
| `--categoria` sobrescrevia o CSV inteiro | perda das outras categorias | corrigido |
| Checkpoint multimodal como CausalLM | risco de pesos aleatórios silenciosos | coberto pelo smoke test |

---

## Estado dos dados (19/08/2026)

Extração com Qwen3.8-27B: **144 regras** (93 Gramática + 45 Estudos + 6 Tânia).
A extração anterior, com Qwen3-30B-A3B, está preservada em
`extraction/output_qwen3-30b-a3b/` (215 regras) para comparação.

As bases de regras e os resultados de avaliação abaixo ainda vêm da extração
**anterior** — a etapa 2 não foi refeita com os dados novos:

| Base (voice2sign) | Regras | Acurácia no teste de 8 frases |
|---|---|---|
| Só Tânia | 7 | 8/8 — **5/6 sem os exemplos** |
| Só livros | 49 | 2/8 |
| Combinada | 56 | 8/8 — **4/8 sem os exemplos** |

> O conjunto de teste tem **8 frases, todas derivadas do mesmo documento da
> Tânia** (5 literais + 3 perturbações deliberadas). Não mede generalização.
> Frases de fonte independente são a principal lacuna para uma avaliação real.
