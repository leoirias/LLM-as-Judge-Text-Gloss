"""Pré-voo do Qwen3.8-27B antes de rodar as pipelines de verdade.

Checa, na ordem, o que pode dar errado silenciosamente:
  1. o modelo carrega pelo cliente do projeto (AutoModelForCausalLM sobre um
     checkpoint cujo `architectures` é ...ForConditionalGeneration — carrega só
     a torre de texto, que é o que usamos);
  2. NENHUM peso foi inicializado aleatoriamente (o risco real de carregar um
     multimodal como CausalLM: se as chaves não casarem, transformers avisa e
     segue com pesos random — geraria texto plausível e ERRADO);
  3. thinking está de fato desligado (sem <think> na saída);
  4. o prompt real do juiz volta um JSON parseável;
  5. quanto de VRAM sobrou pro KV-cache.

Rodar (dentro do container):
    docker compose exec -e CUDA_VISIBLE_DEVICES=<N> judge bash -lc \
      'PYTHONPATH=src uv run python libras_pipeline/evaluation/smoke_qwen38.py'
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import torch  # noqa: E402

# captura os avisos de carregamento do transformers (é onde aparece
# "newly initialized" quando o state dict não casa com a arquitetura)
_records: list[logging.LogRecord] = []


class _Capture(logging.Handler):
    def emit(self, record):
        _records.append(record)


logging.getLogger("transformers").addHandler(_Capture())
logging.getLogger("transformers").setLevel(logging.WARNING)

from llm import get_llm  # noqa: E402
from parsing import JudgeParseError, parse_verdict  # noqa: E402
from prompt import load_prompt_config, render  # noqa: E402
from rules_store import load_rules_text, valid_rule_ids  # noqa: E402

FALHAS: list[str] = []


def check(nome: str, ok: bool, detalhe: str = "") -> None:
    print(f"  [{'OK ' if ok else 'FALHA'}] {nome}" + (f" — {detalhe}" if detalhe else ""))
    if not ok:
        FALHAS.append(nome)


print("=" * 72)
print("1. carregando o modelo pelo cliente do projeto")
print("=" * 72)
llm = get_llm()
print(f"  model_id: {llm.config.model_id}")
print(f"  classe carregada: {type(llm.model).__name__}")
print(f"  dtype: {next(llm.model.parameters()).dtype}")

print()
print("=" * 72)
print("2. algum peso inicializado aleatoriamente? (crítico)")
print("=" * 72)
suspeitos = [r.getMessage() for r in _records
             if "newly initialized" in r.getMessage() or "randomly initialized" in r.getMessage()]
check("nenhum peso random", not suspeitos,
      "limpo" if not suspeitos else f"{len(suspeitos)} aviso(s): {suspeitos[0][:200]}")
nao_usados = [r.getMessage() for r in _records if "were not used" in r.getMessage()]
if nao_usados:
    print(f"  (nota: {len(nao_usados)} aviso de pesos não usados — esperado, são os do "
          f"encoder de visão que não carregamos)")

print()
print("=" * 72)
print("3. thinking desligado?")
print("=" * 72)
saida = llm.generate("Responda apenas com este JSON, nada mais: {\"teste\": \"ok\"}")
print(f"  saída crua: {saida[:160]!r}")
check("sem bloco <think>", "<think>" not in saida)

print()
print("=" * 72)
print("4. prompt real do juiz devolve JSON parseável?")
print("=" * 72)
prompt = render(load_prompt_config(HERE / "prompts" / "judge.yaml"), {
    "regras": load_rules_text(),
    "text": "Posso ir para casa hoje?",
    "gloss": "EU PODER IR PARA CASA HOJE",
})
print(f"  tamanho do prompt: {len(prompt)} chars (~{len(prompt)//3.5:.0f} tokens)")
raw = llm.generate(prompt)
print(f"  saída crua: {raw[:300]!r}")
try:
    v = parse_verdict(raw)
    check("parse do veredito", True, f"estado={v.veredito}, regras={v.regras}")
    ids = valid_rule_ids()
    inventadas = [r for r in v.regras if r not in ids]
    check("regras citadas existem na base", not inventadas,
          "todas válidas" if not inventadas else f"inventadas: {inventadas}")
except JudgeParseError as exc:
    check("parse do veredito", False, str(exc))

print()
print("=" * 72)
print("5. VRAM")
print("=" * 72)
if torch.cuda.is_available():
    usado = torch.cuda.memory_allocated() / 1e9
    total = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"  pesos ocupam {usado:.1f} GB de {total:.1f} GB "
          f"({total - usado:.1f} GB livres pro KV-cache)")
    check("sobra VRAM pro KV-cache", (total - usado) > 8, f"{total - usado:.1f} GB")

print()
print("=" * 72)
if FALHAS:
    print(f"RESULTADO: {len(FALHAS)} FALHA(S) -> {', '.join(FALHAS)}")
    print("NÃO rodar as pipelines antes de resolver.")
    sys.exit(1)
print("RESULTADO: tudo OK — liberado para rodar as pipelines.")
