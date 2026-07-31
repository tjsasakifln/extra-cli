# SECURITY-REVIEW

Preserved from PR #186 foundation:

- allowlisted argv / shell=False
- loopback bind (public bind denylist)
- CSRF on mutating routes
- redaction
- path containment for artifacts
- no DOD auto-accept
- no auto-outreach

Added:

- formula injection neutralization for XLSX/CSV cells
- ZIP members basename-only (zip-slip defense)
- workflow execution in-process only for known workflow.* IDs
- ACCEPT hash binding

Tests: `tests/command_center/test_api_security.py` + workbench flows.
