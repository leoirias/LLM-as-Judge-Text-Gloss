# Pipeline de extração de regras — do documento à lista de regras

Formaliza o bloco **anterior à avaliação**: como um documento (PDF de
gramática, manual, notas de consultoria) vira uma lista de regras utilizável
pelo juiz de glosa. A avaliação é documentada à parte.

O pipeline é **genérico por construção** — nada aqui é específico da Libras ou
de um livro. O que muda entre documentos são parâmetros de configuração, não
código. As decisões de projeto abaixo saíram de falhas medidas em documentos
reais, e cada uma está registrada com o sintoma que a motivou.

```
documento (PDF)
   │
   ├─ PASSO 1  detectar bordas                       sem LLM
   │           topo do documento → trechos por tópico
   │
   ├─ PASSO 2  triagem de tópicos                    com LLM
   │           descarta tópico fora do canal voice2sign, pelo título
   │
   ├─ PASSO 3  extrair regras                        com LLM
   │           um trecho por chamada
   │
   ├─ PASSO 4  filtrar regras por canal              com LLM (--confirmar)
   │           segunda opinião: confirma o canal de cada regra
   │
   └─ PASSO 5  simplificar                           com LLM
               funde regras equivalentes → lista final
```

| Passo | Entra | Sai | LLM? | Script |
|---|---|---|---|---|
| **1** | PDF + faixa de páginas | trechos + `manifest.csv` | não | `chunk_topicos.py` |
| **2** | títulos dos tópicos | `incluir` = 0/1 no manifesto | **sim** | `triagem_topicos.py` |
| **3** | um trecho por chamada | regras candidatas | **sim** | `extract.py --chunks` |
| **4** | candidatas de todas as fontes | voice2sign / sign2voice + divergências | **sim**\* | `classify_pipeline.py` |
| **5** | candidatas voice2sign | lista final, sem duplicata | **sim** | `merge_rules.py` |

\* O Passo 4 roda sem LLM por padrão; `--confirmar` liga a segunda opinião.

O funil descarta duas vezes, em granularidades diferentes: o **Passo 2** joga
fora *tópicos* antes de lê-los (barato, decisão pelo título); o **Passo 4** joga
fora *regras* depois de extraídas (preciso, decisão regra a regra). Um não
substitui o outro — o Passo 2 evita gastar extração, o Passo 4 pega o que
escapou.

**Os Passos 1 e 2 são pré-processamento**: nenhum produz regra, só decidem o
que será lido. São as únicas etapas cujo resultado dá para conferir a olho
antes de gastar a extração, e por isso gravam tudo em disco.

---

## Passo 1 — Detectar bordas (sem LLM)

**Objetivo:** entregar à LLM um assunto por chamada, nunca um corte arbitrário
no meio de uma explicação.

**Script:** `libras_pipeline/extraction/chunk_topicos.py`

### Por que não fatiar por página fixa

O fatiamento anterior usava janelas de 15 páginas. Medido no Cap.5 da
Gramática: **10 dos 13 cortes internos (76%) caem no meio de um tópico**, e a
janela mediana tem **6.081 tokens** (máx. 10.573) — o modelo recebe vários
assuntos misturados e precisa achar sozinho onde um termina.

### Definições

1. **Fronteira** — página que inicia um tópico.
2. **Tópico** — da fronteira até a página anterior à fronteira seguinte.
3. **Trecho** — o que vai em **uma** chamada de LLM: tópicos consecutivos
   agrupados até o orçamento de tokens. Tópico maior que o orçamento é partido
   por página, e **cada parte repete o cabeçalho do tópico**, marcada
   `parte i de n` — é isso que impede a perda de contexto ao subdividir.

### Como as fronteiras são detectadas

Duas fontes, unidas:

**(a) Outline do PDF** (bookmarks), percorrido **recursivamente em todos os
níveis**. Rasar a recursão custa caro: uma varredura de um nível só encontrou
3 fronteiras no ASL for Dummies, que tem 49 na faixa.

**(b) Título detectado no texto** — para onde o outline é raso ou não confiável.

### Filtros, e o sintoma que motivou cada um

| Filtro | Sintoma observado |
|---|---|
| **Descartar âncora-lixo** (`_7jjy9o4k5753`) | **176 das 211 entradas (83%)** do outline da Gramática são âncoras internas de editor. Apontam para posições arbitrárias — p.176, p.243 e p.259 caem em meio de prosa, sem título nenhum. Usá-las como fronteira reintroduz exatamente o corte no meio do assunto. |
| **Modo adaptativo** (`numerado` × `prosa`) | O detector conta títulos numerados na faixa. Se o documento usa numeração (≥5 ocorrências), ela é o sinal confiável e o modo prosa fica desligado — sem isso, `1. Sinais monomorfêmicos…` (item de lista) e `GLOSA E SIGNIFICADO` (cabeçalho de tabela) entravam como se fossem seção. |
| **`topic_prefix`** (config) | Restringe a fronteira ao capítulo em foco: com `topic_prefix: 5`, só `5.x` conta. Evita numeração de listas e de outros capítulos. |
| **Palavra funcional** (modo prosa) | Em livro sem numeração, as seções são linhas em MAIÚSCULAS — mas **glosas também são maiúsculas**. O que separa é linguístico: *glosa não realiza artigo nem preposição*. Exigir uma palavra funcional (`A`, `DE`, `COM`…) aceita `A ORDEM BÁSICA DA FRASE` e rejeita `IX GOSTA FUTEBOL`. |

### Formato do trecho entregue à LLM

```
=== DOCUMENTO: Gramática da Libras Vol.1 (INES/Quadros et al.) — Cap.5 ===
=== TÓPICO: 5.4.3.2. Processos de composição dos sinais da Língua de Sinais ===
=== TRECHO: páginas 198-200 (parte 1 de 2 do mesmo tópico) ===

[p.198]
5.4.3.2. Processos de composição dos sinais...
 Em termos práticos, a composição realiza-se por duas ou mais unidades...

[p.199]
...
```

- O **cabeçalho de tópico** dá a identidade do assunto mesmo quando o tópico
  foi subdividido.
- Os marcadores **`[p.N]` inline** mantêm `fonte_pagina` e `fonte_citacao`
  rastreáveis quando o trecho cruza páginas. `N` é o índice 0-based do pypdf,
  **não** o número impresso.

### Verificação automática

Ao gerar, o script confere que a união dos trechos cobre a faixa configurada
**exatamente uma vez** — sem furo e sem sobreposição — e imprime `OK` ou
`FALHOU`. Nenhum trecho de texto pode sumir nem ser processado duas vezes.

### Saída

`libras_pipeline/extraction/chunks/<slug>/`
- `manifest.csv` — índice ordenado do capítulo (a "ordem oficial")
- `NNN_<titulo>.txt` — o texto exato que será enviado ao modelo, revisável
  antes de gastar GPU

Colunas do `manifest.csv`:

| Coluna | O que é |
|---|---|
| `n`, `arquivo` | ordem e nome do `.txt` correspondente |
| `topico` | título que vai no cabeçalho do trecho |
| `nivel_outline` | profundidade no bookmark do PDF; **`-1` = não estava no outline**, título veio do detector de texto. Metadado descritivo — não influencia o fatiamento. Serve de diagnóstico: muitos `-1` indicam que os bookmarks do documento não cobrem as próprias seções. |
| `pagina_ini`, `pagina_fim`, `n_paginas` | faixa coberta (índice 0-based do pypdf) |
| `n_topicos` | quantos tópicos foram agrupados neste trecho |
| `parte` | vazia = tópico inteiro (ou agrupamento, se `n_topicos > 1`); `i/n` = tópico grande partido, este é o pedaço `i` de `n` |
| `tokens` | tamanho medido com o tokenizer do modelo |
| `incluir` | 0/1 — triagem do Passo 2; `extract.py --chunks` pula os `0` |
| `motivo_exclusao` | por que o tópico foi excluído (vazio quando `incluir=1`) |

As três combinações possíveis, com exemplos do Cap.5:

| Caso | `n_topicos` | `parte` | Exemplo |
|---|---|---|---|
| tópico inteiro | 1 | vazia | #1 · p.174 · 480 tok · `5. Aspectos gerais da morfologia` |
| tópicos agrupados | >1 | vazia | #3 · p.177-181 · 1.890 tok · `5.2. Morfemas em Libras` (2 tópicos) |
| tópico partido | 1 | `i/n` | #46–#50 · p.328-336 · `5.7.5.1` tem 6.256 tokens, virou 5 partes |

Cada parte de um tópico partido **repete o mesmo cabeçalho** e carrega
`parte i de n` — é o que impede a subdivisão de apagar o contexto.

### Uso

```bash
python libras_pipeline/extraction/chunk_topicos.py --book gramatica --budget 2000
```

| Flag | Efeito |
|---|---|
| `--book <trecho>` | filtra a fonte pelo label/slug no `config.yaml` |
| `--budget N` | orçamento de tokens por trecho (default 2000) |
| `--out DIR` | destino (default `extraction/chunks/`) |

---

## Passo 2 — Triagem de tópicos (com LLM)

Nem todo tópico de uma gramática pode gerar regra verificável em texto. Ações
de boca são canal não-manual **por definição**: qualquer regra extraída dali
sairia como `sign2voice` e nunca chegaria ao juiz. Pedagogia e história da
língua estão fora do escopo declarado no próprio prompt de extração. Ler esses
tópicos é gastar GPU para produzir o que será descartado no Passo 4.

**Script:** `triagem_topicos.py` · **Prompt:** `prompts/triagem_topicos.yaml`

### Como decide

Cada **título** distinto do `manifest.csv` vai ao modelo, que responde:

```json
{"incluir": true|false, "motivo": "<no máximo 12 palavras>"}
```

A decisão é pelo título só, e isso é de propósito: descarta-se um tópico
inteiro — às vezes 15 trechos — com uma chamada curta, em vez de ler o texto
todo para depois jogar fora. Os títulos são enviados em batch
(`generate_batch`), e um tópico partido em `n` trechos é decidido **uma vez**.

O prompt manda responder `false` quando o título for **claramente** sobre:

| Grupo | Exemplos de termo |
|---|---|
| canal não-manual | boca, ações-de-boca, articulação-boca, expressão facial, olhar, cabeça, tronco |
| espaço, movimento, forma da mão | uso do espaço, localização, trajetória, configuração de mão, orientação |
| visualidade e iconicidade | gesto, classificador imagético, transferência de incorporação/localização |
| não é estrutura da língua | ensino, pedagogia, história, política linguística, tecnologia, corpus |

### Duas salvaguardas contra perder conteúdo

- **Na dúvida, inclui.** O prompt é explícito: o critério é "claramente sobre",
  não "possivelmente relacionado a". Incluir um tópico inútil custa uma chamada
  de extração; excluir um tópico útil perde as regras dele para sempre.
- **Resposta ilegível vira incluir.** O parse é tolerante e o default de falha
  é `incluir=1` — uma triagem que quebra não pode ser a causa de um tópico
  sumir silenciosamente.

Nada é apagado: os `.txt` dos tópicos excluídos continuam em disco, e editar
`incluir` no `manifest.csv` reverte caso a caso.

### Uso

```bash
docker compose exec -e CUDA_VISIBLE_DEVICES=<N> judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/extraction/triagem_topicos.py --book gramatica'
```

### Por que não uma lista declarada à mão

Uma lista de prefixos por livro (`excluir: ["5.6", "5.7.4"]`) foi implementada
e descartada: exige conhecer o sumário de cada documento novo de antemão, o que
quebra a premissa de funcionar automaticamente para qualquer PDF. A decisão por
título vale para livro e artigo, em português ou inglês, sem configuração.

### Evidência que motiva o passo

Rendimento por seção na extração anterior do Cap.5 — quanto cada uma produziu,
e quanto disso era `voice2sign`, o único canal que chega ao juiz:

| Seção | Regras extraídas | Das quais `voice2sign` |
|---|---:|---:|
| 5.4 Formação/composição | 14 | 6 (42%) |
| 5.5 Flexão/concordância | 16 | 1 (6%) |
| **5.6 Ações-boca** | 26 | **1 (3%)** |
| **5.7 Desc. imagéticas + ensino** | 10 | **0 (0%)** |
| 5.8 Expressões idiomáticas | 19 | 14 (73%) |

5.6 e 5.7 ocupam **31 dos 63 trechos e 51% dos tokens** do capítulo, e renderam
1 regra `voice2sign` de 36.

> **Cuidado ao ler essa tabela.** O rendimento foi medido com o extrator
> antigo, que é justamente o que se suspeita ser ruim. Ela justifica *existir*
> a triagem, mas não deve virar critério: excluir uma seção por ter rendido
> pouco antes fossiliza a falha do extrator anterior. Por isso o critério do
> prompt é o assunto do título, não o rendimento passado.

---

## Passo 3 — Extrair regras (com LLM)

**Script:** `libras_pipeline/extraction/extract.py` ·
**Prompt:** `prompts/extract_rules.yaml` (formato AUTOMAT)

Uma chamada por trecho. O modelo devolve `{"rules": [...]}`; cada regra tem
`titulo · descricao · gatilho · verificavel_por_texto · exemplos ·
fonte_pagina · fonte_citacao · categoria`.

O prompt separa explicitamente o **gatilho** (a condição, o "quando") da
**determinação** (o efeito na glosa, o "então") — sem essa separação as regras
saem vagas demais para o juiz decidir "respeita ou viola".

Ele também carrega uma **definição formal de glosa**, que delimita o que pode
virar regra verificável: a glosa carrega *quais sinais e em que ordem*; não
carrega expressão facial, uso do espaço, movimento nem configuração de mão.

**Duas decisões de robustez, ambas por falha observada:**

- **Validação item a item** — uma regra com campo faltando é descartada
  sozinha, sem derrubar as outras do mesmo trecho. Antes, um `gatilho` ausente
  matava a lista inteira.
- **ID atribuído por código**, não pelo modelo (`LIBRAS.SINTAXE.001`). Cada
  trecho é uma chamada isolada; o modelo não sabe o que já foi numerado, então
  IDs vindos dele colidiriam. O modelo escolhe só a `categoria`.

Cada rodada grava também `<slug>_regras.raw.txt` (resposta crua), o que
permite reconstruir o CSV **sem GPU** via `--from-raw` e auditar qualquer
regra até o texto que a gerou.

> **Onde o canal é decidido, hoje:** `verificavel_por_texto` é preenchido pela
> **LLM aqui na extração**, não no Passo 3 — o Passo 3.1 apenas *aplica* o
> campo. A alternativa (extrair tudo sem canal e classificar depois, numa
> chamada dedicada) é viável e talvez mais precisa, já que isolaria a decisão;
> não foi implementada.

---

## Passos 4 e 5 — Filtrar e simplificar

A extração produz uma lista **crua**: cada trecho foi processado isolado, então
a mesma regra reaparece em trechos vizinhos, com outras palavras. O Passo 3
transforma isso numa lista utilizável.

### Passo 4 — Filtrar regras por canal — `classify_pipeline.py`

Três operações mecânicas, sempre:

1. **Junta as fontes.** Lê *todos* os `extraction/output/*_regras.csv` — os dois
   livros e as notas de consultoria — num pool único.
2. **Renumera IDs em colisão.** Cada fonte numera do 1 por categoria, então dois
   livros geram o mesmo `LIBRAS.SINTAXE.002`.
3. **Separa em dois arquivos** pelo campo `verificavel_por_texto`.

| Regra | Canal | Por quê |
|---|---|---|
| `LIBRAS.SINTAXE.001` — *Ordem básica SVO como dominante* | **voice2sign** | dá para checar lendo a glosa: os sinais estão em SVO ou não |
| `LIBRAS.VERBOS.001` — *Verbos direcionais com concordância espacial* | **sign2voice** | depende de "movimento manual e direção" — a glosa escrita não mostra isso |

As `sign2voice` não são descartadas: ficam guardadas para quando houver vídeo
ou anotação.

#### `--confirmar`: segunda opinião sobre o canal

O canal foi decidido no Passo 3, mas **junto com outros sete campos, numa
resposta só**. Com `--confirmar`, a mesma pergunta é refeita aqui — sozinha,
sobre a regra já pronta, sem o texto do livro à vista. É deliberadamente um
contexto diferente do que decidiu antes: se fosse o mesmo, repetiria o mesmo
viés em vez de checá-lo.

```bash
docker compose exec -e CUDA_VISIBLE_DEVICES=<N> judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/simplification/classify_pipeline.py --confirmar'
```

**A divergência nunca é silenciosa.** O CSV de saída ganha quatro colunas —
`canal_extracao`, `canal_confirmado`, `divergencia`, `motivo_confirmacao` — e
sai um `divergencias_canal.csv` com todos os casos em que as duas decisões não
bateram, para revisão.

**Política quando divergem** (`--politica`):

| Valor | Comportamento |
|---|---|
| `conservadora` *(default)* | qualquer `false` das duas manda a regra para sign2voice |
| `confirmacao` | a segunda opinião decide sozinha |

O default é conservador porque **os dois erros não custam igual**. Uma regra
não-verificável que passa faz o juiz reprovar glosa correta, citando algo que
ele não tem como enxergar — foi exatamente a falha medida antes, com 20 regras
de articulação-boca marcadas como verificáveis em texto. Já uma regra
verificável que sai por engano só reduz cobertura: o juiz abstém
(`nao_coberto`), que é um resultado honesto.

Se o parse da confirmação falhar, **mantém-se a decisão da extração**, marcada
como tal no motivo — uma confirmação quebrada não pode mudar canal por acidente.

### Passo 5 — Fundir regras equivalentes — `merge_rules.py` (com LLM)

Aqui está o trabalho de verdade. Processa **por categoria, em rodadas**: pega a
lista já consolidada (vazia na 1ª rodada) + um lote de 15 candidatas novas, e
pede a lista atualizada. Regras que dizem a mesma coisa viram uma; regras que se
completam são fundidas.

Efeito medido: **81 candidatas → 49 regras finais**.

Exemplo real — a fusão que mais agregou, 8 candidatas numa regra só:

```
[LIBRAS.EXPRESSOES-IDIOMATICAS.3]  Expressões idiomáticas com significado não literal

ids_origem: EXPRESSOES-IDIOMATICAS.007, .008, .011, .013, .014, .017, .018, .019

justificativa_fusao: "Todas as candidatas descrevem expressões idiomáticas em
Libras com significado não literal, baseadas em regularidade, convencionalidade,
metaforização, uso corporal e variação, sendo fenômenos distintos apenas em
foco, mas unificados pelo núcleo comum de significação."
```

As 8 candidatas eram variações do mesmo fato, extraídas de trechos diferentes:
*"reconhecidas por regularidade"*, *"podem ser constituídas por um ou mais
sinais"*, *"refletem experiências culturais"*, *"com base metafórica"*, *"com
metáfora estrutural"*, *"com significado convencional"*…

Dois campos existem para tornar a fusão **auditável**: `ids_origem` rastreia
cada regra final até as candidatas do Passo 3, e `justificativa_fusao` registra
por que o modelo as considerou a mesma regra. Dá para desfazer qualquer fusão
que não convença.

Três redes de segurança, todas por falha observada na prática: item inválido não
derruba o lote · candidata omitida pelo modelo volta sozinha como regra própria ·
`ids_origem` deduplicado quando a mesma candidata é reivindicada duas vezes.

### Passo 5b — Comparar com uma base existente — `compare_rules.py` (opcional)

Classifica cada candidata nova contra a base em `ja_temos` / `nao_temos` /
`conflito` / `parcial`. **Não altera a base** — gera CSV para revisão humana.

> **Limite conhecido:** a comparação é estática, regra contra regra. Um conflito
> que só aparece **quando aplicado a uma frase** passa como `parcial`.

---

## Resultado do teste — Gramática da Libras Vol.1, Cap.5

Passo 1 executado sobre p.174–377 (204 páginas), orçamento de 2.000 tokens,
contagem com o tokenizer do próprio Qwen3.8-27B.

| Métrica | Janela fixa (antes) | Por tópico (agora) |
|---|---|---|
| Trechos | 14 | **63** |
| Tokens por trecho (mediana) | 6.081 | **1.445** |
| Tokens (máx.) | 10.573 | **1.999** |
| Cortes no meio de tópico | 10 de 13 (76%) | **0** |

**Fronteiras:** 44 tópicos — 29 do outline + 15 do texto; 0 âncoras-lixo e 0
falsos positivos remanescentes. **Cobertura:** p.174–377 exatamente uma vez,
sem furo nem sobreposição (86.910 tokens no total).

**Composição dos 63 trechos:** 12 são um tópico inteiro · 7 agrupam mais de um
tópico pequeno · 44 são partes de tópicos maiores que o orçamento.

> **Custo:** 63 chamadas contra 14. A extração deste capítulo passa de ~14 para
> ~63 chamadas de LLM — o ganho de contexto é pago em tempo de GPU. Com
> `--budget 3000` o total cai para ~40 trechos, se o custo pesar.

### Índice dos trechos

| # | Páginas | Pgs | Tokens | Tipo | Tópico |
|---:|---|---:|---:|---|---|
| 1 | p.174–174 | 1 | 480 | tópico inteiro | 5. Aspectos gerais da morfologia das Línguas de Sinais |
| 2 | p.175–176 | 2 | 1645 | tópico inteiro | 5.1. Morfologia e modalidade |
| 3 | p.177–181 | 5 | 1890 | 2 tópicos | 5.2. Morfemas em Libras |
| 4 | p.182–186 | 5 | 1999 | parte 1/3 | 5.2.2. Morfemas lexicais e gramaticais |
| 5 | p.187–191 | 5 | 1913 | parte 2/3 | 5.2.2. Morfemas lexicais e gramaticais |
| 6 | p.192–192 | 1 | 429 | parte 3/3 | 5.2.2. Morfemas lexicais e gramaticais |
| 7 | p.193–195 | 3 | 1722 | 2 tópicos | 5.3. A expansão lexical da Língua de Sinais brasileira |
| 8 | p.196–197 | 2 | 614 | tópico inteiro | 5.4.3.1 Caracterização dos compostos em Língua de Sinais |
| 9 | p.198–200 | 3 | 1620 | parte 1/2 | 5.4.3.2. Processos de composição dos sinais da Língua de Sinais |
| 10 | p.201–205 | 5 | 1434 | parte 2/2 | 5.4.3.2. Processos de composição dos sinais da Língua de Sinais |
| 11 | p.206–208 | 3 | 1069 | tópico inteiro | 5.4.4 Derivação |
| 12 | p.209–211 | 3 | 1602 | tópico inteiro | 5.4.4.1 A distinção entre nome e verbo em Libras |
| 13 | p.212–212 | 1 | 482 | tópico inteiro | 5.5. Flexão |
| 14 | p.213–217 | 5 | 1917 | parte 1/3 | 5.5.1 Concordância verbal |
| 15 | p.218–222 | 5 | 1912 | parte 2/3 | 5.5.1 Concordância verbal |
| 16 | p.223–224 | 2 | 447 | parte 3/3 | 5.5.1 Concordância verbal |
| 17 | p.225–227 | 3 | 1062 | tópico inteiro | 5.5.2 Pluralidade verbal |
| 18 | p.228–231 | 4 | 1497 | tópico inteiro | 5.5.3 A representação da morfologia na escrita |
| 19 | p.232–235 | 4 | 960 | 2 tópicos | 5.5.3.2.1 Movimentos Diferentes |
| 20 | p.236–237 | 2 | 1613 | parte 1/2 | 5.6 Ações-boca: morfemas-boca, articulação-boca  e gestos-boca |
| 21 | p.238–239 | 2 | 1339 | parte 2/2 | 5.6 Ações-boca: morfemas-boca, articulação-boca  e gestos-boca |
| 22 | p.240–241 | 2 | 1227 | parte 1/2 | 5.6.2 Ações de boca: morfemas-boca,  articulações-boca e gestos-boca |
| 23 | p.242–243 | 2 | 1312 | parte 2/2 | 5.6.2 Ações de boca: morfemas-boca,  articulações-boca e gestos-boca |
| 24 | p.244–248 | 5 | 1796 | parte 1/2 | 5.6.2.1 Morfemas-boca |
| 25 | p.249–254 | 6 | 1390 | parte 2/2 | 5.6.2.1 Morfemas-boca |
| 26 | p.255–258 | 4 | 1825 | parte 1/3 | 5.6.2.2 Gestos-boca |
| 27 | p.259–260 | 2 | 1425 | parte 2/3 | 5.6.2.2 Gestos-boca |
| 28 | p.261–261 | 1 | 654 | parte 3/3 | 5.6.2.2 Gestos-boca |
| 29 | p.262–266 | 5 | 1735 | parte 1/6 | 5.6.2.3.2 Categorias de articulações-boca da Libras |
| 30 | p.267–271 | 5 | 1950 | parte 2/6 | 5.6.2.3.2 Categorias de articulações-boca da Libras |
| 31 | p.272–277 | 6 | 1950 | parte 3/6 | 5.6.2.3.2 Categorias de articulações-boca da Libras |
| 32 | p.278–283 | 6 | 1736 | parte 4/6 | 5.6.2.3.2 Categorias de articulações-boca da Libras |
| 33 | p.284–289 | 6 | 1956 | parte 5/6 | 5.6.2.3.2 Categorias de articulações-boca da Libras |
| 34 | p.290–301 | 12 | 1887 | parte 6/6 | 5.6.2.3.2 Categorias de articulações-boca da Libras |
| 35 | p.302–305 | 4 | 1966 | parte 1/2 | 5.7 Descrições Imagéticas e Classificadores |
| 36 | p.306–307 | 2 | 1520 | parte 2/2 | 5.7 Descrições Imagéticas e Classificadores |
| 37 | p.308–310 | 3 | 1458 | parte 1/2 | 5.7.1 Línguas de Sinais primárias e iconicização da experiência dos sujeitos Sur |
| 38 | p.311–311 | 1 | 710 | parte 2/2 | 5.7.1 Línguas de Sinais primárias e iconicização da experiência dos sujeitos Sur |
| 39 | p.312–314 | 3 | 1579 | 3 tópicos | 5.7.2 Elementos altamente icônicos da Libras: as Descrições Imagéticas |
| 40 | p.315–318 | 4 | 1710 | 3 tópicos | 5.7.2.5 Transferência de Incorporação |
| 41 | p.319–320 | 2 | 1415 | parte 1/3 | 5.7.4  Aplicando a visualidade ao processo de ensino e aprendizagem dos Sujeitos |
| 42 | p.321–322 | 2 | 1346 | parte 2/3 | 5.7.4  Aplicando a visualidade ao processo de ensino e aprendizagem dos Sujeitos |
| 43 | p.323–324 | 2 | 1541 | parte 3/3 | 5.7.4  Aplicando a visualidade ao processo de ensino e aprendizagem dos Sujeitos |
| 44 | p.325–326 | 2 | 1474 | parte 1/2 | 5.7.5. Visualidade na/para/da educação de Surdos |
| 45 | p.327–327 | 1 | 643 | parte 2/2 | 5.7.5. Visualidade na/para/da educação de Surdos |
| 46 | p.328–329 | 2 | 1303 | parte 1/5 | 5.7.5.1. Sugestões e parâmetros para a implementação de pro- |
| 47 | p.330–331 | 2 | 1319 | parte 2/5 | 5.7.5.1. Sugestões e parâmetros para a implementação de pro- |
| 48 | p.332–333 | 2 | 1534 | parte 3/5 | 5.7.5.1. Sugestões e parâmetros para a implementação de pro- |
| 49 | p.334–335 | 2 | 1322 | parte 4/5 | 5.7.5.1. Sugestões e parâmetros para a implementação de pro- |
| 50 | p.336–336 | 1 | 778 | parte 5/5 | 5.7.5.1. Sugestões e parâmetros para a implementação de pro- |
| 51 | p.337–338 | 2 | 1426 | parte 1/2 | 5.8 Expressões idiomáticas em Língua de Sinais brasileira |
| 52 | p.339–340 | 2 | 1167 | parte 2/2 | 5.8 Expressões idiomáticas em Língua de Sinais brasileira |
| 53 | p.341–345 | 5 | 1832 | 2 tópicos | 5.8.2 Expressões Idiomáticas em Língua de Sinais brasileira: ponto de vista lexi |
| 54 | p.346–348 | 3 | 1247 | tópico inteiro | 5.8.4 Expressões Idiomáticas em Língua de Sinais brasileira: ponto de vista idio |
| 55 | p.349–353 | 5 | 1993 | parte 1/3 | 5.8.5 Expressões Idiomáticas em Língua de Sinais brasileira: ponto de vista semâ |
| 56 | p.354–359 | 6 | 1873 | parte 2/3 | 5.8.5 Expressões Idiomáticas em Língua de Sinais brasileira: ponto de vista semâ |
| 57 | p.360–361 | 2 | 536 | parte 3/3 | 5.8.5 Expressões Idiomáticas em Língua de Sinais brasileira: ponto de vista semâ |
| 58 | p.362–362 | 1 | 302 | tópico inteiro | 5.8.6 Expressões Idiomáticas e Falsos Cognatos |
| 59 | p.363–365 | 3 | 1445 | parte 1/2 | 5.8.7 Expressões Idiomáticas em Língua de Sinais brasileira: ponto de vista meta |
| 60 | p.366–367 | 2 | 929 | parte 2/2 | 5.8.7 Expressões Idiomáticas em Língua de Sinais brasileira: ponto de vista meta |
| 61 | p.368–371 | 4 | 1427 | 2 tópicos | 5.8.7.3 Metáforas ontológicas |
| 62 | p.372–375 | 4 | 1628 | tópico inteiro | 5.8.9 Expressões Idiomáticas em Língua de Sinais brasileira: ponto de vista sint |
| 63 | p.376–377 | 2 | 998 | tópico inteiro | 5.8.10 Em síntese |

---

## Aplicando a um documento novo

Adicionar uma entrada em `books:` no `config.yaml`:

```yaml
  - label: "Nome legível da fonte"      # vai no cabeçalho de cada trecho
    slug: nome_curto                     # nomeia os arquivos de saída
    path: documento.pdf
    start_page: 174                      # índice 0-based do pypdf
    end_page: 377
    topic_prefix: 5                      # opcional: restringe ao capítulo
```

Depois: rodar o Passo 1, **abrir o `manifest.csv` e conferir os títulos**. Se
vierem `_xxxx` ou nomes que não são seção, o documento usa um sinal ainda não
coberto — vale inspecionar antes de gastar GPU. É justamente para permitir essa
conferência barata que o Passo 1 grava os trechos em disco.

## Limitações conhecidas

- **Fronteira depende de sinal tipográfico.** Documento sem outline útil,
  sem numeração e sem título em maiúsculas não é fatiável por este método.
  Um passo de detecção por LLM cobriria esse caso; não foi implementado.
- **A subdivisão de tópico grande é por página**, não por parágrafo — uma
  parte ainda pode terminar no meio de uma frase, embora dentro do mesmo
  assunto e com o cabeçalho preservado.
- **`--budget` não é calibrado empiricamente.** 2.000 tokens foi escolhido por
  deixar a mediana confortavelmente abaixo do limite; nenhum teste comparou
  qualidade de extração entre orçamentos.
- **O efeito na qualidade das regras ainda não foi medido.** Tudo acima mede
  o *fatiamento*. Se isso melhora a extração, só uma rodada comparada dirá.
