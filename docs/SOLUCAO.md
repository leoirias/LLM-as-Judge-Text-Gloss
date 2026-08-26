# Validação automática de glosa em Libras

## 1. O problema

Dado um par **(frase em português, glosa em Libras)**, decidir se a glosa está
correta — e, quando não está, **dizer por quê citando a regra violada** e
sugerir a correção.

O requisito que orienta todo o desenho é **transparência**: o sistema não pode
devolver só "certo/errado". Precisa mostrar **em que regra se apoiou**. E
quando nenhuma regra cobre o fenômeno, precisa **dizer isso** em vez de
inventar um veredito.

Daí o espaço de decisão de **três estados**, não dois:

| Estado | Significado |
|---|---|
| `valido` | a glosa preserva o sentido e respeita as regras |
| `invalido` | viola uma regra específica, que é citada por ID |
| `nao_coberto` | **nenhuma regra cobre o fenômeno** — abstenção honesta |

`nao_coberto` **não conta como erro nem acerto** e fica fora da acurácia.
Abster-se é o comportamento correto diante de uma base de regras incompleta.

---

## 2. A arquitetura em três etapas

```
   PDFs (livros, notas de consultoria)
              │
       ┌──────▼──────┐
       │  ETAPA 1    │  extração        documento → regras candidatas
       │  extraction │
       └──────┬──────┘
              │  CSV: id, categoria, titulo, descricao, gatilho,
              │       verificavel_por_texto, exemplos, fonte_*
       ┌──────▼──────┐
       │  ETAPA 2    │  simplificação   candidatas → grupos → lista final
       │simplification│
       └──────┬──────┘
              │  2.1 separa por CANAL (texto × vídeo)
              │  2.2 funde duplicatas, com justificativa
              │  2.3 compara fonte nova contra a base (opcional)
       ┌──────▼──────┐
       │  ETAPA 3    │  avaliação       texto + glosa → veredito + regra citada
       │  evaluation │
       └─────────────┘
```

Estrutura espelhada para os dois idiomas: `libras_pipeline/` e
`asl_pipeline/`, mesmo código e mesmo formato de CSV. Muda só a configuração
(fontes, prefixo de ID) e o idioma dos prompts.

**Modelo:** Qwen3.8-27B

---

## 3. Etapa 1 — Extração de regras

**Ideia:** transformar texto corrido de gramáticas em regras estruturadas e
citáveis, cada uma com procedência (livro + página + citação literal).

**Passo a passo:**

1. O capítulo é fatiado em **janelas de 15 páginas** — um capítulo inteiro não
   cabe num prompt.
2. Cada página é marcada como `[p.N]` no texto enviado, para a citação ser
   rastreável até a página exata.
3. Uma chamada de LLM por janela devolve as regras daquela janela em JSON.
4. **Validação regra a regra**: uma regra com campo faltando é descartada
   sozinha, sem derrubar as outras da mesma janela.
5. O **ID é atribuído por código** (`LIBRAS.SINTAXE.001`), não pelo modelo —
   cada janela é uma chamada isolada e IDs gerados pelo modelo colidiriam.
6. A resposta crua é salva em `.raw.txt`, permitindo reconstruir o CSV sem
   GPU e auditar qualquer decisão.

**Prompt de extração** (`extraction/prompts/extract_rules.yaml`, resumido):

> Você está extraindo regras gramaticais da Língua Brasileira de Sinais
> (Libras) a partir de um trecho de livro acadêmico de linguística. O objetivo
> é capturar regras que ajudem a produzir/validar uma GLOSA.
>
> **INCLUA** regras de nível de frase ou palavra: ordem dos sinais, morfologia,
> concordância verbal, pronomes (IX), interrogativas, foco, negação,
> classificadores, tempo/aspecto, tópico-comentário.
> **IGNORE** listas de sinais sem padrão, notas de história/documentação,
> variação regional sem relevância estrutural, e comentários bibliográficos.
>
> Cada regra tem os campos: `categoria` (lista fechada), `titulo`,
> `descricao` (o QUE determina), `gatilho` (QUANDO se aplica),
> `verificavel_por_texto`, `exemplos`, `fonte_pagina`, `fonte_citacao`.
>
> `verificavel_por_texto` = `true` se dá para checar olhando só o TEXTO da
> glosa; `false` se depende de canal fora do texto (expressão facial,
> articulação-boca, uso do espaço, movimento).
>
> Não invente regra que o texto não afirma. `fonte_citacao` copiada, não
> parafraseada.

**Fontes processadas:**

| Idioma | Fonte | Páginas | Regras |
|---|---|---|---|
| Libras | Gramática da Libras Vol.1 (INES) — Cap.5 Morfologia | 174–377 | 93 |
| Libras | Estudos Linguísticos (Quadros & Karnopp) — Cap.4 Sintaxe | 123–210 | 45 |
| Libras | Notas de consultoria (Profa. Tânia) | 0–5 | 6 |
| ASL | ASL for Dummies — Caps. 1-13 e Cap.19 | — | 251 |

---

## 4. Etapa 2 — Simplificação

### 4.1 Separação por canal

Toda regra vai para um de dois grupos, pelo campo `verificavel_por_texto`:

- **voice2sign** — verificável no texto da glosa; é o que o juiz usa
- **sign2voice** — depende de vídeo (expressão facial, espaço, movimento);
  fora do escopo de um validador de texto

Esse passo também **renumera IDs em colisão**: cada livro numera do 1 por
categoria, então duas fontes podem gerar o mesmo `LIBRAS.SINTAXE.002`.

Resultado (Libras): **81 voice2sign** e **122 sign2voice**.

### 4.2 Fusão de duplicatas

A mesma regra aparece várias vezes — o livro a explica em páginas diferentes,
ou duas fontes a descrevem com outras palavras. A fusão consolida, **sempre
com justificativa e rastreio** (`ids_origem` aponta para as candidatas
originais).

Processa **por categoria, em rodadas**: consolidado atual + lote de 15
candidatas novas → lista consolidada atualizada.

**Prompt de fusão** (resumido):

> Você está organizando candidatas a regra gramatical da Libras, todas da
> MESMA categoria, para chegar numa lista final SEM DUPLICATAS. Duas
> candidatas viram UMA regra quando descrevem o MESMO fenômeno — mesmo vindas
> de páginas/livros diferentes ou escritas com palavras diferentes.
>
> Regras já consolidadas que nenhuma candidata nova tocar devem ser devolvidas
> **exatamente como estavam**. `ids_origem` acumula TODOS os IDs fundidos —
> nunca remova um que já estava lá. `justificativa_fusao` é **obrigatória**
> quando há 2+ origens.
>
> NÃO funda duas candidatas só porque são da mesma categoria — categoria
> ampla (ex. "sintaxe") cobre vários fenômenos distintos.

**Três redes de segurança**, todas motivadas por falhas observadas na prática:

| Falha observada | Proteção |
|---|---|
| 1 item inválido derrubava o lote inteiro | valida item a item |
| o modelo "esquecia" uma candidata na resposta | ela volta como entrada própria |
| o modelo reivindicava a mesma candidata em 2 regras | fica só na primeira |

Resultado: **81 → 49 regras** (livros) e **8 → 7** (Tânia).

### 4.3 Comparação de fonte nova contra a base

Uma chamada de LLM por candidata, recebendo a base inteira. Classifica em
`ja_temos` / `nao_temos` / `conflito` / `parcial`. **Não altera a base** —
produz um CSV para revisão humana.

---

## 5. Etapa 3 — O juiz

**Passo a passo**, para cada frase **isoladamente** (prompt novo, sem
histórico entre chamadas):

1. Monta o prompt: bloco de regras + frase em português + glosa proposta
2. O modelo devolve JSON com 6 campos obrigatórios
3. Parse tolerante: aceita sinônimos de veredito e deriva o veredito das
   dimensões se o campo faltar
4. Se o parse falhar de vez, vira `nao_coberto` com origem `parse_falhou` —
   distinto de abstenção por falta de regra
5. **Alerta se o modelo citar ID que não existe** na base (alucinação)

**Prompt do juiz** (`evaluation/prompts/judge.yaml`, resumido):

> Você é um validador de glosa de Libras. Recebe uma frase em PORTUGUÊS e uma
> GLOSA proposta. Uma glosa correta REPRESENTA o sentido de forma FLUIDA e
> NATURAL para surdos, respeitando a ESTRUTURA descrita nas regras abaixo.
>
> Julgue DUAS dimensões: **FIDELIDADE** (preserva o sentido?) e
> **NATURALIDADE/ESTRUTURA** (respeita as regras?).
>
> Se NENHUMA regra cobrir o fenômeno, responda `nao_coberto` — não invente
> veredito nem force uma regra que não se aplica. **Abster-se não é reprovar,
> é honestidade sobre os limites da base atual.**
>
> Baseie-se SOMENTE nas regras listadas. Cite o(s) **ID(s) exato(s)** — não
> descreva a regra em texto livre.
>
> Seis campos obrigatórios: `veredito` (exatamente `valido`/`invalido`/
> `nao_coberto`), `representa_sentido` (Sim/Não), `natural_estrutura`
> (Sim/Não), `regras` (lista de IDs), `problema`, `sugestao`.

**Saída** — uma linha por frase:
`Texto · Glosa · Estado · Fidelidade · Naturalidade · Regras · Problema ·
Sugestao · Esperado · Acertou · Origem`

---

## 6. Resultados medidos

### O experimento

8 frases de teste, das quais 5 válidas e 3 inválidas. Três bases de regras
comparadas, **mantendo tudo o mais constante**:

| Base | Origem | Regras |
|---|---|---|
| Tânia | notas de consultoria | 7 |
| Livros | 2 gramáticas acadêmicas | 49 |
| Combinada | as duas | 56 |

### Resultado principal

| Base | Acurácia | Comportamento |
|---|---|---|
| **Tânia (7 regras)** | **5/6 decididos** (83%), 2 abstenções | decide com regra certa, abstém quando não sabe |
| **Livros (49 regras)** | **2/8** (25%) | **reprovou 7 das 8 frases**, inclusive válidas |
| **Combinada (56)** | 4/8 (50%) | — |

**7 regras bem-postas superaram 49.** O volume de regras não é o que importa.

### Por que a base de livros falha

Duas causas distintas, medidas separadamente:

1. **Lacuna de cobertura** — os livros **não têm regra** sobre preposição
   locativa nula nem sobre posição do adjetivo. Verificamos direto no PDF: em
   568 páginas da *Gramática da Libras*, "preposição" aparece em 3 páginas,
   todas incidentais (definição genérica, fenômeno não-manual, tipologia
   geral). Confirmado também com o modelo novo.
2. **Interpretação invertida** — onde há regra, o modelo lê descrição como
   obrigação. `PERGUNTA.1` diz que o interrogativo *"pode* permanecer in situ
   **ou** mover-se"; o juiz aplicou como *"deve* ser movido" e reprovou uma
   frase que a própria regra permite.

> **A conclusão que tiramos:** gramática descritiva registra o que a língua
> *faz*; um validador precisa saber o que a glosa *não pode* conter. Regras de
> ausência ("a preposição nunca aparece") raramente são escritas — são
> inferência do linguista. Por isso as **notas de consultoria** funcionam
> melhor que os **livros acadêmicos**: elas são prescritivas.

### Um resultado que revisamos para baixo

A primeira medição deu **100% para a base da Tânia**. Ao auditar, encontramos
**dois vazamentos**:

| Vazamento | Onde | Efeito |
|---|---|---|
| Exemplo do prompt continha a resposta de um caso | prompt (erro nosso) | 1 caso, só na base de livros |
| 5 das 8 glosas de teste aparecem como **exemplos dentro das regras** da Tânia | inerente à fonte | **sustentava os 100%** |

Corrigidos os dois, o número honesto é **83% com 25% de abstenção**. Mantemos
os três resultados registrados (`resultado_*`, `v2_*`, `v3_*_semex`) para a
comparação ser auditável.

**As duas abstenções são o sistema funcionando como projetado:**
- `PODER EXPLICAR TRATAMENTO` → *"nenhuma regra cobre pergunta polar nem o uso
  de PODER como modal"* — está correto: a Tânia tem essa decisão no documento,
  mas ela não sobreviveu à extração
- `ENFERMEIRA CHAMAR AGORA` → *"a posição de AGORA não está coberta"* — também
  correto

Ou seja, o juiz **identificou lacunas reais da base** em vez de chutar.

---

## 7. O que sabemos que ainda não está resolvido

**Sobre a avaliação:**
- São **8 frases, todas derivadas do mesmo documento** (5 literais + 3
  perturbações deliberadas). **Não mede generalização.** Frases de fonte
  independente são a lacuna mais crítica.
- O vazamento por exemplos é inerente quando a fonte da regra e a fonte do
  teste são o mesmo documento.

**Sobre as regras:**
- 23% das 215 regras extraídas envolvem canal não-manual, espalhadas por todas
  as categorias — sinal de que categoria e canal são eixos distintos sendo
  tratados como um só.
- Decisões da consultoria (modal `PODER`, ordem alternativa do advérbio) não
  sobreviveram à extração.

**Sobre dados:**
- Libras tem ~14 frases anotadas no projeto contra 81 mil pares de ASL.
  Recursos externos existem (ver `LITERATURA.md`) e mudariam esse quadro.

---

## 8. Próximos passos propostos

| # | Ação | Por quê |
|---|---|---|
| 1 | Extrair regras de **fontes prescritivas** (Lima 2022, regras do VLibras) em vez de só gramáticas descritivas | ataca diretamente a causa dos 25% |
| 2 | **Etiquetagem por nó sintático** antes de julgar, recuperando só as regras dos nós presentes na frase | hoje as 49 regras são despejadas no prompt e o modelo cita a mais genérica; também entrega a análise sintática palavra a palavra |
| 3 | Reorganizar categorias em **três eixos** (canal · nível · nó) | hoje um único campo tenta responder duas perguntas |
| 4 | Conjunto de teste de **fonte independente** | única forma de medir generalização de verdade |
| 5 | Adotar protocolo de avaliação já publicado (CLIHC 2023) | evita reinventar metodologia |

---

## Anexo — como reproduzir

```bash
# Etapa 1 — extração (todas as fontes do config)
docker compose exec -e CUDA_VISIBLE_DEVICES=<N> judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/extraction/extract.py'

# Etapa 2.1 — separação por canal (sem GPU)
docker compose exec judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/simplification/classify_pipeline.py'

# Etapa 2.2 — fusão de duplicatas
docker compose exec -e CUDA_VISIBLE_DEVICES=<N> judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/simplification/merge_rules.py'

# Etapa 3 — juiz (--rules escolhe a base, --exp-name evita sobrescrever)
docker compose exec -e CUDA_VISIBLE_DEVICES=<N> judge bash -lc \
  'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/evaluation/run.py \
     --rules <base.csv> --exp-name <nome>'
```

Detalhamento técnico completo (flags, formatos, armadilhas): `docs/PIPELINES.md`.
Mapa da literatura: `docs/LITERATURA.md`.
