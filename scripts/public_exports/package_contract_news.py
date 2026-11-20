"""Package the exact approved news-producer Python closure, without site deps."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = """
import json,sys
from pathlib import Path
import scripts.public_exports.contract_news
from scripts.public_exports.pdf_extract import PYPDF_WHEEL, verified_wheel
root=Path.cwd()
files=set()
for module in list(sys.modules.values()):
    file=getattr(module, '__file__', None)
    if file and Path(file).is_relative_to(root):
        relative=Path(file).relative_to(root)
        if relative.parts[0] == 'scripts' and relative.suffix == '.py':
            files.add(relative.as_posix())
verified_wheel(root)
files.add(PYPDF_WHEEL)
print(json.dumps(sorted(files)))
"""


def package(output: Path, sha: str) -> dict[str, object]:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("producer SHA must be a full commit")
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()  # noqa: S603,S607
    if current != sha:
        raise ValueError("checkout does not match producer SHA")
    probe = subprocess.check_output([sys.executable, "-S", "-c", PROBE], cwd=ROOT, text=True)  # noqa: S603
    files = json.loads(probe)
    contents = {}
    for name in files:
        raw = subprocess.check_output(["git", "show", f"{sha}:{name}"], cwd=ROOT)  # noqa: S603,S607
        if raw != (ROOT / name).read_bytes():
            raise ValueError(f"producer checkout differs: {name}")
        contents[name] = raw
    manifest = {
        "schema": "confenge.contract-news-producer/v1", "repository": "tjsasakifln/extra-cli",
        "producer_commit": sha, "fact_contract": "confenge.contract-news-facts/v1",
        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in contents.items()},
    }
    contents["producer-manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    with tarfile.open(output, "w:gz") as archive:
        for name, raw in sorted(contents.items()):
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            member.mode = 0o444
            member.mtime = 0
            archive.addfile(member, io.BytesIO(raw))
    return {
        "ok": True, "producer_commit": sha, "files": len(contents), "bytes": output.stat().st_size,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.output, args.sha), sort_keys=True))


if __name__ == "__main__":
    main()
