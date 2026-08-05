# framework_rules — juiz de glosa ASL guiado por regras

Juiz que valida uma glosa ASL contra uma **base de regras gramaticais**
(entregue pela consultoria) e responde, para cada par texto→glosa:

- **Correto?** Sim ou Não
- **Regras** em que se baseou (IDs citados da base, ex.: `PRON.2.5`)
- **Sugestão** da glosa correta, quando a glosa está errada

A base de regras é um arquivo YAML que **cresce com o tempo**: novas entregas da
consultoria viram novas entradas, sem tocar em código.

## Fluxo

```
rules/asl_rules.yaml   (base de regras, extensível)
        │  rules_store.py -> texto injetável
        ▼
data/pares_review.csv  (Input=texto, Output=glosa, Output review=validação manual)
        │  run.py monta o prompt (prompts/judge_rules.yaml) por linha
        ▼
   qwen3-32B  (thinking ON, temperatura 0.5)   [llm.py + config.yaml]
        │  parsing.py: remove <think>, extrai o JSON, valida
        ▼
framework_rules/experiments/<data>_<nome>/
    config.yaml         snapshot dos parâmetros
    teste_inicial.csv   Texto | Glosa | Correto? | Regras | Sugestao | Glosa Review
    meta.json           timestamp, modelo, contagem Sim/Não, parse_failed, versão das regras
    raw.jsonl           respostas cruas (debug / reprocesso sem re-rodar o modelo)
```

## Arquivos

- `rules/asl_rules.yaml` — base de regras. Campos: `id`, `categoria`, `titulo`,
  `descricao`, `verificavel_por_texto`, `exemplos`. Regras com
  `verificavel_por_texto: false` (espaciais/não-manuais) são passadas ao juiz só
  como contexto — ele é instruído a **não reprovar** uma glosa por elas.
- `rules_store.py` — carrega a base e renderiza o bloco injetável no prompt.
- `prompts/judge_rules.yaml` — prompt do juiz (fragmentos `@{...}`, variáveis
  `{{text}}`, `{{gloss}}`, `{{rules}}`).
- `prompt.py` — monta o prompt (reusa o renderizador de `src/judge/prompt.py`).
- `schema.py` / `parsing.py` — decisão do juiz e parse do JSON (com remoção do
  bloco `<think>` do Qwen3).
- `config.yaml` / `llm.py` — modelo qwen3-32B, thinking on, temperatura 0.5.
- `run.py` — CLI.

## Rodar (dentro do container, GPU do projeto)

```bash
docker compose exec judge bash -lc '
  PYTHONPATH=src uv run python framework_rules/run.py'
```

Opções:

- `--exp-name NOME` — nomeia a pasta do experimento (default: `<data>_thinking-on`).
- `--limit N` — processa só as N primeiras linhas (útil para um teste rápido).
- `--input CAMINHO` — outro CSV de entrada (default: `data/pares_review.csv`).

Teste rápido em poucas linhas antes da rodada cheia:

```bash
docker compose exec judge bash -lc '
  PYTHONPATH=src uv run python framework_rules/run.py --limit 5 --exp-name smoke'
```

## Adicionar regras

Acrescente entradas em `rules/asl_rules.yaml` mantendo os IDs existentes
estáveis (o juiz os cita). Nada mais precisa mudar.
