# ruff: noqa
# ARQUIVO DE EVIDENCIA ARQUIVADO — NAO E CODIGO MANTIDO.
#
# Script de baseline do @architect, persistido pelo @po (AC 16 da story
# docs/stories/story-outbound-sector-classifier-false-positive-01.md) exatamente
# como foi executado, para que a medicao continue reproduzivel e auditavel.
# Reformatar o script alteraria o artefato de evidencia, por isso ele e isento
# do lint em vez de reescrito.
#
# A versao MANTIDA e portavel deste baseline — com caminhos relativos ao
# repositorio e executavel em CI — e o teste formal de nao-regressao em
# tests/commercial_leads/test_real_corpus_no_regression.py.
"""FINAL design: narrow physical-presence gate + fundacao disambiguation + SQL seed preservation."""
import json, glob, re, sys
sys.path.insert(0, "/home/tjsasakifln/code/confenge/extra-cli")
from scripts.commercial_leads import contract_relevance as cr
from scripts.confenge_universe import target_fit as tf

norm = cr.normalize_text

ADVERSARIAL = [
    ("CONTRATACAO DE EMPRESA PARA LOCACAO DE ESTANDE NA FEIRA DA CONSTRUCAO CIVIL DE VITORIA", False),
    ("PATROCINIO DE ESPACO EM CONGRESSO DE CONSTRUCAO CIVIL", False),
    ("REPASSE A FUNDACAO MUNICIPAL DE CULTURA PARA APOIO ADMINISTRATIVO", False),
    ("CONTRATO COM A FUNDACAO DE APOIO AO DESENVOLVIMENTO DA PESQUISA", False),
    ("PRESTACAO DE SERVICOS PELA FUNDACAO EDUCACIONAL DE SAO JOSE", False),
    ("INSCRICAO DE SERVIDORES NO XIX SEMINARIO CAPIXABA DE PREVIDENCIA", False),
    # must REMAIN execution (recall guards, incl. advisor's counter-example)
    ("CONSTRUCAO DE LABORATORIO PARA O CURSO DE ENGENHARIA CIVIL", True),
    ("REFORMA DO BLOCO DIDATICO DO CURSO DE ENGENHARIA CIVIL DA UNIVERSIDADE", True),
    ("CONSTRUCAO DE CENTRO DE CAPACITACAO PROFISSIONAL EM ALVENARIA ESTRUTURAL", True),
    ("EXECUCAO DE OBRA DE CONSTRUCAO CIVIL DA ESCOLA MUNICIPAL", True),
    ("EXECUCAO DE FUNDACAO PROFUNDA COM ESTAQUEAMENTO PARA O EDIFICIO SEDE", True),
    ("SERVICOS DE FUNDACAO E ESTRUTURA EM CONCRETO ARMADO", True),
    ("EMPREITADA GLOBAL PARA CONSTRUCAO CIVIL DO GINASIO POLIESPORTIVO", True),
    ("EXECUCAO DE OBRA DE ENGENHARIA COM FUNDACAO EM SAPATA CORRIDA", True),
    ("PAVIMENTACAO ASFALTICA E DRENAGEM PLUVIAL DA RUA X", True),
    ("REFORMA E AMPLIACAO DO ESTANDE DE TIRO DA POLICIA MILITAR COM OBRA CIVIL", True),
]

def report(tag):
    print(f"\n--- {tag} ---")
    bad = 0
    for obj, want in ADVERSARIAL:
        ex = tf._object_is_execution(obj)
        ok = ex == want
        bad += not ok
        print(f"  {'OK ' if ok else 'XX '} exec={ex!s:5} want={want!s:5} :: {obj[:72]}")
    print(f"  mismatches: {bad}/{len(ADVERSARIAL)}")

report("BEFORE")

REAL = []
for f in sorted(glob.glob("/home/tjsasakifln/code/confenge/extra-cli/evals/commercial_leads/real/*.jsonl")):
    for line in open(f):
        line = line.strip()
        if not line: continue
        r = json.loads(line)
        o = r.get("objeto_contrato_original") or r.get("objeto") or ""
        if o: REAL.append(o)

def labeled():
    for f in sorted(glob.glob("/home/tjsasakifln/code/confenge/extra-cli/evals/commercial_leads/*.jsonl")):
        for line in open(f):
            line = line.strip()
            if not line: continue
            r = json.loads(line)
            if r.get("relevant") is None: continue
            yield (r.get("objeto") or ""), bool(r["relevant"])

def metrics():
    tp=fp=tn=fn=0
    for o,g in labeled():
        p = cr.classify_contract_relevance(o).status == "PASS"
        if p and g: tp+=1
        elif p and not g: fp+=1
        elif not p and not g: tn+=1
        else: fn+=1
    return {"tp":tp,"fp":fp,"tn":tn,"fn":fn,
            "precision":round(tp/(tp+fp),4) if tp+fp else 0,
            "recall":round(tp/(tp+fn),4) if tp+fn else 0}

m_before = metrics()
rel_before = [cr.classify_contract_relevance(o).status for o in REAL]
exec_before = [tf._object_is_execution(o) for o in REAL]

# ================= FINAL DESIGN =================
FOUNDATION_ENG = (
    "fundacao profunda", "fundacoes profundas", "fundacao rasa", "fundacoes rasas",
    "execucao de fundacao", "execucao de fundacoes", "servicos de fundacao",
    "servico de fundacao", "obra de fundacao", "obras de fundacao",
    "bloco de fundacao", "blocos de fundacao", "fundacao e estrutura",
    "fundacoes e estruturas", "estaqueamento", "estaca helice", "estaca raiz",
    "sapata corrida", "radier", "fundacao em concreto",
)
ENTITY_FUNDACAO_RE = re.compile(
    r"\bfundac(?:ao|oes)\s+(?:municipal|estadual|federal|nacional|educacional|cultural|"
    r"universitaria|hospitalar|de\s+(?:apoio|cultura|saude|ensino|pesquisa|"
    r"desenvolvimento|amparo|assistencia|previdencia|educacao)|"
    r"[a-z]+\s+de\s+[a-z]+)\b"
)
# NARROW: physical event presence only. NO training/education terms.
EVENT_PRESENCE_RE = re.compile(
    r"\b(feira|estande|expositor|exposicao|congresso|seminario|simposio|"
    r"salao|patrocinio|inscricao|credenciamento\s+de\s+evento)\b"
)
EXEC_ESCAPE = (
    "execucao de obra", "empreitada", "pavimentacao", "terraplenagem",
    "reforma predial", "obra de construcao civil", "construcao de",
    "reforma d", "ampliacao d", "drenagem", "saneamento",
)

cr.STRONG_PHRASES = tuple(p for p in cr.STRONG_PHRASES if p != "fundacao") + FOUNDATION_ENG
cr.STRONG_TOKENS = tuple(t for t in cr.STRONG_TOKENS if t != "fundacao")
cr.POSITIVE_CONTEXT = tuple(t for t in cr.POSITIVE_CONTEXT if t != "fundacao")

_orig = cr.classify_contract_relevance

def _neutralize(objeto):
    """Strip evidence attributable to entity-name / event-theme, then reclassify."""
    n = norm(objeto)
    stripped = n
    if ENTITY_FUNDACAO_RE.search(n) and not any(p in n for p in FOUNDATION_ENG):
        stripped = ENTITY_FUNDACAO_RE.sub(" ", stripped)
    if EVENT_PRESENCE_RE.search(n) and not any(e in n for e in EXEC_ESCAPE):
        # event theme: construction words describe the EVENT, not the work
        stripped = re.sub(r"\b(construcao civil|construcao|engenharia|obra|obras)\b", " ", stripped)
    return stripped

def classify_v4(objeto):
    s = _neutralize(objeto)
    if s != norm(objeto):
        r = _orig(s)
        r.reason_codes = list(r.reason_codes) + ["evidence_neutralized_entity_or_event"]
        return r
    return _orig(objeto)

cr.classify_contract_relevance = classify_v4
tf.classify_contract_relevance = classify_v4

_orig_exec = tf._object_is_execution
def exec_v4(obj):
    s = _neutralize(obj)
    return _orig_exec(s if s != norm(obj) else obj)
tf._object_is_execution = exec_v4
tf._EXECUTION_MARKERS = tuple(m for m in tf._EXECUTION_MARKERS
                              if m not in ("fundacao de", "fundacoes de")) + FOUNDATION_ENG

report("AFTER")

m_after = metrics()
rel_after = [cr.classify_contract_relevance(o).status for o in REAL]
exec_after = [tf._object_is_execution(o) for o in REAL]

print("\n== LABELED GATE METRICS (holdout gate: P>=0.95 R>=0.90) ==")
print(" before:", json.dumps(m_before))
print(" after :", json.dumps(m_after))
print("\n== REAL CORPUS n=%d ==" % len(REAL))
print(" relevance PASS before=%d after=%d" % (rel_before.count("PASS"), rel_after.count("PASS")))
print(" is_execution   before=%d after=%d" % (sum(exec_before), sum(exec_after)))

print("\n== ALL FLIPS ==")
for o,b,a in zip(REAL, rel_before, rel_after):
    if b!=a: print(f"  rel  {b}->{a} :: {o[:115]}")
for o,b,a in zip(REAL, exec_before, exec_after):
    if b!=a: print(f"  exec {b}->{a} :: {o[:115]}")
