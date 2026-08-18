# extraction — extrair regras de livros → CSV normalizado + comparar com a base

Duas etapas, cada uma uma chamada de LLM por unidade (qwen3-32B, thinking on,
**determinístico** para reprodutibilidade):

```
ASL_for_dummies.pdf (capítulo 2)
        │  extract.py   [1 chamada LLM, JSON validado por schema]
        ▼
output/asl_for_dummies_cap02_regras.csv
   id · categoria · titulo · descricao · verificavel_por_texto ·
   gatilho · exemplos · fonte_pagina · fonte_citacao
        │  compare.py   [1 chamada LLM POR REGRA, semântica]
        │  recebe cada regra + TODA a base (rules/asl_rules.yaml)
        ▼
output/asl_for_dummies_cap02_comparacao.csv
   (colunas acima) + status · regra_base_correspondente · justificativa
```

## O que é extraído

Só regras relevantes para **entender e representar a estrutura da ASL** —
ordem dos sinais, morfologia, pronomes, verbos, perguntas, negação,
tempo/aspecto, tópico-comentário. **Ignora** vocabulário, datilologia, notas
culturais e dicas de aprendizado.

Campos espelham a base da consultoria (`rules/asl_rules.yaml`) + `gatilho`
(a condição que ATIVA a regra, separada do "o que fazer" da `descricao`) +
procedência (`fonte_pagina`, `fonte_citacao`). Sem campo de confiança.

## Status da comparação (regra a regra, semântico)

| status | significado | ação da consultoria |
|--------|-------------|---------------------|
| `ja_temos`  | a base já cobre o fenômeno e concorda | nada |
| `nao_temos` | fenômeno não coberto | candidata a **adicionar** |
| `conflito`  | mesmo fenômeno, base diz diferente | **resolver** |
| `parcial`   | base cobre em parte, regra acrescenta nuance | avaliar |

## Rodar (dentro do container, GPU do projeto)

Piloto (capítulo 2):
```bash
docker compose exec judge bash -lc 'PYTHONPATH=src uv run python framework_rules/extraction/extract.py'
docker compose exec judge bash -lc 'PYTHONPATH=src uv run python framework_rules/extraction/compare.py'
```

Livro inteiro (fatiado em janelas — demorado, deixe rodando):
```bash
docker compose exec judge bash -lc 'PYTHONPATH=src uv run python framework_rules/extraction/extract.py --full'
docker compose exec judge bash -lc 'PYTHONPATH=src uv run python framework_rules/extraction/compare.py --full'
```

Regras induzidas dos pares-ouro (o que a convenção segue na prática) e comparação:
```bash
docker compose exec judge bash -lc 'PYTHONPATH=src uv run python framework_rules/extraction/extract_pairs.py'
docker compose exec judge bash -lc 'PYTHONPATH=src uv run python framework_rules/extraction/compare.py --pairs'
```

Opções úteis:

- `extract.py --start-page N --end-page M` — outra faixa (0-indexada, índice pypdf).
- `extract.py --full` — livro inteiro (janelas de `window_pages`, config).
- `extract*.py --from-raw` — reconstrói o CSV do `*.raw.txt` salvo, **sem GPU**.
- `compare.py [--full|--pairs]` — escolhe o CSV de entrada/saída pela config;
  ou `--rules CSV --out CSV --base asl_rules.yaml` para caminhos manuais.

Todo `extract*.py` sempre salva a resposta crua em `*.raw.txt` ao lado do CSV,
para depuração / reconstrução com `--from-raw`.

## Arquivos

- `config.yaml` — modelo, geração (thinking on, determinístico), livro/páginas,
  caminhos de I/O, base de comparação.
- `pdf_text.py` — extrai texto de uma faixa de páginas, marcando `[p.N]`.
- `prompts/extract_rules.yaml`, `prompts/compare_rule.yaml` — os dois prompts.
- `schema.py` — `ExtractedRule`/`ExtractedRuleSet` e `CompareResult` (pydantic).
- `parsing.py` — remove `<think>` e extrai o JSON.
- `prompt.py` — carrega/renderiza os prompts (reusa o renderizador do repo).
- `llm.py` — client qwen3-32B (config própria).
- `extract.py`, `compare.py` — os dois CLIs.
- `output/` — CSVs gerados.
