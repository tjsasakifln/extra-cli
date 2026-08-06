#!/usr/bin/env python3
import base64, concurrent.futures, gzip, json, re, time
from pathlib import Path
import requests

PAYLOAD = "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"
ROWS = json.loads(gzip.decompress(base64.b64decode(PAYLOAD)).decode("utf-8"))
BASE = "https://pncp.gov.br/api/pncp/v1/orgaos"
SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json", "User-Agent": "CONFENGE-public-data-qualification/1.0"})


def get_json(url, timeout=35, params=None):
    last = None
    for attempt in range(4):
        try:
            response = SESSION.get(url, params=params, timeout=timeout)
            if response.status_code == 200:
                try:
                    return {"http": 200, "url": response.url, "data": response.json(), "error": None}
                except Exception as exc:
                    return {"http": 200, "url": response.url, "data": None, "error": f"json:{exc}", "text": response.text[:1000]}
            last = f"HTTP {response.status_code}: {response.text[:300]}"
            if response.status_code not in (429, 500, 502, 503, 504):
                break
        except Exception as exc:
            last = repr(exc)
        time.sleep(0.7 * (attempt + 1))
    return {"http": None, "url": url, "data": None, "error": last}


def parse_id(contract_id):
    match = re.fullmatch(r"([A-Za-z0-9]{14})-2-(\d+)/([0-9]{4})", contract_id)
    if not match:
        raise ValueError(contract_id)
    return match.group(1), int(match.group(3)), int(match.group(2))


def unwrap_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "content", "itens", "items", "resultado", "resultados"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def term_seq(term):
    if not isinstance(term, dict):
        return None
    for key in ("sequencialTermoContrato", "sequencialTermo", "sequencial", "id"):
        value = term.get(key)
        if value is not None:
            try:
                return int(value)
            except Exception:
                pass
    return None


def collect(row):
    out = dict(row)
    try:
        cnpj, year, seq = parse_id(row["contrato_id"])
    except Exception as exc:
        out["fatal_error"] = repr(exc)
        return out
    root = f"{BASE}/{cnpj}/contratos/{year}/{seq}"
    contract = get_json(root)
    contract_files = get_json(root + "/arquivos")
    terms = get_json(root + "/termos")
    history = get_json(root + "/historico", params={"pagina": 1, "tamanhoPagina": 500})
    empenhos = get_json(root + "/empenhos")
    cdata = contract.get("data") if isinstance(contract.get("data"), dict) else {}
    purchase_id = cdata.get("numeroControlePNCPCompra") or cdata.get("numeroControlePncpCompra")
    procurement = procurement_files = procurement_history = None
    if purchase_id:
        purchase_match = re.fullmatch(r"([A-Za-z0-9]{14})-1-(\d+)/([0-9]{4})", str(purchase_id))
        if purchase_match:
            pc, py, ps = purchase_match.group(1), int(purchase_match.group(3)), int(purchase_match.group(2))
            procurement_root = f"{BASE}/{pc}/compras/{py}/{ps}"
            procurement = get_json(procurement_root)
            procurement_files = get_json(procurement_root + "/arquivos")
            procurement_history = get_json(procurement_root + "/historico", params={"pagina": 1, "tamanhoPagina": 500})
    terms_list = unwrap_list(terms.get("data"))
    term_details = []
    seen = set()
    for term in terms_list:
        sequence = term_seq(term)
        if sequence is None or sequence in seen:
            continue
        seen.add(sequence)
        term_details.append({
            "sequencial": sequence,
            "list_item": term,
            "detail": get_json(root + f"/termos/{sequence}"),
            "files": get_json(root + f"/termos/{sequence}/arquivos"),
        })
    for event in unwrap_list(history.get("data")):
        if not isinstance(event, dict):
            continue
        sequence = event.get("sequencialTermoContrato")
        try:
            sequence = int(sequence)
        except Exception:
            continue
        if sequence in seen:
            continue
        seen.add(sequence)
        term_details.append({
            "sequencial": sequence,
            "list_item": None,
            "detail": get_json(root + f"/termos/{sequence}"),
            "files": get_json(root + f"/termos/{sequence}/arquivos"),
        })
    out.update({
        "contract_url": root,
        "contract": contract,
        "contract_files": contract_files,
        "terms": terms,
        "term_details": term_details,
        "history": history,
        "empenhos": empenhos,
        "procurement": procurement,
        "procurement_files": procurement_files,
        "procurement_history": procurement_history,
    })
    return out


def main():
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(collect, row): row for row in ROWS}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            row = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({**row, "fatal_error": repr(exc)})
            print(f"{index}/{len(ROWS)}", flush=True)
    results.sort(key=lambda item: item.get("rank", 999999))
    Path("output/tmp").mkdir(parents=True, exist_ok=True)
    Path("output/tmp/pncp_contract_qualification_raw.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "contracts": len(results),
        "contract_ok": sum(1 for row in results if row.get("contract", {}).get("http") == 200),
        "with_terms": sum(1 for row in results if row.get("term_details")),
        "with_procurement": sum(1 for row in results if row.get("procurement", {}).get("http") == 200),
        "fatal": sum(1 for row in results if row.get("fatal_error")),
    }
    Path("output/tmp/summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
