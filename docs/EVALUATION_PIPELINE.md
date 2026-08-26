# Pipeline de Avaliação do Juiz

Como um par (frase em português, glosa) vira um veredito com regra citada por ID
— e por que a acurácia de 100% que medimos não é real.

Documento 2 de 2 — o companheiro é [EXTRACTION_PIPELINE.md](EXTRACTION_PIPELINE.md).
Atualizado em 21/08/2026.

---

## 1. Visão geral

O juiz recebe uma frase, uma glosa e a base de regras construída pelo pipeline de
extração. Devolve um veredito citando as regras por ID real. Existe só para
Libras por enquanto.

Cada frase é julgada em um **prompt isolado**, sem histórico entre chamadas — o
veredito de uma frase não pode influenciar o da seguinte.

```
  base de regras                                       ┌──────────────────────────┐
  voice2sign_final.csv ──┐                        ┌───▶│ valido                   │
                         │                        │    │ fidelidade e estrutura OK│
                         ├──▶ prompt do juiz ─────┤    └──────────────────────────┘
  par a julgar           │    1 chamada/frase     │
  frase PT + glosa ──────┘    sem histórico       │    ┌──────────────────────────┐
                                   │              ├───▶│ invalido                 │
                                   ▼              │    │ viola regra citada       │
                            JSON, 6 campos        │    └──────────────────────────┘
                            veredito              │
                            representa_sentido    │    ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
                            natural_estrutura     └───▶  nao_coberto
                            regras                     │ nenhuma regra cobre     │
                            problema                     └ ─ ─ ─ ─ ─ ┬ ─ ─ ─ ─ ─ ┘
                            sugestao                                 │
                                   │                                 ▼
                                   ▼                    ┌──────────────────────────┐
                          parse tolerante               │ FORA do cálculo de       │
                          aceita sinônimo               │ acurácia — abstenção não │
                          deriva veredito das dimensões │ é acerto nem erro        │
                                                        └──────────────────────────┘
```

Se o parse falhar de vez, a linha vira `nao_coberto` com `Origem=parse_falhou` —
distinto de abstenção por falta de regra. Se o modelo citar um ID que não existe
na base, o runner avisa: é sinal de alucinação de identificador.

---

## 2. Arquivos

Diretório autocontido em `libras_pipeline/evaluation/`, sem import cruzado com as
outras etapas.

| Arquivo | Responsabilidade |
|---|---|
| `run.py` | CLI do juiz. Monta o prompt por frase, chama o modelo, parseia, escreve o CSV e imprime o resumo |
| `prompts/judge.yaml` | o prompt, em fragmentos: objetivo · dimensões · abstenção · uso de regras · formato de saída |
| `rules_store.py` | carrega `voice2sign_final.csv` e renderiza o bloco de regras injetado no prompt; expõe também o conjunto de IDs válidos |
| `parsing.py` | parse tolerante: remove `<think>`, extrai o JSON, normaliza sinônimos, deriva o veredito das dimensões |
| `schema.py` | `JudgeVerdict` e o conjunto `ESTADOS`; valida o veredito na construção |
| `llm.py` | monta o `ModelConfig` e devolve o cliente |
| `prompt.py` | carrega o YAML de fragmentos e renderiza o template |
| `config.yaml` | modelo e geração — `max_new_tokens: 1024`, menor que na extração porque a resposta é só o JSON |
| `smoke_qwen38.py` | pré-voo: falha explicitamente se detectar peso inicializado aleatoriamente |
| `data/frases_teste.csv` | os pares a julgar, com `esperado` e `fonte` |
| `output/resultado*.csv` | um arquivo por experimento, mais o `.raw.txt` com a resposta crua de cada frase |

> **Por que `run.py` e não `judge.py`.** Com `PYTHONPATH=src`, um arquivo local
> chamado `judge.py` sombrearia o pacote `src/judge/` — usado por `prompt.py`
> para renderizar templates — e quebraria o import.

### Como a base de regras entra no prompt

`rules_store.py` lê o CSV final e renderiza cada regra como um bloco com o ID
visível, que é o que permite ao modelo citá-lo:

```
[LIBRAS.SINTAXE.001] Ordem básica SVO  (sintaxe)
  A ordem básica (canônica) da frase na Libras é Sujeito-Verbo-Objeto (SVO).
  gatilho: frase declarativa simples, sem elementos adicionais
  exemplos: EU GOSTAR FUTEBOL
```

A base cresce sozinha: linhas novas em `voice2sign_final.csv` aparecem no prompt
sem tocar em código. O `--rules` aponta para outro CSV, que é o mecanismo usado
para comparar bases diferentes.

---

## 3. Os três estados

| Estado | Significado | Entra na acurácia? |
|---|---|---|
| `valido` | fidelidade e estrutura OK | sim |
| `invalido` | viola alguma regra citada | sim |
| `nao_coberto` | **nenhuma regra cobre o fenômeno** — abstenção honesta, não reprovação | **não** |

A abstenção fica **fora do cálculo** porque não é acerto nem erro: é o juiz
dizendo que a base de regras não alcança aquele caso. Contá-la como erro puniria
a honestidade; contá-la como acerto premiaria o silêncio. O `run.py` reporta a
taxa de abstenção separadamente, e a acurácia é calculada só sobre os
não-abstidos.

Há uma distinção operacional importante: quando o parse falha de vez, a linha
também vira `nao_coberto`, mas com `Origem=parse_falhou` em vez de `llm`. Isso
separa "o juiz se absteve" de "a resposta não deu para ler" — dois problemas com
causas e correções diferentes.

---

## 4. O prompt do juiz

Cinco fragmentos montados por um template, em `prompts/judge.yaml`.

| Fragmento | O que estabelece |
|---|---|
| `objetivo` | o papel — validador de glosa. Define que uma glosa correta "representa o sentido de forma fluida e natural para surdos", e que a glosa é a sequência de sinais a serem feitos |
| `dimensoes` | as duas dimensões julgadas: **fidelidade** (preserva o sentido?) e **naturalidade/estrutura** (respeita as regras?) |
| `abstencao` | se nenhuma regra cobrir o fenômeno, responder `nao_coberto` — e a instrução explícita de que abster-se não é reprovar |
| `uso_regras` | baseie-se *somente* nas regras listadas; cite o **ID exato**, não descreva a regra em texto livre; várias podem valer ao mesmo tempo |
| `output_rules` | os seis campos obrigatórios, um JSON em uma linha, sem markdown e sem prosa fora do objeto |

### Os seis campos obrigatórios

```
"veredito"           EXATAMENTE "valido" | "invalido" | "nao_coberto"
                     (não "aprovado", "correto", "reprovado")
"representa_sentido" EXATAMENTE "Sim" ou "Não" — preserva o sentido?
"natural_estrutura"  EXATAMENTE "Sim" ou "Não" — respeita as regras?
"regras"             lista de IDs citados; [] se nenhuma
"problema"           motivo curto se invalido/nao_coberto; "" se valido
"sugestao"           glosa corrigida se invalido; "" caso contrário
```

O prompt inclui um exemplo do *formato* do JSON — com uma frase fictícia e um ID
fictício (`XX.EXEMPLO.0`, `<motivo curto aqui>`), e o aviso explícito de que nada
dele deve ser usado como resposta. Isso não é zelo excessivo: a versão anterior
desse exemplo continha uma glosa que era a resposta de um dos casos de teste.

O fragmento `output_rules` também proíbe nominalmente o campo `justificativa`,
porque o modelo tendia a inventá-lo em vez de usar `problema`.

---

## 5. Parse tolerante

O modelo inventa nome de campo e sinônimo de veredito. O parser absorve isso em
vez de descartar a resposta.

- **Remove `<think>`**, inclusive o caso de bloco aberto sem fechar por estouro
  de tokens.
- **Extrai o JSON** varrendo o texto a partir de cada `{` e tentando
  `raw_decode` — funciona mesmo com prosa antes ou depois.
- **Normaliza sinônimos de veredito** sem acento e em minúscula: `aprovado`,
  `correto`, `certo`, `ok`, `sim` → `valido`; `reprovado`, `rejeitado`,
  `incorreto`, `errado`, `negado`, `nao` → `invalido`.
- **Deriva o veredito das dimensões** quando o campo `veredito` não vem: qualquer
  "Não" em fidelidade ou estrutura resulta em `invalido`.
- **Falha explícita** (`JudgeParseError`) quando não há JSON nenhum — e aí o
  `run.py` marca `Origem=parse_falhou`.

O `schema.py` valida na construção: um veredito fora de
`{valido, invalido, nao_coberto}` levanta `VerdictError`. O parser é tolerante na
entrada e estrito na saída.

---

## 6. Conjunto de teste

Oito pares em `data/frases_teste.csv`, com o veredito esperado e a origem.

| Frase (português) | Glosa | Esperado | Fonte |
|---|---|---|---|
| Quando a dor começou? | `DOR COMEÇAR QUANDO?` | valido | libras_teste |
| Quando a dor começou? | `QUANDO DOR COMEÇAR?` | invalido | libras_teste |
| Posso ir para casa hoje? | `EU PODER IR PARA CASA HOJE` | invalido | libras_teste |
| Bebeu água suficiente? | `BEBER ÁGUA SUFICIENTE?` | valido | libras_teste |
| Comeu algo estranho? | `COMER ESTRANHO ALGO?` | invalido | libras_teste |
| Pode explicar o tratamento? | `PODER EXPLICAR TRATAMENTO` | valido | grammar_tania |
| Posso ir para casa hoje? | `EU PODER IR CASA HOJE` | valido | grammar_tania |
| Chamar a enfermeira, agora. | `ENFERMEIRA CHAMAR AGORA` | valido | grammar_tania |

Os pares testam fenômenos específicos: **item-QU no fim** (frases 1–2, a mesma
frase com a ordem invertida), **preposição locativa nula** (3 × 7,
`IR PARA CASA` versus `IR CASA`), **omissão de pronome** (4, 6) e **ordem do
advérbio** (5).

> **As oito frases vêm do mesmo documento.** Cinco de `libras_teste.csv` e três
> das sentenças-exemplo da gramática da Profa. Tânia — todas do mesmo PDF de
> consultoria. São 5 literais mais 3 perturbações deliberadas. **O conjunto não
> mede generalização**: mede se o juiz reproduz as convenções de um único
> documento. Frases de fonte independente são a principal lacuna para uma
> avaliação real.

---

## 7. Resultados medidos

Dez rodadas registradas. A leitura correta delas depende de um detalhe que só
apareceu depois.

| Rodada | Base de regras | Regras | Acurácia | Distribuição |
|---|---|---:|---:|---|
| `resultado_tania` | só Tânia | 7 | 8/8 = 100% | 5 válido, 3 inválido |
| `resultado_combinado` | Tânia + livros | 56 | 8/8 = 100% | 5 válido, 3 inválido |
| `resultado_livros` | só livros | 49 | **3/8 = 37%** | 8 inválido |
| `resultado_v2_tania` | só Tânia | 7 | 8/8 = 100% | 5 válido, 3 inválido |
| `resultado_v2_combinado` | Tânia + livros | 56 | 8/8 = 100% | 5 válido, 3 inválido |
| `resultado_v2_livros` | só livros | 49 | **2/8 = 25%** | 7 inválido, 1 válido |
| `resultado_v3_tania_semex` | Tânia, **sem exemplos** | 7 | **5/6 = 83%** | 2 válido, 4 inválido, 2 não coberto |
| `resultado_v3_combinado_semex` | combinada, **sem exemplos** | 56 | **4/8 = 50%** | 3 válido, 5 inválido |
| `resultado_qwen3-30b-a3b` | modelo anterior | — | 5/8 = 62% | 6 válido, 2 inválido |

### Por que os 100% não são reais

As regras extraídas das notas da Tânia trazem, no campo `exemplos`, as próprias
frases do documento. E o conjunto de teste veio desse mesmo documento.
Verificação direta:

| Base | Regras | Glosas de teste presentes nos exemplos |
|---|---:|---:|
| `tania_voice2sign_final.csv` | 7 | **5 de 8** |
| `combinado_voice2sign_final.csv` | 56 | **5 de 8** |
| `tania_semex_voice2sign_final.csv` | 7 | 0 |
| `combinado_semex_voice2sign_final.csv` | 56 | 0 |
| `voice2sign_final.csv` | 49 | 0 |

As glosas `DOR COMEÇAR QUANDO?`, `BEBER ÁGUA SUFICIENTE?`,
`PODER EXPLICAR TRATAMENTO` e `EU PODER IR CASA HOJE` aparecem **verbatim** dentro
das regras que o juiz recebe. Ele não estava aplicando a regra — estava
reconhecendo a resposta.

Removendo os exemplos, o resultado muda de forma reveladora: **Tânia cai de 100%
para 83%**, mas passa a se abster em 2 dos 8 casos, o que é o comportamento
correto quando a base tem 7 regras. E a **base combinada desaba de 100% para
50%** — as 49 regras dos livros, ao serem somadas, *pioram* o juiz em vez de
ajudar.

> **O número honesto é 83%, com 7 regras e 2 abstenções.** Todos os resultados de
> 100% dependem do vazamento. E a comparação entre bases só é válida entre as
> variantes `semex`.

### Gramática descritiva rende juiz ruim

A base de 49 regras vinda dos dois livros acadêmicos produz **25% de acurácia**,
reprovando frases válidas — 7 ou 8 dos 8 casos marcados como inválidos. A causa
não é o extrator: é o tipo de fonte.

Gramáticas descritivas afirmam o que a língua *permite* ("a ordem SVO é a mais
comum", "o item-QU pode aparecer no fim"). Elas não escrevem proibições —
ninguém publica "a preposição nunca aparece na glosa", porque isso é óbvio para
quem já sabe a língua. Mas é exatamente esse enunciado que um validador precisa.

Verificamos que a lacuna é da fonte, não da extração: em 568 páginas dos dois
livros há 3 menções incidentais a preposição, nenhuma delas afirmando a regra. As
notas de consultoria, que são **prescritivas**, dão 7 regras que sozinhas rendem
mais que as 49 descritivas.

---

## 8. Erros encontrados

### O schema nunca chegava ao modelo

O fragmento `@{output_rules}` — que define os seis campos obrigatórios — **não
estava no template**. O prompt era montado sem ele, então o modelo nunca via a
especificação de saída. Sintoma: as colunas `Fidelidade`, `Problema` e `Sugestao`
saíam vazias em 8 de 8 frases.

O mesmo defeito existia no `survey_pipeline`, onde causou 5 de 5 falhas de parse.
Foi herdado junto com o código.

### O prompt continha a resposta

O exemplo de formato JSON dentro de `output_rules` trazia
`"sugestao":"DOR COMEÇAR QUANDO?"` — que é exatamente a glosa correta do caso de
teste nº 2. O modelo podia copiá-la sem aplicar regra nenhuma.

Corrigido: o exemplo passou a usar ID fictício (`XX.EXEMPLO.0`) e placeholders
(`<motivo curto aqui>`), com aviso explícito de que nada dele deve ser usado como
resposta.

### Vazamento pelas regras, não pelo prompt

Este é o mais sutil e continua **em aberto**: mesmo com o prompt limpo, as glosas
de teste chegavam ao modelo pelo campo `exemplos` das regras. O contorno foi gerar
variantes `semex` das bases, sem exemplos — mas isso custa informação legítima, já
que exemplo é útil para o juiz entender a regra.

A solução real é um conjunto de teste de fonte independente das regras. Enquanto
ele não existir, qualquer base derivada das notas da Tânia vaza no teste atual.

### Resumo

| Problema | Sintoma | Estado |
|---|---|---|
| `@{output_rules}` fora do template | modelo nunca via o schema; 3 colunas vazias em 8/8 | corrigido |
| exemplo do prompt continha uma glosa de teste | vazamento de gabarito | corrigido |
| glosas de teste nos `exemplos` das regras | 100% inflado; cai para 83% sem os exemplos | **em aberto** — inerente à fonte |
| modelo cita ID inexistente | alucinação de identificador | detectado e avisado |
| modelo inventa o campo `justificativa` | motivo fora do campo esperado | proibido no prompt |
| sinônimo de veredito (`aprovado`, `reprovado`) | veredito não reconhecido | normalizado no parse |
| checkpoint multimodal como CausalLM | risco de pesos aleatórios silenciosos | coberto pelo pré-voo |
| eixo de comparação inválido | uma análise comparou a classificação de não-manuais contra um baseline já corrigido à mão | descartada |

---

## 9. Pré-voo

`smoke_qwen38.py` — rodar antes da primeira avaliação com um modelo novo.

```bash
docker compose exec -e CUDA_VISIBLE_DEVICES=3 judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/evaluation/smoke_qwen38.py'
```

Quatro checagens, e a segunda é a que justifica o script existir:

1. **Carrega pelo cliente do projeto** e reporta `model_id`, classe instanciada e
   `dtype` — confirma que o caminho de carregamento é o mesmo da produção.
2. **Algum peso foi inicializado aleatoriamente?** Captura os avisos do
   `transformers` e **falha explicitamente** se detectar. Carregar um checkpoint
   multimodal com `AutoModelForCausalLM` pode inicializar pesos em silêncio, e o
   modelo responde — mal, sem erro nenhum.
3. **Thinking está desligado?** Gera uma saída curta e verifica se não há bloco
   `<think>`.
4. **O prompt real do juiz volta JSON parseável?** Monta o prompt de verdade, com
   a base de regras, e confere que o retorno parseia e cita IDs que existem.

---

## 10. Como rodar

```bash
docker compose exec -e CUDA_VISIBLE_DEVICES=3 judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/evaluation/run.py'
```

| Flag | Efeito |
|---|---|
| `--rules <csv>` | qual base de regras usar (default `voice2sign_final.csv`) |
| `--exp-name X` | grava em `output/resultado_X.csv` em vez de sobrescrever |

Sempre use `--exp-name` ao comparar bases — sem ele, `resultado.csv` é
sobrescrito e a rodada anterior se perde.

### Saída

`Texto · Glosa · Estado · Fidelidade · Naturalidade · Regras · Problema ·
Sugestao · Esperado · Acertou · Origem`, mais `resultado_*.raw.txt` com a
resposta crua de cada frase.

O resumo impresso traz a distribuição de estados, a **taxa de abstenção**
separada, e a acurácia calculada só sobre os não-abstidos.

---

## 11. Possibilidades de avanço

1. **Conjunto de teste independente.** É a lacuna que domina todas as outras: com
   8 frases do mesmo documento que gerou as regras, nenhum número atual mede
   generalização. Corpora paralelos existem — o *Libras-UFPel* (2.400 sentenças,
   1.200 com glosa completa, com pesquisadores surdos em todas as etapas,
   aguardando liberação) e o *VLibrasBD* (127 mil pares, já disponível, mas sem
   QA documentado).
2. **Camada determinística antes do juiz.** Parte das regras é checável por
   código — presença de preposição na glosa, posição do item-QU, presença de
   artigo. Um `checks.py` resolveria esses casos sem chamar o modelo, e o LLM
   ficaria com o resíduo. Exige formalizar as regras num formato verificável, o
   que hoje não existe.
3. **Fontes prescritivas.** 7 regras de consultoria valem mais que 49 de livro.
   Vale mapear e extrair mais material prescritivo — o trabalho da UFPB que
   sustenta o VLibras tem regras formalizadas, ainda que as regras em si não
   estejam publicadas.
4. **Protocolo de avaliação da literatura.** Existe metodologia multinível
   publicada para avaliar tradutores de língua de sinais brasileira, incluindo
   estudo de caso com o VLibras. Adotá-la evita reinventar o protocolo.
5. **Análise sintática antes das regras.** O trabalho da UFPB mede que rotular a
   função sintática de cada palavra antes de aplicar as regras foi a contribuição
   decisiva (82% × 45% de compreensão). Hoje o juiz recebe a glosa crua.
6. **Análise por fenômeno, não só agregada.** Com 8 frases, a acurácia agregada
   esconde qual regra funcionou. Um teste com vários casos por fenômeno diria
   qual parte da base é confiável.
7. **Espelhar para ASL.** O pipeline de avaliação existe só para Libras; o ASL
   tem extração e simplificação, mas nenhum juiz.
8. **Reprocessar com a base nova.** Todos os resultados acima usam bases da
   extração anterior. A etapa de simplificação nunca foi refeita com os dados
   novos.


---

## 12. Passo a passo detalhado do juiz

Cada frase percorre sete etapas. As cinco primeiras montam a pergunta; as duas
últimas interpretam a resposta.

```
┌─ 1. CARREGAR A BASE ─────────────────────── rules_store.py ─────────────┐
│  lê o CSV (--rules) e renderiza um bloco por regra, com o ID visível:    │
│                                                                          │
│     [TANIA.M.002] Item QU na posição final  (pergunta)                   │
│       O item QU aparece no FINAL da sentença, ocupando função de ADJV.   │
│       gatilho: a frase é interrogativa com item QU                       │
│       exemplos: Onde dói? -> DOER ONDE?                                  │
│                                                                          │
│  guarda também o conjunto de IDs válidos, para detectar alucinação       │
└──────────────────────────────────────────────┬───────────────────────────┘
                                               │
┌─ 2. MONTAR O PROMPT ───────── prompts/judge.yaml ─────────────────────────┐
│  objetivo · dimensões · abstenção · uso_regras                           │
│    + bloco de regras (passo 1)                                           │
│    + frase em português  +  glosa proposta                               │
│    + output_rules (os 6 campos obrigatórios)                             │
│  UM prompt por frase, montado do zero — sem histórico entre frases       │
└──────────────────────────────────────────────┬───────────────────────────┘
                                               │
┌─ 3. GERAR ────────────────────────────────── llm.py ─────────────────────┐
│  Qwen3.8-27B, thinking desligado, do_sample=false, max_new_tokens=1024   │
│  a resposta crua vai para resultado_<exp>.raw.txt antes de qualquer parse│
└──────────────────────────────────────────────┬───────────────────────────┘
                                               │
┌─ 4. PARSE TOLERANTE ──────────────────────── parsing.py ─────────────────┐
│  remove <think> · varre o texto a partir de cada { e tenta raw_decode    │
│  normaliza sinônimos: aprovado/correto/ok -> valido                      │
│                       reprovado/rejeitado -> invalido                    │
│  se faltar o campo veredito, DERIVA das duas dimensões:                  │
│       qualquer "Não" em fidelidade ou estrutura  ->  invalido            │
│  falhou de vez? -> nao_coberto com Origem=parse_falhou                   │
└──────────────────────────────────────────────┬───────────────────────────┘
                                               │
┌─ 5. VALIDAR O VEREDITO ───────────────────── schema.py ──────────────────┐
│  JudgeVerdict aceita só {valido, invalido, nao_coberto};                 │
│  qualquer outra coisa levanta VerdictError                               │
│  (tolerante na entrada, estrito na saída)                                │
└──────────────────────────────────────────────┬───────────────────────────┘
                                               │
┌─ 6. CHECAR OS IDs CITADOS ────────────────── run.py ─────────────────────┐
│  todo ID em "regras" tem que existir na base carregada no passo 1;       │
│  se não existir, imprime aviso — é alucinação de identificador           │
└──────────────────────────────────────────────┬───────────────────────────┘
                                               │
┌─ 7. CONTABILIZAR ─────────────────────────── run.py ─────────────────────┐
│  valido / invalido  ->  entra na acurácia (compara com `esperado`)       │
│  nao_coberto        ->  FORA da acurácia, conta na taxa de abstenção     │
│                                                                          │
│  saída: resultado_<exp>.csv                                              │
│    Texto · Glosa · Estado · Fidelidade · Naturalidade · Regras ·         │
│    Problema · Sugestao · Esperado · Acertou · Origem                     │
└──────────────────────────────────────────────────────────────────────────┘
```

### Por que a abstenção fica fora da acurácia

Um validador que sempre dá veredito mente quando não sabe. Contar `nao_coberto`
como erro puniria a honestidade; contar como acerto premiaria o silêncio. As
duas métricas são reportadas **separadas**:

- **acurácia** = acertos ÷ frases julgadas (não-abstidas)
- **taxa de abstenção** = abstenções ÷ total de frases

Uma base pode ter 100% de acurácia com 62% de abstenção — foi o que aconteceu
com a base do livro. É um resultado bom e ruim ao mesmo tempo, e só as duas
métricas juntas mostram isso.

---

## 13. Experimento das quatro bases

Quatro bases, mesmas 8 frases, mesmo prompt, mesmo modelo. Só a base muda.

| Base | Regras | Origem |
|---|---:|---|
| `base1_tania` | 10 | notas de consultoria, **extração manual** |
| `base2_livro` | 179 | Gramática da Libras, partes 1 e 2 (caps. 5, 7, 8) |
| `base3_combinada` | 189 | Tânia + livro |
| `base4_parte2` | 79 | só a parte 2 (sintaxe, caps. 7 e 8) |

### Controle de vazamento

As 8 frases de teste vêm do documento da Tânia, então a extração manual
inicialmente trazia todas elas como exemplos — 13 vazamentos. Os exemplos foram
substituídos por frases **da mesma estrutura com léxico diferente**, no mesmo
contexto de saúde:

```
antes   Dor começar quando? -> DOR COMEÇAR QUANDO?     (é o caso de teste 1)
agora   Onde dói? -> DOER ONDE? ; Qual remédio tomou? -> REMÉDIO TOMAR QUAL?

antes   Beber água suficiente? -> BEBER ÁGUA SUFICIENTE (é o caso de teste 4)
agora   Sentiu febre alta? -> SENTIR FEBRE ALTA?
```

Auditoria após a troca: **zero vazamentos** nas quatro bases e no prompt.

### Resultados

| Base | Acurácia | Abstenção | Distribuição |
|---|---:|---:|---|
| `base1_tania` (10) | **8/8 = 100%** | 0% | 5 válido, 3 inválido |
| `base2_livro` (179) | 3/3 = 100% | **62%** | 2 válido, 1 inválido, 5 não coberto |
| `base3_combinada` (189) | **8/8 = 100%** | 0% | 5 válido, 3 inválido |
| `base4_parte2` (79) | **2/5 = 40%** | 38% | 5 inválido, 3 não coberto |

### Frase a frase

| # | Glosa | Esperado | b1 Tânia | b2 livro | b3 comb. | b4 parte2 |
|---:|---|---|---|---|---|---|
| 1 | `DOR COMEÇAR QUANDO?` | válido | OK | absteve | OK | **erro** |
| 2 | `QUANDO DOR COMEÇAR?` | inválido | OK | absteve | OK | absteve |
| 3 | `EU PODER IR PARA CASA HOJE` | inválido | OK | OK | OK | OK |
| 4 | `BEBER ÁGUA SUFICIENTE?` | válido | OK | absteve | OK | absteve |
| 5 | `COMER ESTRANHO ALGO?` | inválido | OK | absteve | OK | OK |
| 6 | `PODER EXPLICAR TRATAMENTO` | válido | OK | absteve | OK | absteve |
| 7 | `EU PODER IR CASA HOJE` | válido | OK | OK | OK | **erro** |
| 8 | `ENFERMEIRA CHAMAR AGORA` | válido | OK | OK | OK | **erro** |

### O que cada resultado significa

**`base1_tania` — 100% limpo, e as citações provam.** Cada veredito cita a regra
correta para o fenômeno: caso 3 cita `TANIA.M.001` (preposição nula), caso 5 cita
`TANIA.M.004` (adjetivo depois do nome), caso 6 cita `TANIA.M.005` (verbo modal).
Não é acerto por sorte nem por vazamento — é a regra certa aplicada ao caso certo.
**Dez regras prescritivas superam 179 descritivas.**

**`base2_livro` — abstém em 5 de 8, e acerta tudo que julga.** O comportamento é
exatamente o previsto pela comparação estática: absteve nos casos de QU (1, 2),
adjetivo (5), sujeito nulo (4) e modal (6) — as regras que a comparação marcou
como `NAO_COBERTA` ou `PARCIAL`. **A abstenção honesta funcionou:** em vez de
inventar veredito, o juiz declarou que a base não alcança o caso.

**`base3_combinada` — 100%, e o livro não diluiu.** Olhando as citações, quase
todas são `TANIA.*`; as do livro entram como apoio secundário (caso 3:
`TANIA.M.001` + `LIVRO.SINTAXE.043`). Somar 179 regras de livro **não estragou**
as 10 da consultoria.

**`base4_parte2` — 40%, e os três erros são instrutivos.** Não falhou por falta
de regra, mas por três causas distintas:

```
1. DOR COMEÇAR QUANDO?    citou "Ordem da oração dependente temporal"
   → leu QUANDO como conjunção temporal, não como item QU interrogativo.
     REGRA ERRADA aplicada — a regra de QU existe na base e não foi escolhida.

7. EU PODER IR CASA HOJE  citou "Uso de IX para pronomes pessoais"
   → exigiu IX(eu) no lugar de EU. CONFLITO DE CONVENÇÃO de anotação:
     o livro glosa pronome como IX, a Tânia usa o pronome reto EU.
     Não é erro de gramática, é notação diferente.

8. ENFERMEIRA CHAMAR AGORA  citou "Topicalização move o constituinte..."
   → exigiu AGORA no início. Tratou POSSIBILIDADE como OBRIGAÇÃO —
     a Tânia diz que as duas ordens valem.
```

> **O achado mais importante do experimento.** A base do livro não falha por
> falta de cobertura: ela falha por **seleção errada de regra**, por **convenção
> de glosa divergente** (IX × pronome reto) e por **ler "pode" como "deve"**.
> São três problemas diferentes, com correções diferentes — e nenhum deles seria
> visível olhando só a acurácia agregada.

### A comparação estática previu o comportamento

Antes de rodar, a comparação Tânia × livro classificou as 12 regras em
equivalente (2), parcial (3), conflito (2) e não coberta (5). O teste confirmou:

- as `NAO_COBERTA` (adjetivo, modal) viraram **abstenção** na `base2_livro`
- o conflito de convenção apareceu como **erro** na `base4_parte2`
- as `EQUIVALENTE` e `PARCIAL` foram acertadas pelas duas bases (caso 3)

Isso valida a comparação estática como ferramenta de previsão — dá para
antecipar onde uma base nova vai falhar sem gastar rodada de GPU.


---

*Modelo Qwen3.8-27B em uma A100 80 GB, thinking desligado, geração
determinística, `max_new_tokens: 1024`. Conjunto de teste: 8 pares derivados das
notas de consultoria da Profa. Tânia (reunião 31/07/2026).*
