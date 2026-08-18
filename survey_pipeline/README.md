# survey_pipeline — validação de glosa ASL na arquitetura do survey

Pipeline de validação texto→glosa montado seguindo a arquitetura de referência do
survey *"Grammar-Based Sentence Validation in the LLM Era"* (§14, Fig. 4, Tab. 5).
Pasta separada de propósito, para organizar as diferentes tentativas.

Tese central do survey que estamos seguindo: **as regras fazem os checks duros de
validade; o LLM só entra no resíduo** (o que não dá para decidir por regra fixa).
Nunca converter incerteza/falta de cobertura em garantia formal; toda decisão
carrega proveniência.

## As 7 etapas (→ arquivos)

```
Specify → Acquire → Formalize → Verify → Interpret → Explain → Evaluate
```

| Etapa | Arquivo | O que faz | Status |
|-------|---------|-----------|--------|
| **Specify** | `SPECIFY.md` | declara construto, domínio, população, alvo do pronome/WILL, política de abstenção | ✅ |
| **Acquire+Formalize** | `rules/rule_package.yaml` | pacote de regras **versionado**: cada regra com fonte, tipo de verificação (dura/aviso/llm/nenhuma), exemplos, contraexemplos, conflitos, cobertura | ⏳ |
| **Verify (determinístico)** | `checks.py` | checks por código (regex/lista) — só o que dá 0 falso-positivo no ouro | ✅ |
| **Verify (resíduo LLM)** | `judge.py` + `prompts/` | qwen3-32B só no que exige julgamento (ordem, sinal conceitual, FEEL/HAVE, WILL) | ⏳ |
| **Interpret (cobertura)** | `coverage.py` | mapeia para `suportado / não-suportado / ambíguo`; nunca trata falta de cobertura como agramaticalidade | ⏳ |
| **Explain** | (embutido) | devolve a regra citada / violada, não só Sim/Não | ⏳ |
| **Evaluate** | `evaluate.py` | métricas SEPARADAS (conformidade formal, cobertura, acurácia vs ouro, localização de erro, parse, eficiência) | ⏳ |
| Orquestrador | `run.py` | determinístico → resíduo LLM → veredito de 3 estados + proveniência | ⏳ |

## Espaço de decisão (§14, Fig. 4)

Três estados, não dois: **`valido` · `invalido` · `nao_coberto`** (abstenção).
`nao_coberto` = nenhuma regra do pacote cobre o fenômeno → não é reprovação.

## Divisão determinístico × LLM (validada empiricamente em 180 glosas do ouro)

- **Dura (0 violação no ouro):** R1 maiúsculas, R2 artigos, R4 cópula, R6 has/had,
  R11 underscore fora da lista, R11b hífen entre sinais, E2 prefixo indevido.
- **Aviso (tem exceção real no ouro → sinaliza, não reprova):** R5 do/does/did,
  REORD.R1 tempo no início, REORD.R6 pontuação.
- **Pronome/possessivo (R7/R8):** NÃO é check — presença é aceitável (ver SPECIFY).
- **Resíduo LLM:** R3 preposição, R9 singular, R10 verbo-base, R3 inserir FEEL/HAVE,
  R3b WILL futuro, R4 FINISH, R5 sinal conceitual, R2 posição do WH, E1/E3.

## Rodar

Escolha a GPU livre no comando (`CUDA_VISIBLE_DEVICES=N`).

```bash
# P3 — teste de 1 par (barato, valida o formato antes da rodada cheia)
docker compose exec -e CUDA_VISIBLE_DEVICES=4 judge bash -lc \
  'PYTHONPATH=src uv run python survey_pipeline/run.py --limit 1 --exp-name smoke'

# P5 — rodada cheia (180 pares)
docker compose exec -e CUDA_VISIBLE_DEVICES=4 judge bash -lc \
  'PYTHONPATH=src uv run python survey_pipeline/run.py --exp-name asl_v1'

# P6 — métricas (sem GPU)
docker compose exec judge bash -lc \
  'PYTHONPATH=src uv run python survey_pipeline/evaluate.py \
     --run survey_pipeline/experiments/asl_v1/resultado.csv'
```

Saída de cada rodada em `experiments/<nome>/`: `resultado.csv`
(Texto · Glosa · Estado · Fidelidade · Naturalidade · Regras · Problema ·
Sugestao · Glosa Review · Origem) + `meta.json`.

Regenerar o pacote de regras (sem GPU): `python survey_pipeline/build_rule_package.py`.

### Estado atual (v1.0)
- Pacote = só `asl_rules` (21 regras; 12 Voice2Sign usadas pelo validador).
- Camada determinística **vazia** (asl_rules não tem regra de superfície) → hoje é
  essencialmente LLM-juiz + abstenção. Quando entrarem regras de convenção com
  check por código, a camada determinística liga sozinha (`enforcement: dura/aviso`).
