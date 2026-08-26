# Proposta — agrupar regras por nó sintático e julgar a partir da análise da frase

Duas mudanças acopladas: **reorganizar as categorias de regra em três eixos**
e **etiquetar a glosa sintaticamente antes de julgar**, recuperando só as
regras dos nós presentes. Documento de proposta — nada disso está
implementado ainda.

---

## 1. O problema que motiva

### 1.1 As categorias de hoje misturam dois eixos

Medição sobre as 215 regras extraídas de Libras:

| Categoria | Regras | Delas, com canal **não-manual** |
|---|---|---|
| morfologia | 39 | 5 (13%) |
| sintaxe | 38 | 11 (29%) |
| verbos | 29 | 1 (3%) |
| expressoes-idiomaticas | 21 | 5 (24%) |
| pronomes | 17 | 3 (18%) |
| tempo-aspecto | 16 | 2 (12%) |
| foco | 15 | 5 (33%) |
| classificadores | 15 | 4 (27%) |
| pergunta | 13 | 6 (46%) |
| negacao | 9 | 6 (67%) |
| concordancia | 3 | 1 (33%) |
| **total** | **215** | **49 (23%)** |

**23% das regras dependem de canal não-manual, espalhadas por todas as 11
categorias.** A categoria diz *domínio gramatical*, mas quem decide se a regra
serve ao juiz de texto é o *canal*. São duas perguntas diferentes numa coluna
só.

Somam-se problemas menores, todos verificados no dado:
- `foco` e `pergunta` descrevem os mesmos fenômenos ("Construções de foco com
  duplicação final" x "Interrogativos em foco seguem estrutura de duplicação")
- `concordancia` (3 regras) é fragmento de `verbos` (29)
- `expressoes-idiomaticas` virou gaveta — contém até "Técnicas de visualidade
  para treinamento de sinalização", que não é regra

### 1.2 Sem âncora, o juiz cita a regra mais genérica

Na rodada de avaliação, as 49 regras foram despejadas inteiras no prompt e o
modelo escolheu quais citar. Resultado: **`LIBRAS.SINTAXE.1` ("ordem básica
SVO") foi citada em 8 das 8 frases** — inclusive para julgar
`EU PODER IR PARA CASA HOJE`, onde o problema real era a preposição, não a
ordem.

---

## 2. Proposta A — três eixos, cada um com uma pergunta

| Eixo | Pergunta que responde | Valores | Serve para |
|---|---|---|---|
| **Canal** | a regra aparece no texto da glosa? | `manual` · `nao-manual` · `misto` | separar voice2sign de sign2voice (substitui o booleano atual) |
| **Nível** | que camada da língua? | `sintaxe` · `morfologia` · `lexico` | substitui as 11 categorias, colapsadas em 5 |
| **Nó** | onde na árvore a regra se aplica? | `SUJ` `PRED` `V` `COMPL` `OBJDIR` `OBJIND` `PREP` `NOME` `ADJN` `ADJV` `S-INT[QU]` | **só regras sintáticas** — habilita a Proposta B |

Consolidação do eixo *Nível* (11 -> 5):

```
sintaxe    <- sintaxe + foco + pergunta + posição de advérbio
verbos     <- verbos + concordancia + aspecto verbal
morfologia <- morfologia + classificadores
pronomes   <- pronomes (IX)
lexico     <- expressões idiomáticas, limpas do que é não-manual
```

### Por que o eixo "Nó" não substitui os outros

As produções da Tânia (`SUJ`, `PRED`, `PREP`, `ADJN`...) são **nós de árvore**.
Funcionam muito bem para regras estruturais — "preposição locativa é nula" é
literalmente uma regra do nó `PREP`; "adjetivo depois do nome" é `NOME -> ADJN`.

Mas **cerca de metade das regras não vive num nó**: morfologia (39) e
classificadores (15) descrevem o que acontece *dentro* de um sinal — ou seja,
dentro de um terminal da árvore; e as 49 regras de canal não-manual acontecem
*fora* dela. Forçá-las num nó criaria categorias falsas. Por isso três eixos,
não um.

---

## 3. Proposta B — análise sintática antes do julgamento

Em vez de oferecer a base inteira em toda decisão, **etiquetar a glosa** e
**recuperar apenas as regras dos nós presentes** naquela frase.

```
frase:  "Posso ir para casa hoje?"
glosa:   EU      PODER IR   PARA    CASA   HOJE
nó:      SUJ     V          PREP    NOME   ADJN
                            ^^^^

nós presentes -- SUJ . V . PREP . NOME . ADJN

regras recuperadas (só as desses nós):
   SUJ   -> sujeito pode ser nulo com referente presente
   PREP  -> preposição locativa é sempre NULA na glosa      << dispara
   ADJN  -> advérbio de tempo pode modificar o locativo

veredito: invalido
regra citada: TANIA.SINTAXE.2
sugestão: EU PODER IR CASA HOJE
```

### O que isso resolve

- **Recuperação dirigida em vez de despejo** — a regra citada passa a ser
  consequência do que está na frase, não escolha livre do modelo.
- **Abstenção deixa de ser palavra e vira verificação** — nó presente sem
  nenhuma regra associada é `nao_coberto` *comprovável*.
- **Entrega a análise sintática palavra a palavra**, no formato da Tânia.
- **Auditabilidade** — erro fica visível na etiquetagem, não escondido no
  julgamento.

### Recomendação de escopo

Começar por **etiquetagem rasa** — qual nó cada sinal ocupa — e **não** pela
árvore completa com todos os níveis de aninhamento. É bem mais robusta a erro
e já entrega quase todo o ganho de recuperação. A árvore cheia, no formato do
PDF da Tânia, vira passo seguinte se fizer falta.

---

## 4. Isso já existe na literatura? **Sim** — e o precedente é forte

### 4.1 O VLibras já faz exatamente isso (UFPB, 2015)

Da monografia de Oliveira (2015), que lemos na íntegra:

> **§4.2 Classificação** — "O módulo de classificação baseia-se em duas
> abordagens: morfológica e sintática. Na classificação sintática **é analisada
> a função que as palavras desempenham dentro da oração**, ou seja, a relação
> sintática entre as palavras. [...] é então aplicado um processo de análise
> sintática que resulta em uma estrutura conhecida como **árvore sintática**,
> que agrupa os itens léxicos em diversas unidades sintáticas."
>
> **§4.3 Adequação** — só *depois* disso as regras de tradução são aplicadas.

Ferramentas: **Aelius** (Alencar, 2010) para etiquetagem morfossintática, com
o conjunto de etiquetas do corpus **Tycho-Brahe**; analisador sintático com
gramática gerativa (Alencar, 2011).

**E a análise sintática foi justamente a contribuição deles.** Na tabela
comparativa da monografia, a linha "Análise sintática" aparece como **"-" na
solução anterior (Araújo et al., 2014)** e **"X" na solução proposta**. O
ganho medido: **82% de compreensão contra 45%**, com 23 usuários de Libras
(incluindo surdos), em teste cego.

### 4.2 Precedente internacional — língua de sinais espanhola

López-Ludeña et al. (2014), citado na mesma monografia:

> "A arquitetura da solução é composta por um analisador, um módulo de
> transferência e um gerador. O analisador é responsável pela identificação das
> dependências [...] produzindo uma **árvore de dependência** que representa as
> relações funcionais entre as palavras. [...] o gerador é responsável pela
> ordenação das palavras **considerando a árvore de dependência da LSE**,
> produzindo uma sequência de glosas em LSE."

Mesma arquitetura: analisa -> estrutura -> aplica regras sobre a estrutura.

### 4.3 O Libras-UFPel usa um esquema de categorias muito próximo do nosso

O corpus da UFPel (PROPOR 2026) organiza a anotação em categorias que
correspondem quase 1:1 aos nossos eixos:

| Libras-UFPel | Nosso eixo equivalente |
|---|---|
| Sinais **lexicais** — ID-gloss em maiúscula, variantes indexadas (`CASA.1`) | Nível: `lexico` |
| **Parcialmente lexicais** — classificadores (`DV:ABRIR_LIVRO`), apontações (`IX-mulher`) | Nível: `morfologia` / Nó: `SUJ`, `OBJ` |
| **Não-lexicais** — gestos espontâneos (`GES:`) | descartável — "ruído gestual" |
| **Tiers independentes** para sobrancelhas, olhar, articulação-boca | **Canal: `nao-manual`** |
| Datilologia (`FS:`), negação incorporada (`NÃO_GOSTAR`) | Nível: `morfologia` |

O ponto mais relevante: eles **separam os marcadores não-manuais em tiers
próprios**, exatamente a separação de canal que propomos — mas já formalizada
e em uso, seguindo o padrão internacional de Johnston (2019, 2024).

### 4.4 O que Lima (2022) provavelmente traz

O artigo em periódico descreve "uma **linguagem formal de descrição de regras
sintático-semânticas**" e "uma gramática específica para tradução de Libras" —
que é, no nome, o mesmo objetivo desta proposta. **Não lemos** (paywall
Cambridge), então isto é expectativa, não fato verificado.

---

## 5. Riscos, com um deles já documentado por quem tentou

| Risco | Descrição |
|---|---|
| **Propagação de erro** | Árvore errada leva a regra errada. Passam a ser dois passos de LLM e os erros compõem. Contrapartida: o erro fica *visível* na etiquetagem — hoje ele já existe, só que invisível. |
| **Árvore nula** | A monografia relata: sentenças não reconhecidas pela gramática produzem "árvore sintática nula", e alerta que **"a árvore sintática nula nem sempre retrata a inadequação da estrutura formal, podendo ser uma limitação da gramática do analisador"**. Ou seja: falha do parser pode ser confundida com frase errada. Nosso `nao_coberto` precisa distinguir os dois casos. |
| **Cobertura estreita** | A gramática da Tânia tem só 6 sentenças transcritas. Frases fora desse conjunto cairão em `nao_coberto` com frequência — honesto, mas reduz a taxa de decisão. |

---

## 6. Diferença entre a nossa proposta e o que o VLibras fez

Não é a mesma coisa, e vale explicitar:

| | VLibras (2015) | Nossa proposta |
|---|---|---|
| Objetivo | **gerar** glosa a partir do português | **validar** uma glosa já existente |
| Parser | gramática gerativa formal (Aelius) sobre o **português** | etiquetagem por LLM sobre a **glosa** |
| Papel da árvore | decidir como transformar | decidir **quais regras consultar** |
| Saída | glosa | veredito + **regra citada** + sugestão |

A diferença central: eles analisam a frase-fonte em português para produzir a
glosa; nós analisamos a **glosa** para escolher as regras que a julgam. O
precedente valida a **arquitetura** (analisar antes de aplicar regras), não o
uso específico.

---

## 7. Ordem de implementação sugerida

1. **Reetiquetar as regras existentes nos três eixos** — sem GPU, é
   reclassificação do CSV atual. Já melhora a separação voice2sign/sign2voice.
2. **Definir o vocabulário de nós** a partir das produções da Tânia,
   alinhando nomenclatura ao Libras-UFPel onde couber (`IX:`, `DV:`).
3. **Etiquetador raso** — glosa -> um nó por sinal. Avaliar isoladamente antes
   de plugar no juiz.
4. **Juiz com recuperação por nó** — trocar o despejo das 49 regras pela
   recuperação dirigida.
5. Medir contra o baseline atual, **com conjunto de teste de fonte
   independente** (a lacuna crítica registrada em `SOLUCAO.md`).
