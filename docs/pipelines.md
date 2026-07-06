# Normalização de Glosa ASL — Como funcionam os dois pipelines

Roteiro de apresentação. Explica **o que cada pipeline faz, etapa por etapa**,
onde entra **função determinística** e onde entra **LLM**, com um exemplo andando
e os resultados da avaliação.

---

## 1. O problema (1 frase)

Dado um par **`(texto inglês, glosa)`**, dizer se a glosa está na **convenção da
consultoria** e, se não estiver, **corrigir e normalizar**. A glosa de entrada é
ruidosa: prefixos `DESC-`/`X-`, mojibake, artigo/preposição sobrando, plural,
verbo flexionado, composto mal marcado.

**Fonte da verdade = os pares-ouro** (`pares_ouro.csv` / coluna `Output review`
do `pares_review.csv`). **Toda regra foi extraída do ouro.**

---

## 2. As regras da convenção (o que normalizar)

Todas vêm do ouro. Numeração estável (detalhe em `plain.md`).

- **Erros:** E2 mojibake · E3 prefixo (`DESC-`/`X-`/`G-`) · E4 typo/token truncado · E5 abreviação (`LAB→LABORATORY`) · E6 composto (`BLOOD-TEST→BLOOD TEST`).
- **Token:** R1 MAIÚSCULAS · R2 artigo cai · **R2b preposição cai** (`for/of/to/with/in/from/about`; quantificador `any/some` **fica**) · R3 cópula "be" cai (todas as formas, incl. `been`) · R4 auxiliar de pergunta cai · **R4b `have/has/had` auxiliar cai** (perfeito), mas `HAVE` de conteúdo fica · R5 pronome sujeito cai (exceto sem verbo / objeto) · R6 possessivo cai · R7 substantivo singular (**nome próprio não**) · R8 verbo na base · R9 composto real com `_`.
- **Frase:** R10 tempo na frente · R11 WH no fim (exceto pergunta sem verbo) · R12 mantém verbo de conteúdo/modal (`HAVE/FEEL/CAN`) · R13 passado com `FINISH`/`PAST` · R14 sinal conceitual · R15 pontuação por tipo de frase.
- **Compostos reais (`_`):** `HOW_MUCH NO_PROBLEM NOT_UNDERSTAND PASS_OUT THANK_YOU THIS_MORNING WRITE_DOWN`.

> Princípio de design: **regra só existe se o ouro mostra.** O que o ouro não
> cobre (ex.: `that` relativo, estrutura de título parlamentar) não vira regra
> determinística — fica pro LLM ou pra revisão humana.

---

## 3. Pipeline B1 — só LLM (um prompt por etapa)

**Ideia:** o LLM faz tudo. Cada etapa é **um prompt** que recebe o `texto` inglês
(referência) + a glosa do passo anterior e devolve a glosa atualizada. Sem
nenhuma função determinística.

```
(texto, glosa)
   │
   ├─ Prompt 2 — Erros conhecidos (E2–E6)         [LLM]
   ├─ Prompt 3 — Limpeza token a token (R1–R9)    [LLM]
   ├─ Prompt 4 — Reorganização da frase (R10–R15) [LLM]  + exemplos do ouro (few-shot)
   └─ Prompt 5 — Validação (opcional)             [LLM]
   │
   gloss_output_llm
```

**O que falar de cada prompt:**
- **P2 (erros):** conserta mojibake usando o inglês, tira prefixo, conserta typo, expande abreviação, ajusta composto.
- **P3 (limpeza):** aplica as regras de token — maiúscula, remove artigo/preposição/cópula/auxiliar/pronome/possessivo, singulariza, põe verbo na base, marca composto.
- **P4 (reorganização):** a parte que exige entender a frase inteira — tempo na frente, posição do WH, marca passado, escolha conceitual. Recebe **exemplos do ouro** (few-shot) pra ancorar a convenção.
- **P5 (validação):** confere contra a convenção; pode rodar o P4 N× pra medir confiança.

**Pontos fortes:** simples de montar; lida bem com regras que interagem (tudo na
mesma cabeça). **Fraquezas:** não-determinístico (às vezes erra o trivial —
omite pontuação, ou "traz de volta" uma palavra do texto), difícil de auditar
(não dá pra isolar a etapa que falhou), mais caro (vários prompts × N por linha).
**Papel:** baseline / protótipo.

---

## 4. Pipeline B2 — híbrido (funções + LLM)

**Ideia:** o que é **mecânico** vira **função determinística** (rápida, barata,
testável); só o que exige **entender a frase** vai pro LLM. A peça-chave é o
**ALIGN**: como a glosa não tem gramática, a gente parseia o **texto inglês**
(que tem) e "empresta" POS/lema/tempo pra cada token da glosa.

```
(texto, glosa)
   │
   ▼
 ALIGN          [função: spaCy + rapidfuzz]
   │   parseia o texto, casa cada token da glosa com a palavra no inglês
   ▼
 Stage 2  E2    [função: ftfy + alinhamento]
   │   conserta mojibake; reconstrói token corrompido a partir do inglês
   ▼
 Stage 3  E3–E6 + R1–R9   [função + spaCy]
   │   prefixo, MAIÚSCULA, artigo/preposição/cópula/auxiliar/pronome/possessivo,
   │   singular e verbo-base (via POS/lema do spaCy), composto, typo, pontuação
   ▼
 Stage 4  R10–R15         [LLM, 1 passada]
   │   reorganização da frase (tempo, WH, FINISH, conceitual) — o que precisa
   │   entender a frase inteira
   ▼
 Validador     [função]   confere tempo-na-frente e pontuação → status
   │
   gloss_output_hybrid
```

**O que falar de cada etapa:**
- **ALIGN (função):** "a glosa é maiúscula e reordenada, sem gramática; então eu
  analiso o texto inglês com o spaCy e ligo cada token da glosa à sua palavra de
  origem. É isso que deixa o resto ser determinístico."
- **Stage 2 — mojibake (função):** `ftfy` conserta o grosso; o que sobra corrompido
  é reconstruído a partir da palavra alinhada no inglês (`Sà\`NCHEZ`→`SANCHEZ`,
  `à?GER`→`OGER`). Irrecuperável → marca pra humano.
- **Stage 3 — limpeza (função + spaCy):** aplica as regras de token. As decisões
  que dependem de gramática usam o spaCy via alinhamento — ex.: só singulariza se
  a palavra no inglês é **substantivo no plural** (por isso **não** estraga nome
  próprio: `JAMES ELLES` fica), e só dropa `have` se for **auxiliar** (`have been`),
  mantendo o `HAVE` de posse.
- **Stage 4 — reorganização (LLM):** aqui mora o que é semântico/estrutural —
  tempo na frente, posição do WH, marca de passado, escolha conceitual do sinal.
  Uma chamada só, porque essas regras interagem.
- **Validador (função):** confere o verificável (tempo na frente, pontuação) e
  define o `status` (`ok`/`corrigida`/`humano`).

**Pontos fortes:** determinístico no trivial (mesma entrada → mesma saída),
barato, **auditável** (cada função tem teste; dá pra ver qual etapa mudou o quê),
LLM só onde precisa. **Fraquezas:** mais peças pra manter; o E4 é conservador
(typo herdado da fonte, tipo `therefore→REFORE`, pode passar — aí o LLM ou a
revisão humana pega). **Papel:** produção nas 81k linhas.

---

## 5. Função × LLM (a frase de efeito)

> **A função resolve o mecânico; o LLM resolve o que exige entender a frase.**

- **Função:** mojibake, prefixo, maiúscula, artigo, preposição, cópula, auxiliar
  (incl. `have` auxiliar), pronome sujeito, possessivo, singular, verbo-base,
  composto, pontuação. (No B2; no B1 isso é o Prompt 2 e 3.)
- **LLM:** posição do WH, tempo na frente, marca de passado (`FINISH`), escolha
  conceitual do sinal — e, no B1, **tudo**.

---

## 6. Um exemplo andando (mostra a diferença)

`Your blood test is ready now.` — glosa de entrada `YOUR BLOOD TEST READY NOW.`

- **B2 passo a passo:** Stage 3 dropa o possessivo `YOUR` (R6) → `BLOOD TEST READY NOW.`;
  Stage 4 (LLM) joga o tempo `NOW` pra frente (R10) → **`NOW BLOOD TEST READY.`** ✅
- **B1:** um prompt de limpeza + um de reorganização chegam no mesmo
  **`NOW BLOOD TEST READY`** (sem o `.` — o LLM tende a omitir pontuação).

Alvo da consultoria (`output_review`): `NOW BLOOD TEST READY.` → **B2 bateu exato.**

---

## 7. Resultado da avaliação (review set)

5 pares onde a glosa estava **errada** (`Output ≠ Output review`), fora do
few-shot. Entrada = `(texto, Output)`; alvo = `Output review`.

| texto | alvo (review) | B1 (LLM) | B2 (híbrido) |
|---|---|---|---|
| blood test | `NEED CHECK BLOOD TEST.` | `...TEST` (sem `.`) | `NEED CHECK BLOOD TEST.` ✅ |
| ready now | `NOW BLOOD TEST READY.` | `...READY` (sem `.`) | `NOW BLOOD TEST READY.` ✅ |
| lab test | `LABORATORY TEST NEED` | `NEED LABORATORY TEST` (ordem) | `NEED LABORATORY TEST` (ordem) |
| blood pressure | `HIGH BLOOD PRESSURE` | `HAVE HIGH BLOOD PRESSURE` (+HAVE) | `HIGH BLOOD PRESSURE.` ✅ |
| pneumonia | `DOCTOR NEED EXAMINE PNEUMONIA.` | `...PNEUMONIA` (sem `.`) | `DOCTOR NEED EXAMINE PNEUMONIA.` ✅ |

**Placar:** B2 (híbrido) **4/5 idênticos** ao ouro; B1 acerta o conteúdo mas
**perde pontuação** e teve 2 desvios (adicionou `HAVE`, e a ordem do `NEED`).

Dois aprendizados que viraram/podem virar regra (do ouro):
1. **`HAVE` de posse em afirmação cai** (`I have high blood pressure → HIGH BLOOD PRESSURE`), mas em pergunta fica (`do you have... → HAVE...?`). O B1 trouxe `HAVE` de volta — o B2 não.
2. **Ordem do `NEED`** (`LABORATORY TEST NEED` vs `NEED LABORATORY TEST`): o ouro varia — `plain.md` (R11) trata como "variação aceita".

---

## 8. Conclusão pra falar

- **B1 (só LLM):** simples, bom baseline, mas inconsistente no trivial (pontuação,
  trazer palavra de volta) e não-auditável.
- **B2 (híbrido):** mais fiel à convenção (4/5 exato), determinístico e
  auditável; o LLM entra só na reorganização. **É o recomendado pra produção.**
- **Tudo ancorado no ouro:** cada regra tem evidência nos pares revisados; o que o
  ouro não cobre fica pro LLM/`humano`, não para regra inventada.

---

## Apêndice — arquivos e execução

Código em `src/` (rodar com `PYTHONPATH=src`):
- `make_sample.py` (amostra seed=42) · `gloss_resources.py` (regras/few-shot/compostos) · `gloss_llm.py` (qwen3-32B compartilhado).
- `pipeline_llm/` = B1 (`prompts.py`, `pipeline.py`).
- `pipeline_hybrid/` = B2 (`align.py`, `mojibake.py`, `clean.py`, `reorder.py`, `validate.py`, `pipeline.py`).
- `run_pipelines.py` (200 da base) · `run_review_eval.py` (review set) · `csv_to_xlsx.py` (gera planilha pro Excel).

Rodar (container, A100 #2):
```bash
docker compose exec -T judge bash -lc '
PYTHONPATH=src uv run python -m run_review_eval \
  --review data/pares_review.csv --output data/processed/review_compare.csv'
```
Modelo: **qwen3-32B** (transformers, bf16, temp 0), carregado 1× e compartilhado
pelos dois pipelines. Estágio 1 (idioma, fastText) já roda no pré-processamento.
