#!/usr/bin/env python3
import base64, concurrent.futures, gzip, json, re, time
from pathlib import Path
from urllib.parse import urlparse
import requests

PAYLOAD = "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"

BASE = "https://pncp.gov.br/api/pncp/v1"
S = requests.Session()
S.headers.update({"User-Agent":"CONFENGE-contract-document-enrichment/1.0","Accept":"application/json"})

def get_json(url):
    err = None
    for n in range(5):
        try:
            r = S.get(url, timeout=40)
            if r.status_code == 200:
                return r.json(), 200, None
            err = f"HTTP {r.status_code}: {r.text[:160]}"
            if r.status_code not in (429,500,502,503,504): break
        except Exception as e: err = repr(e)
        time.sleep(min(2**n,12))
    return None, None, err

def walk(x, path=""):
    if isinstance(x, dict):
        for k,v in x.items():
            p=f"{path}.{k}" if path else k
            yield p,v
            yield from walk(v,p)
    elif isinstance(x,list):
        for i,v in enumerate(x): yield from walk(v,f"{path}[{i}]")

def urls_in(x):
    out=[]
    for p,v in walk(x):
        if isinstance(v,str):
            for u in re.findall(r'https?://[^\s\"<>]+',v): out.append((p,u.rstrip('.,;)]}')))
    return out

def procurement_id(contract):
    for p,v in walk(contract):
        if isinstance(v,str) and re.fullmatch(r"\d{14}-1-\d{6}/\d{4}",v.strip()): return v.strip()
    for key in ("numeroControlePNCPCompra","numeroControlePncpCompra","numeroControlePNCPContratacao"):
        for p,v in walk(contract):
            if p.split('.')[-1].lower()==key.lower() and isinstance(v,str): return v.strip()
    seq=yr=None
    for p,v in walk(contract):
        k=p.split('.')[-1].lower()
        if k in ("sequencialcompra","sequencialcontratacao") and str(v).isdigit(): seq=int(v)
        if k in ("anocompra","anocontratacao") and str(v).isdigit(): yr=int(v)
    if seq and yr:
        cnpj=next((str(v) for p,v in walk(contract) if p.split('.')[-1].lower() in ("cnpjorgao","cnpj") and re.fullmatch(r"\d{14}",str(v))),None)
        if cnpj:return f"{cnpj}-1-{seq:06d}/{yr}"
    return None

def file_rows(data,cnpj,yr,seq):
    src=data if isinstance(data,list) else (data.get("data") or data.get("items") or []) if isinstance(data,dict) else []
    out=[]
    for i,it in enumerate(src,1):
        if not isinstance(it,dict):continue
        flat={p.split('.')[-1]:v for p,v in walk(it) if not isinstance(v,(dict,list))}
        title=" | ".join(str(flat.get(k) or '') for k in ("titulo","nomeArquivo","tipoDocumentoNome","descricao","nome") if flat.get(k))
        us=[u for _,u in urls_in(it)]
        n=flat.get("sequencialDocumento") or flat.get("sequencial") or flat.get("id") or i
        if not us:us=[f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/compras/{yr}/{seq}/arquivos/{n}"]
        for u in us:out.append({"url":u,"title":title,"meta":flat})
    return out

def score(row):
    s=(row.get("url","")+" "+row.get("title","")).lower()
    n=0
    if "compras.gov.br" in s:n+=140
    if ".zip" in s or " zip" in s:n+=120
    if any(k in s for k in ("planilha","orcament","orçamento","budget")):n+=90
    if any(k in s for k in (".xlsx",".xls",".ods",".csv")):n+=70
    if any(k in s for k in ("edital","anexo","projeto","documentos","proposta")):n+=25
    return n

def one(inp):
    m=re.fullmatch(r"(\d{14})-2-(\d+)/(\d{4})",inp["c"])
    cnpj,seq,yr=m.group(1),int(m.group(2)),int(m.group(3))
    cu=f"{BASE}/orgaos/{cnpj}/contratos/{yr}/{seq}"
    contract,code,err=get_json(cu)
    out={"rank":inp["r"],"empresa":inp["e"],"contrato_id":inp["c"],"contract_api_url":cu,"contract_http":code,"error":err}
    if not contract:return out|{"status":"contract_fetch_failed"}
    pid=procurement_id(contract)
    out["procurement_id"]=pid
    found=[{"url":u,"title":p,"meta":{}} for p,u in urls_in(contract) if "compras.gov.br" in u.lower() or ".zip" in u.lower()]
    if pid:
        mm=re.fullmatch(r"(\d{14})-1-(\d{6})/(\d{4})",pid)
        pc,pseq,pyr=mm.group(1),int(mm.group(2)),int(mm.group(3))
        out["procurement_page_url"]=f"https://pncp.gov.br/app/editais/{pc}/{pyr}/{pseq}"
        fu=f"{BASE}/orgaos/{pc}/compras/{pyr}/{pseq}/arquivos"
        out["files_api_url"]=fu
        files,fcode,ferr=get_json(fu)
        out["files_http"]=fcode
        out["files_error"]=ferr
        if files:found+=file_rows(files,pc,pyr,pseq)
    uniq={}
    for x in found:uniq[x["url"]]=x
    cand=sorted(uniq.values(),key=score,reverse=True)
    out["candidates_count"]=len(cand)
    out["candidates"]=cand[:20]
    if cand:
        best=cand[0]
        out["best_url"]=best["url"]
        out["best_name"]=best.get("title")
        out["best_score"]=score(best)
        out["is_zip"]=".zip" in (best["url"]+" "+str(best.get("title"))).lower()
        out["is_comprasgov"]="compras.gov.br" in best["url"].lower()
        out["status"]="package_candidate_found" if out["best_score"]>=70 else "procurement_found_no_strong_package"
    else:out["status"]="procurement_found_no_files" if pid else "procurement_id_not_found"
    return out

def main():
    items=json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        results=list(ex.map(one,items))
    results.sort(key=lambda x:x["rank"])
    Path("output").mkdir(exist_ok=True)
    Path("output/pncp_enrichment_results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    summary={k:sum(1 for r in results if r.get(k)) for k in ("procurement_id","best_url","is_zip","is_comprasgov")}
    print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
