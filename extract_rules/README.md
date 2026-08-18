# extract_rules — extração e validação de regras de ASL a partir de livros

Objetivo: capturar conhecimento de gramática ASL (livros/papers) que ajude o
`main_pipeline` a transformar texto em glosa de forma mais **natural e
estruturalmente correta** — pensando à frente na hora em que a glosa vira
vídeo/avatar, onde ordem, marcação temporal e estrutura de frase importam
tanto quanto o vocabulário escolhido.

Duas etapas, cada uma uma chamada de LLM (qwen3-32B, thinking ligado,
config própria em `config.yaml` — separada do `main_pipeline` porque aqui os
outputs são bem mais longos):

```
ASL_for_dummies.pdf (1 capítulo)
        │
        ▼
   extract.py            [LLM, schema-forced JSON]
        │  lê o capítulo, extrai regras candidatas com:
        │  trigger, constraint, exception, evidence_channel, citação
        ▼
   output/chapter02_rules.json
        │
        ▼
   validate.py            [LLM, 1 chamada por regra]
        │  para cada regra, varre TODOS os pares do ouro
        │  (data/pares_ouro.csv + data/pares_review.csv) de uma vez,
        │  aponta quais pares disparam o gatilho e se a glosa bate
        ▼
   output/chapter02_validation.csv
```

## Veredito por regra

- **confirmed** — disparou em >=1 par do ouro, todos batem com a regra.
  Candidata a virar texto novo em `src/main_pipeline/prompts/` (revisão
  humana antes de entrar).
- **contradicted** — disparou, mas o ouro faz diferente do livro. Vira nota
  de pesquisa (o livro descreve ASL geral; a convenção da consultoria pode
  ter escolhido diferente de propósito) — não integra sem confirmar com o
  Jean.
- **partial** — mistura de casos que batem e não batem. Mesmo tratamento dos
  🔴 pontos abertos em `PontosDiscussao.md`: fica pro Jean decidir.
- **unattested** — regra `string-checkable` que nunca disparou nos ~180
  pares do ouro (domínio clínico é estreito; a maior parte da gramática ASL
  geral não aparece nele). Fica pendurada, não vira regra automática.
- **video_reference** — regra `nonmanual`/`spatial` (expressão facial, uso do
  espaço, concordância verbal direcional) que **por natureza** não dá pra
  confirmar contra um ouro só de texto. Não é descartada: vira parte de uma
  base de conhecimento à parte, guardada para quando a glosa alimentar a
  geração de vídeo — é exatamente o tipo de informação que o texto da glosa
  não carrega hoje, mas que faz a diferença entre um sinal "readable" e um
  natural.

## Arquivos

- `config.yaml` — modelo, geração (thinking on, max_new_tokens alto), capítulo/páginas, caminhos de I/O.
- `schema.py` — `ExtractedRule`/`ExtractedRuleSet` (pydantic) e `RuleMatch`/`RuleMatchSet`.
- `pdf_text.py` — extrai texto de um range de páginas do PDF, marcando `[p.N]`.
- `parsing.py` — remove bloco `<think>` e extrai o JSON da resposta.
- `llm.py` — client próprio (mesmo qwen3-32B do main_pipeline, config de geração diferente).
- `prompts/extract_rules.yaml`, `prompts/validate_rule.yaml` — os dois prompts.
- `extract.py`, `validate.py` — os dois scripts CLI.
- `output/` — `chapter02_rules.json`, `chapter02_validation.csv` (gerados, não versionar em `.gitignore` até decidir).

## Rodando (dentro do container, GPU do projeto — ver docker-compose.yml)

```bash
docker compose exec judge bash -lc '
  PYTHONPATH=src python extract_rules/extract.py'

docker compose exec judge bash -lc '
  PYTHONPATH=src python extract_rules/validate.py'
```

## Depois — virar skill?

Dá, sim, mas só depois de provar que a esteira funciona neste 1 capítulo
piloto. Uma vez validado, empacotar como skill (apontar PDF + range de
página, sair regras já classificadas) é um passo de generalização direto —
não vale a pena adiantar isso antes de ver se a extração/validação em si
produz sinal útil.
