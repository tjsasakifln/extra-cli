#!/usr/bin/env python3
import base64, concurrent.futures, gzip, json, re, time
from pathlib import Path
import requests

PAYLOAD = "H4sIAAAAAAACA6tWKkktLlGyUjA0MNA1NTE3NTLQNTQxM9QzNDI1tLTQNTMyMzcyNjE2MTIwMjfSUSpKzCvJTE7Mz1PIzEtJzSvRSM7PzU3MSwVJ6QYUp+Yp5OQXK+koJqWm5edn5ugZGxkY6RsZGtQCAKZ07rBoAAAA"
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
