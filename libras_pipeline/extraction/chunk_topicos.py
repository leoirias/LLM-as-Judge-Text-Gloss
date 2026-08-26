"""Fatia uma fonte do config em TRECHOS por tópico e grava tudo em disco.

Um TRECHO é o que vai numa única chamada de LLM na etapa 1. Definição:

  1. FRONTEIRA — página que inicia um tópico. União de duas fontes:
       a) outline do PDF (bookmarks), percorrido em TODOS os níveis;
       b) título detectado no texto, para onde o outline é raso.
     Detector (b) aceita dois padrões: numerado ("5.4.3.2 Título") e linha em
     MAIÚSCULAS contendo palavra funcional (A, DE, COM...). A palavra funcional
     é o que separa título de GLOSA: glosa não realiza artigo nem preposição,
     então "A ORDEM BÁSICA DA FRASE" é título e "IX GOSTA FUTEBOL" não é.

  2. TÓPICO — da fronteira até a página anterior à fronteira seguinte.

  3. TRECHO — tópicos consecutivos agrupados até `--budget` tokens. Tópico
     maior que o orçamento é partido por página, e cada parte repete o
     cabeçalho do tópico (marcada "parte i de n") para não perder contexto.

Saída em <out>/<slug>/:
    manifest.csv          índice ordenado — o sumário oficial do capítulo
    NNN_<titulo>.txt      o texto exato que seria enviado ao modelo

Uso:
    python libras_pipeline/extraction/chunk_topicos.py --book gramatica [--budget 2000]
"""
from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from pathlib import Path

import yaml
from pypdf import PdfReader

AQUI = Path(__file__).resolve().parent

FUNCIONAIS = {"A", "O", "OS", "AS", "DE", "DA", "DO", "DAS", "DOS",
              "COM", "E", "NA", "NO", "EM", "UM", "UMA", "PARA", "POR"}
RUIDO = re.compile(r"[*<>?()\[\]]|\d")
NUMERADO = re.compile(r"^\s*(\d+(?:\.\d+)+\.?|\d+\.)\s+([A-ZÀ-Úa-zà-ú]\S*.{2,70})$")
# Âncora interna de PDF gerado por editor ("_7jjy9o4k5753"): posição arbitrária,
# não início de tópico. 83% do outline da Gramática é disso — descartar.
ANCORA_LIXO = re.compile(r"^_[a-z0-9]{4,}$", re.I)


def conta_tokens(model_id: str):
    """Tokenizer do próprio modelo; cai para aproximação se não houver cache."""
    try:
        from transformers import AutoTokenizer
        tk = AutoTokenizer.from_pretrained(model_id, local_files_only=True)
        return (lambda s: len(tk(s).input_ids)), f"tokenizer {model_id}"
    except Exception:
        return (lambda s: int(len(s) / 3.5)), "aproximação chars/3.5"


def limpa_titulo(s: str) -> str:
    """Colapsa qualquer espaço em branco — inclusive quebra de linha — num
    espaço só. Título de bookmark de PDF pode vir quebrado no meio, e isso
    partia o cabeçalho `=== TÓPICO: ... ===` em duas linhas e metia uma
    quebra dentro do campo do manifesto."""
    return " ".join(str(s).split())[:80]


def outline_rec(no, rd, prof=0, saida=None):
    """Percorre o outline em todos os níveis (o aninhamento pode ser profundo)."""
    saida = [] if saida is None else saida
    for it in no:
        if isinstance(it, list):
            outline_rec(it, rd, prof + 1, saida)
        else:
            try:
                saida.append((rd.get_destination_page_number(it), prof, limpa_titulo(it.title)))
            except Exception:
                pass
    return saida


def detecta_modo(textos, prefixo):
    """Descobre COMO este documento marca seção, em vez de assumir.

    Conta páginas com título numerado. Se o documento usa numeração, ela é o
    sinal confiável e o modo 'prosa' fica desligado — é o que evita capturar
    item de lista ("1. Sinais monomorfêmicos...") e cabeçalho de tabela
    ("GLOSA E SIGNIFICADO") como se fossem seção.
    """
    n = sum(1 for txt in textos.values() if _numerado(txt, prefixo))
    return ("numerado", n) if n >= 5 else ("prosa", n)


def _numerado(txt, prefixo):
    for linha in [x.strip() for x in txt.splitlines() if x.strip()][:12]:
        m = NUMERADO.match(linha)
        if m and (prefixo is None or m.group(1).startswith(str(prefixo))):
            return limpa_titulo(f"{m.group(1)} {m.group(2)}")
    return None


def _prosa(txt):
    """Linha em MAIÚSCULAS que seja prosa, não glosa.

    Glosa não realiza artigo nem preposição; prosa realiza. Exigir palavra
    funcional separa 'A ORDEM BÁSICA DA FRASE' (título) de 'IX GOSTA FUTEBOL'.
    """
    for linha in [x.strip() for x in txt.splitlines() if x.strip()][:40]:
        if RUIDO.search(linha):
            continue
        limpa = re.sub(r"[^A-ZÀ-Úa-zà-ú ]", "", linha).strip()
        if limpa.isupper() and 6 < len(linha) < 60:
            palavras = set(limpa.split())
            if len(palavras) >= 2 and (FUNCIONAIS & palavras):
                return limpa_titulo(linha)
    return None


def titulo_no_texto(txt, modo, prefixo):
    return _numerado(txt, prefixo) if modo == "numerado" else _prosa(txt)


def fronteiras(rd, ini, fim, textos, prefixo):
    modo, n_num = detecta_modo(textos, prefixo)
    fr, niveis = {}, {}
    try:
        for pag, prof, tit in outline_rec(rd.outline, rd):
            if ini <= pag <= fim and pag not in fr and not ANCORA_LIXO.match(tit):
                if modo == "numerado" and prefixo is not None and not tit.startswith(str(prefixo)):
                    continue
                fr[pag], niveis[pag] = tit, prof
    except Exception:
        pass
    n_outline = len(fr)
    for pag in range(ini, fim + 1):
        if pag not in fr:
            tit = titulo_no_texto(textos[pag], modo, prefixo)
            if tit:
                fr[pag], niveis[pag] = tit, -1
    if ini not in fr:
        fr[ini], niveis[ini] = "(início da faixa)", -1
    return dict(sorted(fr.items())), niveis, n_outline, len(fr) - n_outline, modo


def monta_trechos(rd, ini, fim, orcamento, ntok, prefixo=None):
    textos = {p: (rd.pages[p].extract_text() or "") for p in range(ini, fim + 1)}
    tam = {p: ntok(textos[p]) for p in textos}
    fr, niveis, n_out, n_txt, modo = fronteiras(rd, ini, fim, textos, prefixo)

    pgs = sorted(fr)
    topicos = [(a, (pgs[i + 1] - 1 if i + 1 < len(pgs) else fim), fr[a], niveis[a])
               for i, a in enumerate(pgs)]

    trechos, buf = [], []

    def fecha():
        if buf:
            paginas = [p for a, b, _, _ in buf for p in range(a, b + 1)]
            trechos.append({
                "ini": buf[0][0], "fim": buf[-1][1],
                "topico": buf[0][2], "nivel": buf[0][3],
                # Todos os títulos agrupados aqui. O `topico` sozinho é o do
                # primeiro; a triagem precisa dos outros, senão julga um tópico
                # por um título que não é o dele.
                "topicos": [x[2] for x in buf],
                "n_topicos": len(buf), "parte": "", "tokens": sum(tam[p] for p in paginas),
            })
            buf.clear()

    for a, b, tit, niv in topicos:
        total = sum(tam[p] for p in range(a, b + 1))
        if total > orcamento:                      # tópico grande: parte por página
            fecha()
            partes, cur, acc = [], a, 0
            for p in range(a, b + 1):
                if acc and acc + tam[p] > orcamento:
                    partes.append((cur, p - 1, acc)); cur, acc = p, 0
                acc += tam[p]
            partes.append((cur, b, acc))
            for i, (x, y, t) in enumerate(partes, 1):
                trechos.append({"ini": x, "fim": y, "topico": tit, "nivel": niv,
                                "topicos": [tit], "n_topicos": 1,
                                "parte": f"{i}/{len(partes)}", "tokens": t})
        else:
            atual = sum(tam[p] for x, y, _, _ in buf for p in range(x, y + 1))
            if buf and atual + total > orcamento:
                fecha()
            buf.append((a, b, tit, niv))
    fecha()
    return topicos, trechos, textos, (n_out, n_txt, modo)


def triagem(topico: str, regras: list[dict]) -> tuple[int, str]:
    """Decide se um tópico deve ir para a extração.

    Passo intermediário entre o fatiamento e a extração: tópico cujo assunto
    não pode gerar regra verificável em texto não precisa gastar chamada de
    LLM. A decisão é declarada no config (`excluir_topicos`), por prefixo, com
    motivo obrigatório — fica versionada e auditável, não escondida em código.

    Devolve (incluir, motivo). Default é INCLUIR: só exclui o que foi
    declarado explicitamente.
    """
    for r in regras or []:
        if topico.strip().startswith(str(r["prefixo"])):
            return 0, r.get("motivo", "declarado em excluir_topicos")
    return 1, ""


def render(tr, label, textos):
    cab = [f"=== DOCUMENTO: {label} ===", f"=== TÓPICO: {tr['topico']} ==="]
    faixa = f"=== TRECHO: páginas {tr['ini']}-{tr['fim']}"
    if tr["parte"]:
        i, n = tr["parte"].split("/")
        faixa += f" (parte {i} de {n} do mesmo tópico)"
    elif tr["n_topicos"] > 1:
        faixa += f" ({tr['n_topicos']} tópicos consecutivos)"
    cab.append(faixa + " ===")
    corpo = "\n\n".join(f"[p.{p}]\n{textos[p].strip()}" for p in range(tr["ini"], tr["fim"] + 1))
    return "\n".join(cab) + "\n\n" + corpo


def slugifica(s, n=44):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")[:n] or "trecho"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", help="filtra pelo label/slug da fonte no config")
    ap.add_argument("--budget", type=int, default=2000, help="orçamento de tokens por trecho")
    ap.add_argument("--out", default=str(AQUI / "chunks"))
    args = ap.parse_args()

    cfg = yaml.safe_load((AQUI / "config.yaml").read_text(encoding="utf-8"))
    ntok, modo = conta_tokens(cfg["model"]["model_id"])
    print(f"Contagem de tokens: {modo}\nOrçamento por trecho: {args.budget}\n")

    livros = [b for b in cfg["books"]
              if not args.book or args.book.lower() in (b["label"] + b["slug"]).lower()]
    if not livros:
        raise SystemExit(f"nenhuma fonte casa com --book {args.book!r}")

    for b in livros:
        rd = PdfReader(b["path"])
        ini, fim = b["start_page"], b["end_page"]
        topicos, trechos, textos, (n_out, n_txt, modo) = monta_trechos(
            rd, ini, fim, args.budget, ntok, b.get("topic_prefix"))

        destino = Path(args.out) / b["slug"]
        destino.mkdir(parents=True, exist_ok=True)
        for f in destino.glob("*.txt"):
            f.unlink()

        with (destino / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["n", "arquivo", "topico", "nivel_outline", "pagina_ini",
                        "pagina_fim", "n_paginas", "n_topicos", "parte", "tokens",
                        "topicos_todos", "incluir", "motivo_exclusao"])
            for i, tr in enumerate(trechos, 1):
                nome = f"{i:03d}_{slugifica(tr['topico'])}.txt"
                inc, motivo = triagem(tr["topico"], b.get("excluir_topicos"))
                tr["incluir"] = inc
                (destino / nome).write_text(render(tr, b["label"], textos), encoding="utf-8")
                w.writerow([i, nome, tr["topico"], tr["nivel"], tr["ini"], tr["fim"],
                            tr["fim"] - tr["ini"] + 1, tr["n_topicos"], tr["parte"],
                            tr["tokens"], " | ".join(tr.get("topicos", [tr["topico"]])),
                            inc, motivo])

        # verificação: a união dos trechos tem que cobrir a faixa, sem furo nem sobreposição
        cobertas = [p for tr in trechos for p in range(tr["ini"], tr["fim"] + 1)]
        esperado = list(range(ini, fim + 1))
        ok = cobertas == esperado
        szs = sorted(tr["tokens"] for tr in trechos)
        print(f"{b['slug']}: {len(topicos)} tópicos (outline {n_out} + texto {n_txt}) "
              f"-> {len(trechos)} trechos  [modo: {modo}]")
        print(f"   tokens/trecho: mediana {szs[len(szs)//2]}, min {szs[0]}, max {szs[-1]}")
        print(f"   cobertura p.{ini}-{fim} sem furo nem sobreposição: {'OK' if ok else 'FALHOU'}")
        fora = [tr for tr in trechos if not tr.get("incluir", 1)]
        if fora:
            tf = sum(tr["tokens"] for tr in fora)
            print(f"   TRIAGEM: {len(fora)} trecho(s) excluídos ({tf} tokens, "
                  f"{100*tf//sum(x['tokens'] for x in trechos)}% do capítulo)")
            print(f"   -> vão para extração: {len(trechos) - len(fora)} trechos")
        print(f"   gravado em: {destino}/  (manifest.csv + {len(trechos)} .txt)\n")


if __name__ == "__main__":
    main()
