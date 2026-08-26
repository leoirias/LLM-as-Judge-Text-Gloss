# Pipeline de Extração de Regras

Como um livro de gramática vira uma lista de regras que o juiz de glosa consegue
aplicar. Cinco passos, os arquivos que os implementam, os prompts que os
governam, os erros encontrados e o que ainda falta.

Documento 1 de 2 — o companheiro é [EVALUATION_PIPELINE.md](EVALUATION_PIPELINE.md).
Atualizado em 21/08/2026.

---

## 1. Visão geral

O pipeline **descarta duas vezes**, em granularidades diferentes. O Passo 2 joga
fora *tópicos* antes de lê-los, com uma decisão barata sobre o título. O Passo 4
joga fora *regras* já extraídas, com uma decisão cara sobre o enunciado inteiro.
Um não substitui o outro: o primeiro evita gastar extração, o segundo pega o que
escapou.

```
documento (PDF)
   │
   │  ┌─ PASSO 1 ─ sem LLM ─────────── chunk_topicos.py
   ├──┤  detectar bordas
   │  └─ 204 páginas → 44 tópicos → 63 trechos
   │
   │  ┌─ PASSO 2 ─ com LLM ─────────── triagem_topicos.py
   ├──┤  triar tópicos (pelo título)          ╲
   │  └─ 63 trechos → 31 seguem                ╲  32 trechos, 53% dos tokens
   │                                            ╲
   │  ┌─ PASSO 3 ─ com LLM ─────────── extract.py  ╲
   ├──┤  extrair regras                              ╲
   │  └─ 31 chamadas → regras candidatas              ╲
   │                                                   ▼
   │  ┌─ PASSO 4 ─ com LLM ─── classify_pipeline.py  ┌──────────────────────┐
   ├──┤  confirmar canal                    ╲        │ Guardado, não apagado│
   │  └─ voice2sign / sign2voice             ╲──────▶│ .txt e CSV em disco; │
   │                                                  │ editar 1 coluna      │
   │  ┌─ PASSO 5 ─ com LLM ─────────── merge_rules.py│ reverte caso a caso  │
   └──┤  fundir regras equivalentes                   └──────────────────────┘
      └─ 81 candidatas → 49 regras finais
```

| Passo | Entra | Sai | LLM? | Arquivo | Prompt |
|---|---|---|---|---|---|
| **1** | PDF + faixa de páginas | trechos + `manifest.csv` | não | `extraction/chunk_topicos.py` | — |
| **2** | títulos dos tópicos | `incluir` = 0/1 | **sim** | `extraction/triagem_topicos.py` | `triagem_topicos.yaml` |
| **3** | um trecho por chamada | regras candidatas | **sim** | `extraction/extract.py` | `extract_rules.yaml` |
| **4** | candidatas de todas as fontes | voice2sign / sign2voice | **sim**\* | `simplification/classify_pipeline.py` | `confirmar_canal.yaml` |
| **5** | candidatas de um canal | lista final | **sim** | `simplification/merge_rules.py` | `merge_rules.yaml` |
| **5b** | base + fonte nova | relatório de divergência | **sim** | `simplification/compare_rules.py` | `compare_rule.yaml` |

\* O Passo 4 roda sem LLM por padrão; `--confirmar` liga a segunda opinião.

> **Modelo em todos os passos com LLM:** Qwen3.8-27B (denso, 27,8B, Apache 2.0),
> bf16, *thinking* desligado, `do_sample: false`. Ocupa ~54 GB e roda em uma
> A100 de 80 GB. Determinístico de propósito: rodar o mesmo trecho de novo
> produz a mesma lista.

---

## 2. Passo 1 — Detectar bordas

**Arquivo:** `libras_pipeline/extraction/chunk_topicos.py` · sem LLM ·
determinístico · verificável

**Objetivo:** entregar à LLM um assunto por chamada, nunca um corte arbitrário
no meio de uma explicação.

### Por que não fatiar por página fixa

O fatiamento anterior usava janelas de 15 páginas. Medido no Cap.5: **10 dos 13
cortes internos (76%) caem no meio de um tópico**, e a janela mediana tem 6.081
tokens (máx. 10.573) — o modelo recebe vários assuntos misturados e precisa achar
sozinho onde um termina.

### Definições

1. **Fronteira** — página que inicia um tópico.
2. **Tópico** — da fronteira até a página anterior à fronteira seguinte.
3. **Trecho** — o que vai em *uma* chamada: tópicos consecutivos agrupados até o
   orçamento de tokens. Tópico maior que o orçamento é partido por página, e cada
   parte repete o cabeçalho, marcada `parte i de n`.

### Como as fronteiras são detectadas

Duas fontes, unidas: o **outline do PDF** (bookmarks), percorrido recursivamente
em todos os níveis, e o **título detectado no texto**, para onde o outline é raso
ou não confiável.

| Filtro | Sintoma observado |
|---|---|
| **Recursão completa no outline** | Varredura de um nível só encontrou 3 fronteiras no ASL for Dummies, que tem 49 na faixa. |
| **Descartar âncora-lixo** (`_7jjy9o4k5753`) | **176 das 211 entradas (83%)** do outline da Gramática são âncoras internas de editor. Apontam para posições arbitrárias — p.176, p.243 e p.259 caem em meio de prosa, sem título nenhum. |
| **Modo adaptativo** (`numerado` × `prosa`) | Conta títulos numerados na faixa; se o documento usa numeração (≥5 ocorrências), o modo prosa fica desligado. Sem isso, `1. Sinais monomorfêmicos…` (item de lista) e `GLOSA E SIGNIFICADO` (cabeçalho de tabela) entravam como seção. |
| **`topic_prefix`** (config) | Restringe a fronteira ao capítulo em foco: com `topic_prefix: 5`, só `5.x` conta. |
| **Palavra funcional** (modo prosa) | Em livro sem numeração as seções são linhas em MAIÚSCULAS — mas *glosas também são*. O que separa é linguístico: glosa não realiza artigo nem preposição. Exigir uma palavra funcional aceita `A ORDEM BÁSICA DA FRASE` e rejeita `IX GOSTA FUTEBOL`. |
| **Normalizar espaço no título** | Bookmark de PDF pode ter quebra de linha embutida; isso partia o cabeçalho `=== TÓPICO: … ===` em duas linhas e metia uma quebra dentro do campo do CSV. |

### Formato do trecho entregue à LLM

```
=== DOCUMENTO: Gramática da Libras Vol.1 (INES/Quadros et al.) — Cap.5 Morfologia ===
=== TÓPICO: 5.4.3.2. Processos de composição dos sinais da Língua de Sinais ===
=== TRECHO: páginas 198-200 (parte 1 de 2 do mesmo tópico) ===

[p.198]
5.4.3.2. Processos de composição dos sinais...
 Em termos práticos, a composição realiza-se por duas ou mais unidades...

[p.199]
...
```

- O **cabeçalho de tópico** dá a identidade do assunto mesmo quando o tópico foi
  subdividido.
- Os marcadores **`[p.N]` inline** mantêm `fonte_pagina` e `fonte_citacao`
  rastreáveis quando o trecho cruza páginas. `N` é o índice 0-based do pypdf,
  **não** o número impresso.

### Colunas do `manifest.csv`

| Coluna | O que é |
|---|---|
| `n`, `arquivo` | ordem e nome do `.txt` correspondente |
| `topico` | título que vai no cabeçalho do trecho |
| `topicos_todos` | todos os títulos agrupados neste trecho, separados por `\|`. Existe porque a triagem precisa julgar cada um |
| `nivel_outline` | profundidade no bookmark do PDF; `-1` = não estava no outline. Descritivo — não influencia o fatiamento. Diagnóstico: muitos `-1` indicam bookmarks que não cobrem as próprias seções |
| `pagina_ini`, `pagina_fim`, `n_paginas` | faixa coberta (índice 0-based do pypdf) |
| `n_topicos` | quantos tópicos foram agrupados |
| `parte` | vazia = tópico inteiro ou agrupamento; `i/n` = pedaço `i` de um tópico grande |
| `tokens` | tamanho medido com o tokenizer do próprio modelo |
| `incluir`, `motivo_exclusao` | preenchidos pelo Passo 2 |

As três combinações de `parte`:

| Caso | `n_topicos` | `parte` | Exemplo no Cap.5 |
|---|---:|---|---|
| tópico inteiro | 1 | vazia | #1 · p.174 · 480 tok · `5. Aspectos gerais da morfologia` |
| tópicos agrupados | >1 | vazia | #3 · p.177-181 · 1.890 tok · `5.2. Morfemas em Libras` (2 tópicos) |
| tópico partido | 1 | `i/n` | #46–#50 · `5.7.5.1` tem 6.256 tokens, virou 5 partes |

### Verificação automática

Ao gerar, o script confere que a união dos trechos cobre a faixa configurada
**exatamente uma vez** — sem furo e sem sobreposição — e imprime `OK` ou
`FALHOU`. Nenhum trecho de texto pode sumir nem ser processado duas vezes.

### Uso

```bash
python3 libras_pipeline/extraction/chunk_topicos.py --book gramatica --budget 2000
```

| Flag | Efeito |
|---|---|
| `--book <trecho>` | filtra a fonte pelo label ou slug no `config.yaml` |
| `--budget N` | orçamento de tokens por trecho (default 2000) |
| `--out DIR` | destino (default `extraction/chunks/`) |

Como é grátis e determinístico, dá para calibrar o orçamento antes de gastar GPU.
Nas cinco fontes: 1.500 → 147 trechos · **2.000 → 114** · 3.000 → 74 ·
4.000 → 55 · 6.000 → 36.

---

## 3. Passo 2 — Triar tópicos

**Arquivo:** `libras_pipeline/extraction/triagem_topicos.py` ·
**Prompt:** `prompts/triagem_topicos.yaml` · LLM, só o título · default: incluir

Ações de boca são canal não-manual **por definição**: qualquer regra extraída
dali sairia como `sign2voice` e nunca chegaria ao juiz. Pedagogia e história da
língua estão fora do escopo declarado no próprio prompt de extração. Ler esses
tópicos é gastar GPU para produzir o que será descartado no Passo 4.

Cada **título** distinto do manifesto vai ao modelo, que responde
`{"incluir": true|false, "motivo": "…"}`. A decisão é pelo título só, e isso é de
propósito: descarta-se um tópico inteiro — às vezes 15 trechos — com uma chamada
curta, em vez de ler o texto todo para depois jogar fora. Os títulos vão em batch
(`generate_batch`), e um tópico partido em *n* trechos é decidido uma vez.

### O critério do prompt

Excluir quando o título for **claramente** sobre:

| Grupo | Exemplos de termo |
|---|---|
| canal não-manual | boca, ações-de-boca, articulação-boca, expressão facial, olhar, cabeça, tronco |
| espaço, movimento, forma da mão | uso do espaço, localização, trajetória, configuração de mão, orientação |
| visualidade e iconicidade | gesto, classificador imagético, transferência de incorporação/localização |
| não é estrutura da língua | ensino, pedagogia, história, política linguística, tecnologia, corpus |

### Salvaguardas contra perder conteúdo

- **Na dúvida, inclui.** O critério é "claramente sobre", não "possivelmente
  relacionado a". Incluir um tópico inútil custa uma chamada; excluir um útil
  perde as regras dele para sempre.
- **Resposta ilegível vira incluir.** O parse é tolerante e o default de falha é
  `incluir=1` — uma triagem que quebra não pode ser a causa de um tópico sumir.
- **Exclusão só se todos os tópicos do trecho forem reprovados.** Um trecho pode
  agrupar vários tópicos; `topicos_todos` guarda todos, e basta um aprovado para
  o trecho seguir.
- **Título sem informação leva um trecho do texto.** `(início da faixa)`,
  `Cap_04`, `Conclusao` não dizem nada — nesses casos vão 300 caracteres do corpo
  junto.
- **Nada é apagado.** Os `.txt` dos tópicos excluídos continuam em disco; editar
  `incluir` reverte caso a caso.

### Por que não uma lista declarada à mão

Uma lista de prefixos por livro (`excluir: ["5.6", "5.7.4"]`) foi implementada e
descartada: exige conhecer o sumário de cada documento novo de antemão, o que
quebra a premissa de funcionar automaticamente para qualquer PDF. A decisão por
título vale para livro e artigo, em português ou inglês, sem configuração.

### Quanto custa a triagem

A pergunta que importa não é quanto ela poupa, e sim quanto faz perder. No Cap.5
a triagem exclui 105 das 204 páginas. Rodando a extração no capítulo *inteiro*,
dessas 105 páginas saiu **uma única regra voice2sign**:

```
[p.292] Transcrição visual das articulações-boca (Sons Surdos)
        "As glosas das articulações-boca devem ser transcritas com base
         na visualidade do movimento articulatório"
```

E ela é sobre articulação-boca — canal não-manual. Estava mal classificada como
voice2sign desde a extração; o Passo 4 a removeria de qualquer forma.

> **Custo medido: uma regra, e duvidosa.** Ganho: metade das páginas do capítulo
> não precisa ser lida. A troca é boa o bastante para não depender de julgamento.

Rendimento por seção que motivou o passo:

| Seção | Regras extraídas | Das quais voice2sign |
|---|---:|---:|
| 5.4 Formação/composição | 14 | 6 (42%) |
| 5.5 Flexão/concordância | 16 | 1 (6%) |
| **5.6 Ações-boca** | 26 | **1 (3%)** |
| **5.7 Desc. imagéticas + ensino** | 10 | **0 (0%)** |
| 5.8 Expressões idiomáticas | 19 | 14 (73%) |

> **Cuidado ao ler essa tabela.** O rendimento foi medido com o extrator antigo,
> que é justamente o que se suspeita ser ruim. Ela justifica *existir* a triagem,
> mas não deve virar critério: excluir uma seção por ter rendido pouco antes
> fossiliza a falha do extrator anterior. Por isso o critério do prompt é o
> assunto do título, não o rendimento passado.

---

## 4. Passo 3 — Extrair regras

**Arquivo:** `libras_pipeline/extraction/extract.py` ·
**Prompt:** `prompts/extract_rules.yaml` (formato AUTOMAT)

### Os fragmentos do prompt

| Fragmento | AUTOMAT | O que faz |
|---|---|---|
| `act_as` | Act as | linguista computacional que destila descrição em regras operacionais |
| `audiencia` | User persona | diz que a saída vai para um validador automático, não para humano — é o que justifica exigir regra decidível |
| `o_que_e_glosa` | — | **definição formal de glosa**: o que ela carrega e o que não carrega |
| `acao` | Targeted action | separar **gatilho** (o "quando") de **determinação** (o "então") |
| `escopo` | Topic whitelisting | o que extrair e o que não extrair |
| `saida` | Output definition | os 8 campos do JSON, sem `id` |
| `criterio_canal` | — | o teste que define `verificavel_por_texto` |
| `casos_atipicos` | Atypical cases | descrição × prescrição, regra com exceção, trecho sem regra |
| `modo` | Mode/tonality | técnico e literal, sem aspas duplas dentro dos valores |

### A definição de glosa

Está no prompt porque delimita o que pode virar regra verificável. Glosa é a
representação **escrita e linear** de uma sequência de sinais; cada sinal é uma
**etiqueta em MAIÚSCULAS** que o *identifica*, não o traduz.

- **Carrega:** quais sinais, em que ordem, e as convenções escritas (hífen para
  sinal multi-palavra `IR-EMBORA`, `IX(referente)` para apontação, `M-A-R-I-A`
  para datilologia).
- **Não carrega:** expressão facial e marcadores não-manuais · uso do espaço e
  localização dos referentes · direção, trajetória, velocidade ou repetição do
  movimento · configuração de mão.

A frase que amarra as duas listas: *"tudo nessa segunda lista é invisível para
quem lê apenas a glosa — e é exatamente por isso que existe o campo
`verificavel_por_texto`"*. Sem isso, a definição e o critério de canal seriam
duas instruções soltas em vez de uma linha de raciocínio.

### O critério de canal

```
"Se eu receber APENAS a sequência de glosas escrita em letras maiúsculas
 — sem vídeo, sem imagem, sem anotação de expressão, sem descrição de
 movimento — eu consigo dizer se esta regra foi respeitada ou violada?"

  SIM, só com as palavras escritas     -> verificavel_por_texto: true
  NÃO, preciso de qualquer outra coisa -> verificavel_por_texto: false
```

### Campos de cada regra

| Campo | Conteúdo |
|---|---|
| `titulo` | nome curto e específico |
| `descricao` | a determinação: o que deve ou não ocorrer na glosa |
| `gatilho` | a condição que ativa a regra |
| `verificavel_por_texto` | true/false — decide o canal |
| `exemplos` | exemplos do próprio texto (português → glosa quando houver) |
| `fonte_pagina` | o número como aparece no marcador `[p.N]` |
| `fonte_citacao` | trecho verbatim (≤200 chars) que sustenta a regra |
| `categoria` | rótulo de uma palavra, de vocabulário fechado. *Campo secundário* — o prompt manda não gastar raciocínio nele |
| `id` | **não pedido ao modelo** — atribuído por código |

### Decisões de robustez

- **Validação item a item.** Uma regra com campo faltando é descartada sozinha,
  sem derrubar as outras do mesmo trecho. Antes, um `gatilho` ausente matava a
  lista inteira.
- **ID atribuído por código** (`LIBRAS.SINTAXE.001`), sequencial por categoria.
  Cada trecho é uma chamada isolada; o modelo não sabe o que já foi numerado,
  então IDs vindos dele colidiriam.
- **Log cru por rodada** (`<slug>_regras.raw.txt`), o que permite reconstruir o
  CSV sem GPU via `--from-raw` e auditar qualquer regra até o texto que a gerou.

### Flags

| Flag | Efeito |
|---|---|
| *sem flag* | processa todas as fontes de `books:` |
| `--book <trecho>` | filtra por label ou slug |
| `--chunks` | usa os trechos por tópico em vez de janelas de página |
| `--no-triagem` | com `--chunks`, processa todos os trechos ignorando `incluir` — usado para isolar o efeito da triagem |
| `--out-dir NOME` | diretório de saída, para não sobrescrever uma extração anterior |
| `--from-raw` | reconstrói o CSV do `.raw.txt` salvo, sem GPU |
| `--patch-pages I F` | reprocessa só essa faixa e funde no resultado existente |

---

## 5. Passos 4 e 5 — Canal e fusão

A extração produz uma lista **crua**: cada trecho foi processado isolado, então a
mesma regra reaparece em trechos vizinhos com outras palavras.

### Passo 4 — Filtrar regras por canal

**Arquivo:** `libras_pipeline/simplification/classify_pipeline.py` ·
**Prompt:** `prompts/confirmar_canal.yaml`

Três operações mecânicas, sempre:

1. **Junta as fontes** — lê todos os `*_regras.csv` do diretório de entrada num
   pool único.
2. **Renumera IDs em colisão** — cada fonte numera do 1 por categoria, então dois
   livros geram o mesmo `LIBRAS.SINTAXE.002`.
3. **Separa em dois arquivos** pelo campo `verificavel_por_texto`.

| Regra | Canal | Por quê |
|---|---|---|
| `LIBRAS.SINTAXE.001` | **voice2sign** | *Ordem básica SVO* — dá para checar lendo a glosa: os sinais estão em SVO ou não |
| `LIBRAS.VERBOS.001` | **sign2voice** | *Verbos direcionais com concordância espacial* — depende de movimento e direção, que a glosa escrita não mostra |

As `sign2voice` não são descartadas: ficam guardadas para quando houver vídeo ou
anotação.

#### `--confirmar`: segunda opinião sobre o canal

O canal foi decidido no Passo 3, mas **junto com outros sete campos, numa
resposta só**. Com `--confirmar`, a mesma pergunta é refeita aqui — sozinha,
sobre a regra já pronta, sem o texto do livro à vista. É deliberadamente um
contexto diferente do que decidiu antes: se fosse o mesmo, repetiria o mesmo
viés em vez de checá-lo.

A divergência nunca é silenciosa. O CSV ganha quatro colunas — `canal_extracao`,
`canal_confirmado`, `divergencia`, `motivo_confirmacao` — e sai um
`divergencias_canal.csv` com todos os casos em que as duas decisões não bateram.

| Política de desempate | Comportamento |
|---|---|
| `conservadora` *(default)* | qualquer `false` das duas manda a regra para sign2voice |
| `confirmacao` | a segunda opinião decide sozinha |

O default é conservador porque **os dois erros não custam igual**. Uma regra
não-verificável que passa faz o juiz reprovar glosa correta, citando algo que ele
não tem como enxergar. Já uma regra verificável que sai por engano só reduz
cobertura: o juiz abstém (`nao_coberto`), que é um resultado honesto.

Se o parse da confirmação falhar, **mantém-se a decisão da extração**, marcada
como tal no motivo — uma confirmação quebrada não pode mudar canal por acidente.

### Passo 5 — Fundir regras equivalentes

**Arquivo:** `libras_pipeline/simplification/merge_rules.py` ·
**Prompt:** `prompts/merge_rules.yaml`

Processa **por categoria, em rodadas**: pega a lista já consolidada (vazia na 1ª)
+ um lote de 15 candidatas novas, e pede a lista atualizada. Categoria com uma
candidata só nem chama o modelo. Efeito medido: **81 candidatas → 49 regras
finais**.

```
[LIBRAS.EXPRESSOES-IDIOMATICAS.3]  Expressões idiomáticas com significado não literal

ids_origem: EXPRESSOES-IDIOMATICAS.007, .008, .011, .013, .014, .017, .018, .019

justificativa_fusao: "Todas as candidatas descrevem expressões idiomáticas em
Libras com significado não literal, baseadas em regularidade, convencionalidade,
metaforização, uso corporal e variação, sendo fenômenos distintos apenas em
foco, mas unificados pelo núcleo comum de significação."
```

Dois campos existem para tornar a fusão **auditável**: `ids_origem` rastreia cada
regra final até as candidatas do Passo 3, e `justificativa_fusao` registra por
que o modelo as considerou a mesma regra. Dá para desfazer qualquer fusão que não
convença.

Três redes de segurança, todas por falha observada na prática: item inválido não
derruba o lote · candidata omitida pelo modelo volta sozinha como regra própria ·
`ids_origem` deduplicado quando a mesma candidata é reivindicada duas vezes.

### Passo 5b — Comparar com uma base existente (opcional)

`compare_rules.py` classifica cada candidata nova contra a base em `ja_temos` /
`nao_temos` / `conflito` / `parcial`. **Não altera a base** — gera CSV para
revisão humana.

> **Limite conhecido.** A comparação é estática, regra contra regra. Um conflito
> que só aparece *quando aplicado a uma frase* passa como `parcial`. Foi o que
> aconteceu com "QU pode mover" (livro) × "QU sempre no fim" (Tânia): no papel
> parecem complementares, na prática se contradizem.

---

## 6. Erros encontrados

Cada linha é uma falha observada na prática, não um risco hipotético.

### Parse e formato de saída

| Sintoma | Causa | Correção | Estado |
|---|---|---|---|
| 7 janelas perdidas na 1ª extração de ASL | tab cru dentro de string JSON | `json.loads(strict=False)` | corrigido |
| lista inteira descartada | uma regra sem `gatilho` derrubava as outras da janela | validação item a item | corrigido |
| JSON truncado no fim | `max_new_tokens` 4000 insuficiente em janelas densas | subido para 6000 | corrigido |
| JSON inválido por aspas | aspas duplas cruas dentro dos valores | instrução explícita no fragmento `modo` | corrigido |
| janela ruim exige rodar tudo de novo | não havia reprocessamento parcial | `--patch-pages` | corrigido |

### Fatiamento e detecção de fronteira

| Sintoma | Causa | Correção | Estado |
|---|---|---|---|
| 3 fronteiras onde havia 49 | varredura do outline descia só um nível | recursão completa | corrigido |
| fronteiras em meio de prosa | 83% do outline da Gramática são âncoras de editor | descartar âncora-lixo | corrigido |
| item de lista virando seção | `1. Sinais monomorfêmicos…`, `GLOSA E SIGNIFICADO` passavam no detector | modo adaptativo + `topic_prefix` | corrigido |
| nota de rodapé como título | `5 Oliveira (2015) chama…` casava com o regex | exigir hierarquia (`5.x`) ou ponto final | corrigido |
| cabeçalho partido em 2 linhas | bookmark do PDF com quebra de linha embutida | `limpa_titulo()` colapsa espaço em branco | corrigido |

### Triagem

| Sintoma | Causa | Correção | Estado |
|---|---|---|---|
| 5 tópicos excluídos sem serem julgados | trecho agrupado guardava só o título do primeiro | coluna `topicos_todos`; exclui só se todos forem reprovados | corrigido |
| decisão vazia em 100% da fonte Tânia | título `(início da faixa)` não carrega informação | título sem informação leva 300 chars do texto | corrigido |

Nos 5 tópicos excluídos sem julgamento — `Orientação da Mão`,
`Transferência Espacial`, `Transferência de Localização`,
`Transferência de Vibração`, `DeafSpace` — o dano prático foi nulo: todos seriam
excluídos de qualquer forma. Mas o mecanismo estava errado e poderia descartar
conteúdo bom em outro documento.

### Escopo do prompt cortava regras boas

O escopo dizia "não extraia vocabulário ou lista de sinais sem padrão por trás".
A intenção é certa — entrada de dicionário não é regra, porque uma glosa não pode
*violar* o fato de que o sinal de casa é CASA. Mas a instrução era cega demais:
na rodada por tópico, **12 dos 13 trechos de expressões idiomáticas voltaram
vazios**, e a seção de idiomatismos era a de maior rendimento do capítulo
(19 regras, 14 voice2sign).

O que se perdia tem exatamente a forma de regra:

```
gatilho    quando a frase em português contém uma expressão idiomática
determina  a glosa usa a forma idiomática da Libras, não a tradução literal
exemplos   Cara de pau → CARA-BATER
           Ficar com ciúme → COTOVELO-CAIR
           Tem fluência em Libras → MÃOS LEVES
```

Uma das regras é sobre **falso cognato** — `mãos leves` em português significa
ladrão, `MÃOS LEVES` em Libras significa fluente — que é o tipo de armadilha que
um validador existe para pegar.

**Correção:** a exclusão passou a ser por *forma*, não por assunto. Entrada solta
de dicionário continua fora; mapeamento com gatilho ("quando a frase tem P, a
glosa usa G") entra.

> **Cuidado com o exemplo no prompt.** A primeira versão da correção usava
> `cara de pau → CARA-BATER` como ilustração — e esse par vem do próprio capítulo
> que será processado. Como a rodada existe para medir se as regras de
> idiomatismo voltam, semear uma delas invalidaria a medição. O exemplo foi
> trocado por um esquema abstrato (P → G), e uma verificação confirma que nenhuma
> glosa do capítulo aparece no prompt.

### Confirmação de canal enviesada

Na primeira rodada do Passo 4, **34 das 36 divergências** foram voice2sign →
sign2voice, cortando o conjunto de 55 para 21 regras. O caso que prova o viés:

```
regra    Ordem básica SVO — a ordem canônica da frase em Libras é SVO
veredito sign2voice
motivo   "Glosa não carrega função sintática, impossível verificar ordem SVO."
```

Isso é falso. Ordem dos sinais é *precisamente* o que a glosa carrega — é o
segundo item da definição que o próprio prompt contém. O modelo confundiu duas
coisas: a glosa não *rotula* qual sinal é sujeito, o que é verdade; disso não
segue que a ordem seja inverificável, porque os papéis vêm da frase em português,
que o juiz também recebe.

A causa não era um prompt ruim isolado, e sim **duas salvaguardas empurrando na
mesma direção**:

```
ANTES                                    DEPOIS
                                    │
 prompt: "NA DÚVIDA, false"  ──┐    │    prompt: julga, com exemplos à vista ──┐
                                ├──▶ sign2voice                                ├──▶ canal
 política: qualquer false vence ┘    │    política: qualquer false vence ──────┘    decidido
                                    │
 55 → 21 regras                     │    divergência reportada
 ✗ "Ordem básica SVO" sai da base   │    ✓ regra de ordem sobrevive
                                    │
 Dois mecanismos, um viés só.       │    Um mecanismo empurra, o outro julga.
 Nada segura o outro lado.          │    A rede fica só na política.
```

Três mudanças: o prompt passou a receber o campo `exemplos`, para o modelo ver a
glosa concreta; saiu a regra "NA DÚVIDA, false"; e entrou um caso positivo
explícito de que **ordem é sempre verificável**, com o aviso contra o erro exato
que aconteceu.

### Ferramental e operação

| Sintoma | Causa | Correção | Estado |
|---|---|---|---|
| CSV de 76 regras virou 4 | `--categoria` reprocessava uma categoria e sobrescrevia todas | preservar as outras categorias | corrigido |
| IDs do relatório não casam com o CSV final | `divergencias_canal.csv` era escrito antes da renumeração | escrito depois, com `titulo` e `descricao` embutidos | corrigido |
| passos 4 e 5 sobrescreviam a base atual | diretórios de entrada e saída fixos | `--from-dir` e `--out-dir` | corrigido |
| comandos quebram ao reorganizar pastas | `PYTHONPATH=src` relativo; `src/` foi movido | — | **em aberto** |

---

## 7. Testes e verificações

O pipeline não tem suíte de testes automatizada. O que existe são verificações
embutidas e auditorias reexecutáveis.

| Verificação | Onde | O que garante |
|---|---|---|
| **Cobertura exata** | embutida no Passo 1 | a união dos trechos cobre a faixa uma vez, sem furo nem sobreposição. Imprime `OK`/`FALHOU` a cada geração |
| **Auditoria de 6 eixos** | script avulso | cobertura · arquivos × manifesto · orçamento respeitado · títulos-âncora e vazios · cabeçalho de 3 linhas e marcadores `[p.N]` na sequência · partes numeradas 1..n |
| **Teste de regressão** | script avulso | roda a versão anterior e a nova do `classify_pipeline.py` sobre a mesma entrada em diretórios temporários e compara byte a byte |
| **Verificação de vazamento** | script avulso | confere que nenhuma glosa do corpus aparece como exemplo semeado no prompt |
| **Log cru por rodada** | `*.raw.txt` | permite reconstruir o CSV sem GPU e auditar qualquer regra até o texto que a gerou |
| **Aviso de ID inexistente** | Passo 3 e juiz | detecta alucinação de identificador |

> **Lacuna reconhecida.** Não há testes unitários das funções de fronteira,
> agrupamento e parse. Todas as verificações acima são de integração e rodam
> sobre os dados reais — o que pega erro grosseiro mas não cobre caso limite.
> `outros/tests/` existe mas não cobre estes pipelines.

---

## 8. Experimento de ablação

**Arquivo:** `libras_pipeline/extraction/experimento_ablacao.py`

Prompt, fatiamento e triagem mudaram na mesma rodada, então nenhuma comparação
feita até agora atribui causa. O experimento muda **uma variável por vez**:

| Célula | Prompt (Passo 3) | Fatiamento (Passo 1) | Triagem (Passo 2) | Chamadas |
|---|---|---|---|---:|
| **A** | antigo | janela de 15 páginas | — | já existe |
| **B** | corrigido | janela de 15 páginas | — | 14 |
| **C** | corrigido | por tópico | desligada | 63 |
| **D** | corrigido | por tópico | ligada | **0** |

- **A → B** isola o **prompt**. Fatiamento igual nos dois, triagem ausente nos dois.
- **B → C** isola o **fatiamento**. É aqui que se descobre se cortar por tópico
  vale as 63 chamadas.
- **C → D** isola a **triagem**. Mesmo prompt, mesmos trechos.

**D não gasta GPU.** A geração é determinística (`do_sample: false`) e cada trecho
é uma chamada isolada, sem histórico — então D é exatamente o subconjunto de C
nos trechos aprovados. O script recorta o `.raw.txt` de C e o CSV sai com
`--from-raw`.

> **Rastreabilidade entre células.** Os IDs são atribuídos por código,
> sequencialmente por categoria sobre o conjunto inteiro. A mesma regra terá ID
> diferente em C e em D. Para casar regra a regra, use `fonte_pagina` + `titulo`,
> não o ID.

O comparador imprime, para cada degrau, a variação em regras e em **voice2sign** —
que é o número que importa, já que é o único canal que chega ao juiz — mais os
fenômenos-alvo: idiomatismo, ordem/SVO, preposição, negação e verbo modal.

Dois sinais para conferir: em **A→B**, as regras de idiomatismo têm que voltar
(eram 14 voice2sign, caíram para ~1). Em **B→C**, se o voice2sign não subir, o
fatiamento por tópico não está pagando as 63 chamadas.

### Estado medido

| Métrica (Cap.5, 204 páginas) | Janela de 15p | Por tópico | Leitura |
|---|---:|---:|---|
| Trechos enviados ao modelo | 14 | 63 | fatiamento mais fino |
| Tokens por trecho (mediana) | 6.081 | 1.445 | um assunto por chamada |
| Tokens (máximo) | 10.573 | 1.999 | orçamento respeitado |
| Cortes no meio de um tópico | 10 de 13 | **0** | objetivo do Passo 1, atingido |
| Trechos após a triagem | — | 31 | 53% dos tokens poupados |
| Regras extraídas | 93 | **24** | queda majoritariamente do escopo do prompt |
| Proporção voice2sign | 26% | **66%** | o que resta é mais aproveitável |
| Regras voice2sign (absoluto) | 25 | **16** | perda concentrada em idiomatismos |

### Carga das três fontes de Libras

| Fonte | Arquivo | Páginas | Tópicos | Trechos | Modo |
|---|---|---|---:|---:|---|
| Gramática da Libras Vol.1, Cap.5 | `Gramatica_de_libras.pdf` | 174–377 | 44 | 63 | numerado |
| Estudos Linguísticos, Cap.4 | `Lingua_de_sinais_brasileira_estudos_linguisticos.pdf` | 123–210 | 7 | 15 | prosa |
| Notas da Profa. Tânia | `Analise_sintatica_tania.pdf` | 0–5 | 1 | 2 | prosa |

> **A confiança difere por fonte.** A Gramática é a mais sólida: 44 tópicos com
> títulos numerados inequívocos. O Estudos tem só **7 fronteiras em 88 páginas**,
> então 13 dos 15 trechos são pedaços partidos por tamanho, não tópicos inteiros
> — o ganho de contexto ali é bem menor. A Tânia tem 1 tópico em 6 páginas: na
> prática equivale a uma janela fixa.

---

## 9. Como rodar

GPUs livres se verificam com `nvidia-smi`. Use uma só — o modelo ocupa ~54 GB.

```bash
# 1 — detectar bordas (sem GPU)
python3 libras_pipeline/extraction/chunk_topicos.py --budget 2000

# 2 — triar tópicos
docker compose exec -e CUDA_VISIBLE_DEVICES=3 judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/extraction/triagem_topicos.py'

# 3 — extrair regras dos tópicos aprovados
docker compose exec -e CUDA_VISIBLE_DEVICES=3 judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/extraction/extract.py \
     --chunks --out-dir output_pipeline'

# 4 — filtrar por canal, com segunda opinião
docker compose exec -e CUDA_VISIBLE_DEVICES=3 judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/simplification/classify_pipeline.py \
     --from-dir output_pipeline --out-dir output_pipeline --confirmar'

# 5 — fundir regras equivalentes
docker compose exec -e CUDA_VISIBLE_DEVICES=3 judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/simplification/merge_rules.py \
     --from-dir output_pipeline --group voice2sign'
```

Ordem é obrigatória — cada passo lê o que o anterior escreveu, e rodar o 1 de
novo zera a triagem do 2.

Duas paradas de conferência, ambas baratas:

- depois do **2**, a lista de tópicos excluídos com o motivo de cada um. É o
  ponto mais barato para pegar um corte indevido, antes das horas do passo 3.
- depois do **4**, o `divergencias_canal.csv`. A regra "Ordem básica SVO" tem que
  sobreviver como voice2sign. Se cair de novo, o prompt ainda está enviesado e
  não vale fundir uma base mutilada.

### Aplicando a um documento novo

Adicionar uma entrada em `books:` no `config.yaml`:

```yaml
  - label: "Nome legível da fonte"      # vai no cabeçalho de cada trecho
    slug: nome_curto                     # nomeia os arquivos de saída
    path: documento.pdf
    start_page: 174                      # índice 0-based do pypdf
    end_page: 377
    topic_prefix: 5                      # opcional: restringe ao capítulo
```

Depois: rodar o Passo 1 e **abrir o `manifest.csv` para conferir os títulos**. Se
vierem `_xxxx` ou nomes que não são seção, o documento usa um sinal ainda não
coberto — vale inspecionar antes de gastar GPU.

---

## 10. Possibilidades de avanço

Em ordem aproximada de retorno sobre esforço.

1. **Rodar a ablação.** É o que falta para saber se o fatiamento por tópico se
   paga. Sem isso, as 63 chamadas por capítulo são uma aposta.
2. **Espelhar para ASL.** O `asl_pipeline` não tem `chunk_topicos.py`,
   `triagem_topicos.py`, `confirmar_canal.yaml`, nem as flags `--chunks` /
   `--no-triagem` / `--from-dir`. Enquanto isso não for feito, "funciona para
   qualquer documento" só vale para Libras.
3. **Mover a decisão de canal para o Passo 4.** Hoje ela sai no Passo 3 junto com
   outros sete campos. Tirá-la de lá isolaria a decisão em vez de checá-la
   depois. As duas opções nunca foram comparadas.
4. **Partir tópico grande por parágrafo, não por página.** Uma parte ainda pode
   terminar no meio de uma frase, embora dentro do mesmo assunto.
5. **Calibrar o orçamento.** 2.000 tokens foi escolhido por deixar a mediana
   confortavelmente abaixo do limite; nenhum teste comparou qualidade entre
   orçamentos.
6. **Usar `generate_batch` no Passo 3.** O cliente já tem o método e o Passo 2 já
   o usa; a extração ainda chama `generate()` um trecho por vez.
7. **Detecção de fronteira por LLM** para documento sem sinal tipográfico — sem
   outline útil, sem numeração e sem título em maiúsculas o método atual não
   funciona. Nenhuma das fontes atuais cai nesse caso.
8. **Extração em estágios** (seleção → extração → canal → eixos), em vez de pedir
   oito campos numa resposta só.
9. **Testes unitários** das funções de fronteira, agrupamento e parse.
10. **Fontes prescritivas.** Gramáticas descritivas dizem o que a língua
    *permite*, não o que a glosa *deve* conter. As regras mais úteis ao juiz
    vieram das notas de consultoria, não dos livros.

---

*Medições sobre `Gramatica_de_libras.pdf` Cap. 5 (p. 174–377),
`Lingua_de_sinais_brasileira_estudos_linguisticos.pdf` Cap. 4 e
`Analise_sintatica_tania.pdf`. Modelo Qwen3.8-27B em uma A100 80 GB, thinking
desligado, geração determinística. Contagem de tokens com o tokenizer do próprio
modelo.*
