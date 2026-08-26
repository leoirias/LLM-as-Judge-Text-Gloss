# SPECIFY — o que estamos validando (conceitos, não regras)

Etapa 1 do survey (§14). Aqui NÃO ficam as regras — elas vivem no
`rules/rule_package.yaml` (e crescem com o tempo). Aqui a gente **define os
conceitos** que o validador precisa entender. É o alvo conceitual; dele sai o
resumo que vira o bloco de instruções do prompt do juiz e os critérios do
`evaluate.py`.

## Construto — o que "glosa correta" significa

Uma glosa correta, acima de tudo, **representa o contexto e a intenção da frase de
forma fluida e natural para surdos e sinalizantes**, descrevendo os SINAIS a serem
feitos e **respeitando as normas e a estrutura da língua de sinais**. A conformidade
de escrita é meio, não fim.

Três dimensões, da superfície ao topo:
1. **Superfície** — segue a convenção de escrita. Verificável por código. Necessária, não suficiente.
2. **Fidelidade** — preserva o sentido e a intenção da frase.
3. **Naturalidade/estrutura** — sequência de sinais fluida e natural, respeitando a estrutura da língua.

Passar em (1) não garante (2) e (3) — exigem julgamento (LLM) e, no limite,
avaliação por **surdos** (§12): o LLM é proxy de naturalidade, não a verdade final.

## Direção: este validador é Voice2Sign (texto → glosa)

As regras se dividem em dois processos (campo `pipeline` de cada regra no pacote):
- **Voice2Sign (texto → glosa)** — o que ESTE validador usa.
- **Sign2Voice (vídeo → glosa)** — regras que dependem de expressão facial, uso do
  espaço, orientação/movimento da mão. Pertencem ao pipeline **inverso** e ficam
  **fora** deste validador.

Logo, aqui **não** existe abstenção "por depender de expressão facial" — isso é do
Sign2Voice. Um canal não-textual que apareça vira **flag** (abaixo), não erro nem motivo de abstenção.

## Alvo do pronome (validado com a consultoria)

Referente presente / conversa direta: o pronome (PRO.1/PRO.2/PRO.3) é normalmente
**omitido**, MAS mantê-lo **não é erro** — pode ser **flag de pós-processamento** para
indicar possível expressão facial. Presença de pronome nunca reprova.

## Alvo do WILL (validado com a consultoria)

WILL permanece nas construções de futuro, EXCETO se a frase já tem outro marcador de
tempo (NOW, TOMORROW, HOW LONG…), quando cai. Julgamento do LLM (resíduo).

## Uma frase, VÁRIAS regras

Não é uma regra por frase — **várias regras podem se aplicar à mesma glosa**. O
veredito considera todas as aplicáveis e a explicação cita todas as regras usadas.

## Espaço de decisão (§14, Fig. 4)

Três estados: **`valido` · `invalido` · `nao_coberto`**.
`nao_coberto` = **nenhuma regra do pacote cobre o fenômeno** (falta de cobertura),
NÃO "depende de expressão facial". Abster-se ≠ reprovar; sai da métrica de acurácia.

## Multi-língua

Construto e arquitetura são os mesmos para **ASL** e **Libras**. Muda o **pacote de
regras** e o **dataset**; o código é agnóstico de língua. Hoje o pacote/dados são ASL.
(A consultoria já entregou o embrião de uma **gramática formal/CFG** para Libras —
formato mais forte, que no futuro habilita um verificador determinístico de verdade.)

## O que o ouro (ASL) NÃO garante

- Não aplicou normalização PRO.1/PRO.2 (por isso pronome não é medido contra ele).
- Ruído pontual de pontuação/typo herdado da fonte.
- Não passou por validação de surdos (§12) — pendente confirmar com a consultoria.
