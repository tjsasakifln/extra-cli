# Security & dependency audit — ARCH-RESET

```bash
bandit -r scripts/ -f txt -q
pip-audit -r requirements.txt
python3 -m piplicenses  # optional
```

Bandit High findings on crawlers are expected; this is evidence, not a clean-seal claim.
