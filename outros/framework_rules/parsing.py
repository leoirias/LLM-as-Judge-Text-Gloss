"""Parse da resposta do juiz: remove o bloco <think> do Qwen3, extrai o JSON e
valida contra o schema. Normaliza variações comuns de "Sim"/"Não".
"""

from __future__ import annotations

import json
import re
from json import JSONDecodeError
from typing import Any

from schema import JudgeDecision, JudgeSchemaError

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class JudgeParseError(ValueError):
    pass


def strip_thinking(reply: str) -> str:
    text = _THINK_BLOCK.sub("", reply or "")  # remove blocos <think>...</think> completos
    if "<think>" in text:
        # <think> aberto e não fechado: o modelo estourou max_new_tokens ainda
        # raciocinando. Não há JSON final — descarta tudo (vira falha de parse)
        # a não ser que haja um </think> avulso, caso em que fica o que vem depois.
        text = text.split("</think>")[-1] if "</think>" in text else ""
    return text.strip()


def _extract_json_object(text: str) -> Any:
    decoder = json.JSONDecoder()
    text = text.replace("```json", "```").strip()
    for start in range(len(text)):
        if text[start] != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[start:])
            return value
        except JSONDecodeError:
            continue
    raise JudgeParseError(f"Nenhum objeto JSON encontrado na resposta: {text[:200]!r}")


def _normalize_correto(value: Any) -> str:
    s = str(value).strip().lower()
    if s in {"sim", "yes", "true", "correto", "s"}:
        return "Sim"
    if s in {"não", "nao", "no", "false", "incorreto", "n"}:
        return "Não"
    raise JudgeParseError(f"Valor inesperado para 'correto': {value!r}")


def parse_judge_response(raw_response: str) -> JudgeDecision:
    data = _extract_json_object(strip_thinking(raw_response))
    if not isinstance(data, dict):
        raise JudgeParseError("O JSON da resposta deve ser um objeto.")

    correto = _normalize_correto(data.get("correto"))

    regras_raw = data.get("regras") or []
    if isinstance(regras_raw, str):
        regras = [r.strip() for r in re.split(r"[,;]", regras_raw) if r.strip()]
    else:
        regras = [str(r).strip() for r in regras_raw if str(r).strip()]

    sugestao = str(data.get("sugestao") or "").strip()
    if correto == "Sim":
        sugestao = ""

    try:
        return JudgeDecision(correto=correto, regras=regras, sugestao=sugestao)
    except JudgeSchemaError as exc:
        raise JudgeParseError(str(exc)) from exc
