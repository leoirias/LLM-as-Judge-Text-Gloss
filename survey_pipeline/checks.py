"""Camada de verificação DETERMINÍSTICA (etapa Verify do survey).

As regras aqui são checadas por código (regex/lista) — sem LLM. Cada check foi
validado contra as 180 glosas aceitas do ouro (data/pares_review.csv, coluna
gloss_review):

  - DURA  (hard): 0 violação no ouro -> se violar, é erro com certeza.
  - AVISO (soft): tem exceção real no ouro -> sinaliza suspeita, NÃO reprova.
  - INFO  (info): não é erro em nenhum sentido; só marca uma pista (ex.: pronome
                  presente pode indicar marcação não-manual — ver SPECIFY.md).

Pronome/possessivo NÃO reprovam (decisão da consultoria, SPECIFY.md): presença é
aceitável, então entram apenas como INFO.

Rodar a autovalidação (sem GPU):
    python survey_pipeline/checks.py --self-test
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path

HARD, SOFT, INFO = "dura", "aviso", "info"

ARTICLES = {"THE", "A", "AN"}
COPULA = {"IS", "ARE", "AM", "WAS", "WERE", "BE", "BEEN", "BEING"}
PERFECT_AUX = {"HAS", "HAD"}          # HAVE fica: pode ser conteúdo/posse
PRONOUNS = {"I", "YOU", "HE", "SHE", "WE", "THEY", "US", "THEM"}
POSSESSIVES = {"MY", "YOUR", "OUR", "THEIR"}
TIME_MARKERS = {"NOW", "TODAY", "TONIGHT", "TOMORROW", "YESTERDAY", "THIS_MORNING"}
COMPOUND_UNDERSCORE = {
    "HOW_MUCH", "NO_PROBLEM", "NOT_UNDERSTAND", "PANIC_ATTACK",
    "PASS_OUT", "THANK_YOU", "THIS_MORNING", "WRITE_DOWN",
}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str          # HARD | SOFT | INFO
    message: str
    tokens: tuple[str, ...] = ()


def _toks(gloss: str) -> list[str]:
    s = (gloss or "").replace("?", " ").replace(",", " ").replace(".", " ")
    return [t for t in s.split() if t]


def run_checks(text: str, gloss: str) -> list[Finding]:
    """Todos os achados determinísticos para um par (text, gloss)."""
    g = gloss or ""
    tk = _toks(g)
    tkset = set(tk)
    out: list[Finding] = []

    # ---- DURA (0 violação no ouro) ----
    if g.strip() and g.strip() != g.strip().upper():
        out.append(Finding("R1", HARD, "glosa deve estar toda em MAIÚSCULAS"))
    if ART := (tkset & ARTICLES):
        out.append(Finding("R2", HARD, "artigo deve ser removido", tuple(sorted(ART))))
    if COP := (tkset & COPULA):
        out.append(Finding("R4", HARD, "cópula 'be' deve ser removida", tuple(sorted(COP))))
    if AUX := (tkset & PERFECT_AUX):
        out.append(Finding("R6", HARD, "auxiliar has/had deve ser removido", tuple(sorted(AUX))))
    bad_us = [t for t in tk if "_" in t and t not in COMPOUND_UNDERSCORE]
    if bad_us:
        out.append(Finding("R11", HARD, "underscore só na lista fechada de compostos", tuple(bad_us)))
    if re.search(r"[A-Za-z]-[A-Za-z]", g):
        out.append(Finding("R11b", HARD, "hífen entre sinais: use dois sinais separados"))
    if re.search(r"\b(DESC|X|G)-", g):
        out.append(Finding("E2", HARD, "prefixo indevido (DESC-/X-/G-)"))

    # ---- AVISO (tem exceção legítima no ouro) ----
    if DO := (tkset & {"DO", "DOES", "DID"}):
        out.append(Finding("R5", SOFT, "do/does/did costuma cair (exceto DO verbo de conteúdo)", tuple(sorted(DO))))
    if tk and tk[0] not in TIME_MARKERS and (tkset & TIME_MARKERS):
        out.append(Finding("REORD.R1", SOFT, "marcador de tempo costuma ir para o início", tuple(sorted(tkset & TIME_MARKERS))))
    if ("?" in (text or "")) != ("?" in g):
        out.append(Finding("REORD.R6", SOFT, "pontuação (?/.) costuma seguir o inglês"))

    # ---- INFO (não é erro; pista) ----
    if PRO := (tkset & PRONOUNS):
        out.append(Finding("R7", INFO, "pronome presente: aceitável; possível flag de marcação não-manual", tuple(sorted(PRO))))
    if POS := (tkset & POSSESSIVES):
        out.append(Finding("R8", INFO, "possessivo presente: aceitável", tuple(sorted(POS))))

    return out


def hard_failures(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == HARD]


# --------------------------------------------------------------------------- #
# Autovalidação: nenhuma regra DURA pode disparar numa glosa aceita do ouro.
# --------------------------------------------------------------------------- #
def _self_test(review_csv: Path) -> int:
    rows = []
    with review_csv.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            text = (r.get("Input") or r.get("text") or "").strip()
            gold = (r.get("Output review") or r.get("gloss_review") or "").strip()
            if gold:
                rows.append((text, gold))

    from collections import Counter
    hard_hits: Counter[str] = Counter()
    soft_hits: Counter[str] = Counter()
    examples: dict[str, tuple[str, str]] = {}
    for text, gold in rows:
        for f in run_checks(text, gold):
            if f.severity == HARD:
                hard_hits[f.rule_id] += 1
                examples.setdefault("HARD:" + f.rule_id, (text, gold))
            elif f.severity == SOFT:
                soft_hits[f.rule_id] += 1

    print(f"autovalidação em {len(rows)} glosas aceitas do ouro\n")
    print("DURAS que dispararam no ouro (deveria ser 0):")
    if not hard_hits:
        print("  nenhuma ✅  (todas as regras duras são seguras)")
    else:
        for rid, n in hard_hits.most_common():
            t, g = examples["HARD:" + rid]
            print(f"  ❌ {rid}: {n}   ex.: {t!r} -> {g!r}")
    print("\nAVISOS que dispararam (esperado ter alguns; são exceções):")
    for rid, n in soft_hits.most_common():
        print(f"  ⚠️  {rid}: {n}")
    return 1 if hard_hits else 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--review", type=Path, default=Path("data/pares_review.csv"))
    args = p.parse_args()
    if args.self_test:
        raise SystemExit(_self_test(args.review))
    print("use --self-test para validar os checks contra o ouro")


if __name__ == "__main__":
    main()
