# Adversarial QA Checklist

- [ ] Auditor is not the implementer
- [ ] Diff matches execution card scope
- [ ] Happy path tested
- [ ] Failure path tested
- [ ] Retry/partial/ambiguous states considered
- [ ] Skipped critical tests disclosed (fail evidence if hidden)
- [ ] No continue-on-error on critical gates
- [ ] Lint/type/security basic checks considered
- [ ] Migrations fresh/upgrade if schema touched
- [ ] Claims vs evidence matrix checked
- [ ] False green patterns hunted (fixture health, empty success)
- [ ] Verdict PASS|FAIL|BLOCKED with reproducible commands
