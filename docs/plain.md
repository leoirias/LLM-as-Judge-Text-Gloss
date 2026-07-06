# Normalizador de Glosa ASL — Especificação

Recebe `(text, gloss)` e devolve a glosa na **convenção ouro** da consultoria.

- Entrada atual: `aslg-pc12` cru (~81.039 pares: `id, text, gloss`).
- Saída: `(id, text, gloss_normalizada, status)`, `status ∈ {ok, corrigida, humano}`.
- Veredito: saída == entrada → `ok`; mudou → `corrigida`; baixa confiança/irrecuperável → `humano`.

O documento tem três partes: (A) os erros e regras — fonte única de verdade; (B) dois pipelines que aplicam essas regras de formas diferentes; (C) a lista de compostos.

---

# PARTE A — Erros conhecidos e regras de normalização

Numeração estável (referenciada pelos dois pipelines).

## A.1 — Erros conhecidos

- **E1 — Idioma.** `text` não é inglês → remove o par da base e para.
- **E2 — Mojibake / encoding.** `�`, `?` no meio de palavra, à-crase, backtick, `?X-`. Conserta usando o `text` inglês como referência (`Ha?kmark`→`HOKMARK`). Irrecuperável → `humano`.
- **E3 — Prefixo indevido.** Remove `DESC-`, `X-`, `G-` (a convenção não usa prefixo).
- **E4 — Typo / token truncado.** Corrige (`gyneclogist`→`GYNECOLOGIST`, `nerlands`→`NETHERLANDS`). Ambíguo (`how`→`H`) → resolve pelo sentido da frase ou `humano`.
- **E5 — Abreviação.** Expande (`LAB`→`LABORATORY`, `SEC`→`SECOND`).
- **E6 — Composto mal marcado.** É composto real → `underscore`; não é → dois sinais (`BLOOD-TEST`→`BLOOD TEST`).

## A.2 — Regras de normalização

Limpeza token a token (remove/troca token):

- **R1** Tudo em MAIÚSCULAS.
- **R2** Remove artigo (`the`, `a`, `an`).
- **R2b** Remove preposição (`for`, `of`, `to`, `with`, `in`, `from`, `about`) — extraído do ouro (28/29 pares com preposição no texto removem todas: `ready for hospital admission`→`READY HOSPITAL ADMISSION`; `shortness of breath`→`...BREATH`). **Mantém quantificador** (`any`, `some`, `all`) — ouro: `HAVE ALLERGIC ANY MEDICINE?`. Lista conservadora (só as atestadas no ouro; `against`/`over`/... ficam até o gold dar evidência).
- **R3** Remove cópula "be" de ligação — **todas as formas** (`is`, `are`, `am`, `was`, `were`, `be`, `been`, `being`).
- **R4** Remove auxiliar de pergunta (`do`, `does`, `did`).
- **R4b** Remove `have`/`has`/`had` **auxiliar** (tempos perfeitos: `have been submitted`→`SUBMIT`; `has gone`→`GO`) — ouro: `how long have you been feeling dizzy?`→`DIZZY, HOW LONG FEEL?` (caem `have` e `been`). **Mantém** `HAVE` de posse/conteúdo (R12: `do you have pain`→`HAVE PAIN`).
- **R5** Remove pronome sujeito (`I`, `YOU`). **Exceção:** mantém quando a frase não tem verbo lexical (`HOW YOU?`, `WHERE YOU?`, `NOW YOU PAIN STRONG?`) ou o pronome é objeto (`NICE MEET YOU`).
- **R6** Remove possessivo (`YOUR`, `MY`) — inclusive parte do corpo/condição (`YOUR PNEUMONIA`→`PNEUMONIA`).
- **R7** Substantivo no singular (`ANTIBIOTICS`→`ANTIBIOTIC`).
- **R8** Verbo na forma base (`MOVING`→`MOVE`). O tempo verbal vira marcação na R13.
- **R9** Marca composto com `underscore` (lista da Parte C).

Reorganização da frase (precisa entender a frase inteira):

- **R10** Tempo na frente — `NOW`, `TODAY`, `TOMORROW`, `THIS_MORNING` vão pro começo (`...READY NOW`→`NOW ... READY`).
- **R11 — Posição do WH (corrigida).**
  - **Padrão: WH vai pro FIM, depois do verbo** — `When did your fever start?`→`FEVER START WHEN?`; `How are you feeling now?`→`NOW FEEL HOW?`; `When did the accident happen?`→`ACCIDENT HAPPEN WHEN?`; `What medicine are you taking?`→`USE MEDICINE WHAT?`.
  - **Exceção: pergunta sem verbo** (cópula caiu, sobra WH + um nome) → WH fica **na frente**: `How are you?`→`HOW YOU?`; `Where are you?`→`WHERE YOU?`; `What time is it?`→`WHAT TIME?`; `How much is this?`→`HOW_MUCH THIS?`.
  - **Topicalização:** tópico vai pra frente com vírgula e o WH continua no fim do comentário — `Where do you feel pain from the accident?`→`ACCIDENT, PAIN WHERE FEEL?`.
  - **Variação aceita:** a mesma frase pode aparecer das duas formas (`VOMIT WHEN?` e `WHEN VOMIT FINISH?`). O juiz NÃO deve reprovar a forma alternativa válida.
- **R12** Mantém verbo de conteúdo e modal — `HAVE`, `FEEL`, `CAN` não caem (`Can you breathe?`→`CAN BREATHE?`; `having a heart attack`→`HAVE HEART ATTACK?`).
- **R13** Passado/concluído com `FINISH` (e `PAST`) — (`When did you vomit?`→`WHEN VOMIT FINISH?`).
- **R14** Escolha conceitual do sinal, não literal (`shortness of breath`→`PROBLEM BREATH`).
- **R15** Preserva a pontuação conforme o tipo da frase (`.` afirmação, `?` pergunta).

---

# PARTE B — Os dois pipelines

Mesmas etapas, mesmas regras. A diferença é **quem executa**: só LLM (B1) ou funções + LLM (B2).

## B1 — Pipeline só LLM-as-judge (um prompt por etapa)

Sequência de chamadas de LLM. Cada prompt recebe o `text` + a glosa do passo anterior e devolve a glosa atualizada. Sem funções determinísticas.

```
INPUT (text, gloss)
  │
  ├─ Prompt 1 — Idioma           → "text é inglês? SIM/NÃO"   NÃO → descarta
  ├─ Prompt 2 — Erros conhecidos → aplica E2–E6 usando o text como referência
  ├─ Prompt 3 — Limpeza token    → aplica R1–R9
  ├─ Prompt 4 — Reorganização    → aplica R10–R15
  └─ Prompt 5 — Validação        → confere convenção; roda Prompt 4 N× p/ confiança
  │
OUTPUT (gloss_normalizada, status)
```

- **Prompt 1 — Idioma:** classifica o idioma do `text`. Não-inglês → `status=humano`/descarte, encerra.
- **Prompt 2 — Erros conhecidos:** instruções E2–E6. Conserta mojibake, tira prefixo, conserta typo, expande abreviação, ajusta composto. Saída: glosa limpa.
- **Prompt 3 — Limpeza token a token:** instruções R1–R9. Saída: glosa sem artigo/cópula/auxiliar/pronome/possessivo, em maiúscula, singular, verbo base, composto com underscore.
- **Prompt 4 — Reorganização:** instruções R10–R15 numa passada. Saída: glosa reordenada na convenção ouro.
- **Prompt 5 — Validação/confiança:** valida a glosa contra a convenção (few-shot dos pares ouro) e roda o Prompt 4 N vezes; concordância → confiança; baixa → `humano`.

Características: simples de montar, lida bem com casos que interagem. Custo alto (5 prompts × N por linha × 81k), não determinístico (pode "errar" coisa trivial como remover artigo), difícil de depurar (não dá pra isolar qual etapa falhou). Bom para **protótipo** e baseline.

## B2 — Pipeline híbrido (funções + LLM)

```
INPUT (text, gloss)
  │
  ▼
Stage 1 — Idioma              [função: fastText]     não-inglês → DESCARTA
  │  (inglês)
  ▼
ALIGN — spaCy (compartilhado) [função]   alinha text↔gloss; projeta POS/lema/tempo
  │
  ▼
Stage 2 — Mojibake (E2)       [função: ftfy + alinhamento]   irrecuperável → HUMANO
  │
  ▼
Stage 3 — Limpeza (E3–E6 + R1–R9)  [função + spaCy]
  │
  ▼
Stage 4 — Reorganização (R10–R15)  [LLM, 1 passada]   ← aqui mora o risco
  │
  ▼
Validador + confiança         [função DET + auto-consistência]   baixa conf. → HUMANO
  │
  ▼
OUTPUT (gloss_normalizada, status)
```

- **Stage 1 — Idioma:** `[função]` fastText LID. Não-inglês → descarta (E1).
- **ALIGN:** `[função]` spaCy parseia o `text`, alinha tokens text↔gloss, projeta POS/lema/tempo. Vem antes do Stage 2 (mojibake usa o alinhamento) e antes do Stage 3 (o tempo projetado alimenta a R13).
- **Stage 2 — Mojibake:** `[função]` ftfy + reconstrução pelo alinhamento. Irrecuperável → `humano`.
- **Stage 3 — Limpeza token a token:** `[função + spaCy]` E3 (prefixo), E4 (typo), E5 (abreviação), E6 (composto), R1–R9. R3/R4/R5 usam spaCy; R7/R8 usam lema do spaCy. R5 pode chamar LLM só no caso de fronteira.
- **Stage 4 — Reorganização:** `[LLM, 1 passada]` R10–R15 juntas. As regras interagem (tempo + WH + dropar sujeito ocorrem na mesma frase), por isso uma chamada só.
- **Validador + confiança:** `[função]` confere o verificável (tempo na frente, pontuação) como validador, não mutador; confiança por auto-consistência (roda o Stage 4 N×); baixa → `humano`. Calibrar o limiar na base de teste.

Características: determinístico no trivial, barato, depurável (cada função tem unit test), LLM só onde precisa entender a frase. Mais peças pra manter. **Recomendado para a produção** nas 81k linhas.

## Recomendação prática

Protótipar em **B1 num sample de ~200 linhas** para mapear os casos difíceis e validar as regras; rodar a produção em **B2**. Independente do pipeline, manter sempre um **validador determinístico + auto-consistência** no fim — é de onde sai a confiança e o corte para `humano`.

> Nota de desenho: ambos acima normalizam o corpus (entrada = aslg-pc12 cru). Se a entrada virar a saída do modelo do colega (validar em vez de normalizar), acrescentar um juiz independente no fim — obrigatoriamente um modelo diferente do que normalizou (evita viés de auto-preferência).

---

# PARTE C — Compostos (R9 / E6)

## C.1 — Compostos reais da consultoria (`underscore`)

Extraídos do gold revisado. São a **verdade** para R9:

```
HOW_MUCH   NO_PROBLEM   NOT_UNDERSTAND   PASS_OUT   THANK_YOU   THIS_MORNING   WRITE_DOWN
```

Regra: composto real (não-composicional) → `underscore`. Sequência composicional → sinais separados (`BLOOD TEST`, `GO HOME`, `BODY SHAKE`).

---

# Pontos em aberto

- **R11 (WH):** 1. A regra do WH (extraída dos dados — e corrige o que eu tinha escrito)
São 18 frases com WH no gold. O padrão real:

Padrão: o WH vai pro FIM, depois do verbo. When did your fever start? → FEVER START WHEN?; How are you feeling now? → NOW FEEL HOW?; When did the accident happen? → ACCIDENT HAPPEN WHEN?; What medicine are you taking? → USE MEDICINE WHAT?.
Exceção: pergunta sem verbo (a cópula caiu e sobra só WH + um nome) → o WH fica na frente, porque não tem verbo pra ele ir atrás: How are you? → HOW YOU?; Where are you? → WHERE YOU?; What time is it? → WHAT TIME?; How much is this? → HOW_MUCH THIS?.
Tópico vai pra frente com vírgula, e o WH continua no fim do comentário: Where do you feel pain from the accident? → ACCIDENT, PAIN WHERE FEEL?.
- **Lista de compostos (C.1):** ampliar conforme o gold crescer 
- **Métrica de `status`:** com input cru quase tudo sai `corrigida`. Considerar separar "corrigida no Stage 3" de "corrigida no Stage 4" para ver onde o trabalho aconteceu.
