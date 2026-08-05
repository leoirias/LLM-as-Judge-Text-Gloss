"""Parse da resposta do juiz: remove <think>, extrai o JSON e é TOLERANTE ao
esquema (o modelo costuma inventar nomes de campo). Deriva o veredito das duas
dimensões (fidelidade + naturalidade) quando o campo `veredito` não vem.
"""

from __future__ import annotations

import json
import re
import unicodedata
from json import JSONDecodeError
from typing import Any

from schema import ESTADOS, JudgeVerdict, VerdictError

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class JudgeParseError(ValueError):
    pass


def strip_thinking(reply: str) -> str:
    text = _THINK.sub("", reply or "")
    if "<think>" in text:  # aberto sem fechar (estourou tokens)
        text = text.split("</think>")[-1] if "</think>" in text else ""
    return text.strip()


def _extract_json(text: str) -> Any:
    text = text.replace("```json", "```").strip()
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            val, _ = dec.raw_decode(text[i:])
            return val
        except JSONDecodeError:
            continue
    raise JudgeParseError(f"nenhum JSON encontrado: {text[:200]!r}")


def _deaccent(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


# ---- veredito (valido/invalido/nao_coberto) ---- #
_ESTADO_SINONIMOS = {
    "valido": "valido", "correto": "valido", "certo": "valido", "ok": "valido",
    "invalido": "invalido", "incorreto": "invalido", "errado": "invalido", "nao_correto": "invalido",
    "nao_coberto": "nao_coberto", "naocoberto": "nao_coberto",
    "nao_sei": "nao_coberto", "indefinido": "nao_coberto", "abstencao": "nao_coberto",
}


def _norm_estado(v: Any) -> str:
    s = re.sub(r"[\s-]+", "_", _deaccent(v)).strip("_")
    if s in ESTADOS:
        return s
    return _ESTADO_SINONIMOS.get(s, "")


# ---- Sim/Não (tolerante: aceita dict aninhado e "não_correto" etc.) ---- #
def _sim_nao(v: Any) -> str:
    if isinstance(v, dict):
        for k in ("veredito", "valor", "resposta", "status"):
            if k in v:
                return _sim_nao(v[k])
        for vv in v.values():
            if isinstance(vv, str) and (r := _sim_nao(vv)):
                return r
        return ""
    s = _deaccent(v)
    if s.startswith(("nao", "incorret", "invalid", "errad", "false")):
        return "Não"
    if s.startswith(("sim", "correto", "valid", "ok", "true")):
        return "Sim"
    return ""


def _get(data: dict, keys: list[str]) -> Any:
    for k in keys:
        if k in data and data[k] not in (None, ""):
            return data[k]
    return None


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [x.strip() for x in re.split(r"[;,]", v) if x.strip()]
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [str(v).strip()]


def parse_verdict(raw: str) -> JudgeVerdict:
    data = _extract_json(strip_thinking(raw))
    if not isinstance(data, dict):
        raise JudgeParseError("JSON deve ser um objeto.")

    representa = _sim_nao(_get(data, ["representa_sentido", "fidelidade", "fidelidade_sentido"]))
    natural = _sim_nao(_get(data, ["natural_estrutura", "naturalidade_estrutura", "naturalidade", "estrutura"]))

    vr = _get(data, ["veredito", "resultado", "decisao"])
    veredito = _norm_estado(vr) if vr is not None else ""
    if veredito not in ESTADOS:
        # deriva das duas dimensões: qualquer "Não" -> inválido; ambas "Sim" -> válido
        dims = [d for d in (representa, natural) if d in ("Sim", "Não")]
        if "Não" in dims:
            veredito = "invalido"
        elif dims:
            veredito = "valido"
        else:
            raise JudgeParseError(f"sem veredito nem dimensões reconhecíveis em {list(data)}")

    problema = _get(data, ["problema", "motivo", "motivo_fidelidade", "justificativa", "observacao"]) or ""
    sugestao = _get(data, ["sugestao", "sugestão", "correcao", "glosa_correta", "glosa_corrigida"]) or ""
    if veredito == "valido":
        sugestao = ""
    regras = _as_list(_get(data, ["regras", "regras_aplicadas", "producoes"]))

    try:
        return JudgeVerdict(
            veredito=veredito,
            representa_sentido=representa,
            natural_estrutura=natural,
            regras=regras,
            problema=str(problema).strip(),
            sugestao=str(sugestao).strip(),
        )
    except VerdictError as exc:
        raise JudgeParseError(str(exc)) from exc
