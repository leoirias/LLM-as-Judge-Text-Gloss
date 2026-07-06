# Pontos de Discussão — Consultoria (Tânia / Jean)

Dúvidas em aberto da convenção de glosa ASL. Cada ponto: **pergunta**, **o que
os dados mostram** e **exemplos**. (Jean = intérprete surdo, decisão final.)

Legenda: 🔴 aberto (precisa do Jean) · 🟢 resolvido.

---

## 1. 🔴 Pronome objeto — cai ou fica?

**O que já está decidido:** pronome **sujeito** cai (quem faz a ação).
- Sujeito: "**I** need help", "**you** need antibiotics" → o `I`/`YOU` cai.

**A dúvida é o pronome OBJETO** (quem *recebe* a ação):
- Objeto: "the doctor will help **you**", "nice to meet **you**" → aqui `you` é objeto.

O documento mostrou o objeto de **dois jeitos**:

| Inglês | Glosa | `you` (objeto) |
|---|---|---|
| See you soon | `SEE SOON` | **caiu** |
| Nice to meet you | `NICE MEET YOU` | **ficou** |

**Nossa hipótese:** pode depender de **verbo direcional** — em ASL, verbos como
MEET "apontam" pro objeto (o movimento já inclui o "você"), então o `YOU` é
significativo e fica; já SEE-SOON é mais uma despedida fixa.

**Pergunta pro Jean:** o pronome objeto cai sempre, fica sempre, ou **depende do
verbo ser direcional**? Se depender, quais verbos são direcionais no contexto médico?

---

## 2. 🟢 Divisão em duas orações — RESOLVIDO

Já está claro: quando a glosa tem duas partes (`TAKE MEDICINE, NOW FEEL BETTER?`),
isso **vem do próprio inglês**, que já tinha duas orações
("Did you take the medicine, do you feel better now?"). **Não é o sistema
dividindo** — ele só preserva as orações que já existem. Sem regra nova.

---

## 3. 🔴 Compostos com underscore — NÃO existe lista

Ponto esclarecido: **não existe uma lista fixa de sinais compostos em ASL** —
composto é lexicalização, decidido caso a caso por quem sinaliza.

**Consequência pra regra:** o sistema **não pode inventar** composto. Então:
- **Padrão = dois sinais separados** (`SMALL TOWN`, `BLOOD TEST`, `GO HOME`).
- Só usar underscore nos poucos **já confirmados** (`THANK_YOU`, `THIS_MORNING`,
  `PASS_OUT`, `WRITE_DOWN`, `NO_PROBLEM`, `NOT_UNDERSTAND`, `HOW_MUCH`).
- `SMALL_TOWN` (que o modelo inventou) → deve virar `SMALL TOWN`.

**Pergunta pro Jean:** como identificar um composto real caso a caso (só ele
sabe)? Ou seguimos com "sempre separado, exceto os poucos confirmados"?

---

## 4. 🔴 Futuro / "will" — o ouro é INCONSISTENTE

Olhando os 4 casos revisados (coluna `Output review`):

| Inglês | Glosa revisada | `will` | marcador temporal? |
|---|---|---|---|
| I will call the doctor | `CALL DOCTOR` | **caiu** | não |
| The doctor will give you medicine now | `NOW DOCTOR GIVE MEDICINE` | **caiu** | sim ("now") |
| The doctor will explain your situation | `DOCTOR WILL EXPLAIN SITUATION` | **ficou** | não |
| How long will I stay here? | `STAY HERE HOW LONG?` | **caiu** | não |

**Regra inferida (a confirmar com o Jean — são só 4 exemplos):**
- `will` **CAI** se houver **noção de tempo** (`now`, `tomorrow`, `how long`…) **OU**
  se a ação for **1ª pessoa** (eu/nós vou fazer → intenção própria, futuro implícito).
- `will` **FICA** (na posição normal, antes do verbo) **só** quando **não há tempo E**
  a ação é de **3ª pessoa** (ele/ela/o médico vai fazer).

Confere com os 4 casos: `I will call → CALL DOCTOR` (1ª pessoa, cai);
`...give medicine now → NOW...` (tem tempo, cai); `The doctor will explain →
DOCTOR WILL EXPLAIN` (3ª pessoa, sem tempo, fica); `How long will I stay →
STAY HERE HOW LONG?` (tem "how long", cai). Já codifiquei essa regra no P3.

**Pergunta pro Jean:** essa regra (tempo OU 1ª pessoa → cai; 3ª pessoa sem tempo →
fica) procede? São poucos exemplos pra ter certeza.

---

## 5. 🔴 Modais (CAN, SHOULD…) — não é unânime, e faltam dados

Dos dados revisados:
- **CAN:** aparece 7×, **mantido em 5**, **caiu em 2**. E os 2 que caíram são
  "Can you explain…", mas um terceiro "Can you explain **the result**?" **manteve**.
  → mantém na maioria, **mas não é unânime**.
- **SHOULD, MUST, MAY, WOULD, COULD:** **não aparecem** no ouro. Nossa regra de
  "mantém SHOULD" é um **chute** (sem evidência).

| Inglês | Glosa | `can` |
|---|---|---|
| Can you breathe? | `CAN BREATHE?` | ficou |
| Can you help me now? | `CAN HELP NOW?` | ficou |
| Can you explain the result? | `CAN RESULT EXPLAIN?` | ficou |
| Can you explain the blood test? | `BLOOD TEST EXPLAIN?` | **caiu** |
| Can you explain my condition? | `CONDITION EXPLAIN?` | **caiu** |

**Pergunta pro Jean:** (a) `CAN` fica sempre? Por que "Can you explain X?" às
vezes cai? (b) e `SHOULD/MUST/MAY/WOULD` — ficam como conteúdo (`SHOULD REST`)?

---

## 6. 🟢 Preposição de localização física — RESOLVIDO (manter)

**Regra normal:** preposição cai (`for/of/to/with/in/from`).
- `pain in my chest → CHEST PAIN` (o "in" cai).

**Exceção (decidida, conforme a consultoria/Struxness):** quando a preposição
marca um **lugar físico específico**, ela **fica**.
- ex.: `the medicine is in the drawer → MEDICINE IN DRAWER` (mantém o `IN`).

Já está no P2 (R3). *(Ainda vale pedir ao Jean 1-2 exemplos médicos reais pra
calibrar o que conta como "lugar físico".)*

---

## 7. 🟢 Pontuação — RESOLVIDO

Decidido: **a pontuação é sempre mantida igual ao texto em inglês** (`.` afirmação,
`?` pergunta); só se trata como **erro de digitação** quando for claramente typo.
Já apliquei essa regra no pipeline (P3).

---

## 8. 🔴 Plural (com número / quantificador)

**Regra:** ASL prefere **singular** — o "-s" do inglês cai (`antibiotics → ANTIBIOTIC`).

**A dúvida:** quando o plural **importa** (tem número ou quantificador), como marcar?
Em ASL o plural é mostrado pelo **número/quantificador** ou pela **repetição do
sinal**, não pelo "-s".

| Inglês | Glosa provável |
|---|---|
| two blood tests | `TWO BLOOD TEST` (número + singular) |
| many people | `MANY PEOPLE` |

**Pergunta pro Jean:** basta manter o número/quantificador + substantivo no
singular? Existe caso de **repetir o sinal** pra marcar plural?
*(provavelmente já resolvido: número/quantificador + singular — só confirmar)*
