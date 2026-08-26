#!/usr/bin/env bash
# Passos 2 e 3 do pipeline de extração, para UMA fonte, numa GPU.
#
# O passo 1 (detectar bordas) não usa GPU e já roda para todas as fontes de uma
# vez — não entra aqui. Os passos 4 e 5 são cross-fonte (consolidam e fundem
# entre livros) e rodam UMA vez, depois que todas as fontes terminarem.
#
#   ./scripts/extrair_fonte.sh <filtro-do-book> <gpu> [out-dir]
#
# Exemplos:
#   ./scripts/extrair_fonte.sh cap5       3          # Gramática Vol.1 Cap.5
#   ./scripts/extrair_fonte.sh gramatica2 4          # Vol.2 Cap.7 + Cap.8
#   ./scripts/extrair_fonte.sh tania      5          # notas de consultoria
set -uo pipefail

BOOK="${1:?uso: extrair_fonte.sh <filtro-do-book> <gpu> [out-dir]}"
GPU="${2:?informe o índice da GPU}"
OUT="${3:-output_v2}"
LOG="logs/extracao_${BOOK}_gpu${GPU}.log"

mkdir -p logs
exec > >(tee -a "$LOG") 2>&1

echo "════════════════════════════════════════════════════════════════"
echo " fonte: $BOOK  |  GPU: $GPU  |  saída: extraction/$OUT"
echo " início: $(date '+%F %T')"
echo "════════════════════════════════════════════════════════════════"

run() {
  docker compose exec -T -e CUDA_VISIBLE_DEVICES="$GPU" judge bash -lc "$1"
}

echo; echo "── PASSO 2 · triagem de tópicos ──────────────────────────────"
if ! run "PYTHONPATH=src /opt/venv/bin/python libras_pipeline/extraction/triagem_topicos.py --book '$BOOK'"; then
  echo "PASSO 2 FALHOU — abortando antes de gastar a extração"; exit 1
fi

echo; echo "── PASSO 3 · extração de regras ──────────────────────────────"
if ! run "PYTHONPATH=src /opt/venv/bin/python libras_pipeline/extraction/extract.py --book '$BOOK' --chunks --out-dir '$OUT'"; then
  echo "PASSO 3 FALHOU"; exit 1
fi

echo; echo "════════════════════════════════════════════════════════════════"
echo " CONCLUÍDO: $BOOK  |  fim: $(date '+%F %T')"
echo " Os passos 4 e 5 são cross-fonte: rode-os só depois que as três"
echo " sessões terminarem, uma única vez."
echo "════════════════════════════════════════════════════════════════"
