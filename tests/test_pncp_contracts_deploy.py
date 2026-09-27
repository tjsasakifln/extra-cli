"""Regression contracts for the canonical PNCP contracts deployment path."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_ansible_reapply_keeps_the_canonical_contracts_timer_running() -> None:
    playbook = yaml.safe_load(
        (ROOT / "deploy" / "ansible" / "site-contracts-ops.yml").read_text(encoding="utf-8")
    )[0]
    variables = playbook["vars"]

    assert "pncp-contracts.timer" in variables["unit_files"]
    assert "pncp-contracts.timer" in variables["enabled_timers"]
    assert "pncp-contracts.timer" not in variables["disabled_timers"]
    for legacy_timer in (
        "pncp-crawl-full.timer",
        "pncp-crawl-inc.timer",
        "extra-crawl-pncp.timer",
    ):
        assert legacy_timer in variables["disabled_timers"]
        assert legacy_timer not in variables["enabled_timers"]
    task_names = [task["name"] for task in playbook["tasks"]]
    assert task_names.index("Reload systemd before managing installed units") < task_names.index(
        "Enable ops timers"
    )
    assert task_names.index("Stop legacy crawl services") < task_names.index("Enable ops timers")
    assert task_names.index("Read back legacy timer states") < task_names.index("Enable ops timers")
    assert task_names.index("Read back legacy service states") < task_names.index("Enable ops timers")


def test_provisioning_keeps_pncp_contracts_as_the_only_contracts_writer() -> None:
    script = (ROOT / "deploy" / "provision-vps.sh").read_text(encoding="utf-8")
    minimal_block = script.split("local minimal_timers=(", 1)[1].split(")", 1)[0]
    full_block = script.split("local full_timers=(", 1)[1].split(")", 1)[0]

    assert "pncp-contracts" in minimal_block
    assert "pncp-contracts" in full_block
    legacy_block = script.split("local legacy_contract_writer_timers=(", 1)[1].split(")", 1)[0]
    legacy_services_block = script.split("local legacy_contract_writer_services=(", 1)[1].split(")", 1)[0]
    for legacy_timer in ("pncp-crawl-full", "pncp-crawl-inc", "extra-crawl-pncp"):
        assert legacy_timer not in minimal_block
        assert legacy_timer not in full_block
        assert legacy_timer in legacy_block
        assert legacy_timer in legacy_services_block
    disable_call = 'systemctl disable --now "${timer}.timer"'
    assert disable_call in script
    assert f"{disable_call} 2>/dev/null || true" not in script
    assert script.index(disable_call) < script.index('case "$ENABLE_TIMERS" in')
    stop_call = 'systemctl stop "${service}.service"'
    assert stop_call in script
    assert script.index(stop_call) < script.index('case "$ENABLE_TIMERS" in')


def test_release_migrates_the_staged_code_before_pinning_or_scheduling_it() -> None:
    script = (ROOT / "deploy" / "confenge" / "cut_release.sh").read_text(encoding="utf-8")
    migration_call = "from scripts.ops.apply_migrations import main"
    pin_call = 'python3 -P "$TARGET/deploy/confenge/pin_release.py"'

    assert "scripts/ops/apply_migrations.py" in script
    assert "dotenv_values" in script
    assert 'source "$MIGRATION_ENV_FILE"' not in script
    assert '--dsn "$MIGRATION_DSN"' not in script
    assert '"LOCAL_DATALAKE_DSN=$MIGRATION_DSN" \\' not in script
    assert 'PYTHONPATH="$TARGET"' in script
    assert "env -i" in script
    assert "--preserve-environment" not in script
    assert migration_call in script
    assert pin_call in script
    assert script.index(migration_call) < script.index(pin_call)
    assert "CUT_RELEASE_MIGRATIONS_OK" in script
    assert script.index('systemctl stop "${CONTRACT_WRITER_TIMERS[@]}"') < script.index(migration_call)
    assert script.index('systemctl stop "${CONTRACT_WRITER_SERVICES[@]}"') < script.index(migration_call)
    assert "trap restore_preserved_chain_state EXIT" in script
    assert "release chain remains stopped" in script
    assert "quiesce_release_chain" in script
    assert "cannot preserve unsafe legacy writer state" in script
    assert "ACTIVE_CHAIN_TIMERS" in script
    assert "ACTIVE_CHAIN_SERVICES" in script
    assert 'for unit in "${ACTIVE_CHAIN_TIMERS[@]}"; do systemctl start "$unit" || failed=1; done' in script
    assert "ACTIVE_CONTACT_DISCOVERY_INSTANCES" in script
    assert "--state=active,activating" in script
    assert "CONTACT_DISCOVERY_LIST" in script
    assert "cannot enumerate active contact-discovery workers" in script
    assert 'for unit in "${ACTIVE_CHAIN_SERVICES[@]}" "${ACTIVE_CONTACT_DISCOVERY_INSTANCES[@]}"; do systemctl start "$unit" || failed=1; done' in script
    assert "flock --nonblock 9" in script

    migrator = (ROOT / "scripts" / "ops" / "apply_migrations.py").read_text(encoding="utf-8")
    assert "pg_try_advisory_lock" in migrator
    assert "another migration runner owns" in migrator


def test_pause_preserving_cut_restores_only_previously_active_canonical_chain() -> None:
    script = (ROOT / "deploy" / "confenge" / "cut_release.sh").read_text(encoding="utf-8")

    assert "ACTIVE_CHAIN_TIMERS" in script
    assert "ACTIVE_CHAIN_SERVICES" in script
    assert 'for unit in "${CHAIN_TIMERS[@]}"; do' in script
    assert 'for unit in "${CHAIN_SERVICES[@]}"; do' in script
    assert 'for unit in "${ACTIVE_CHAIN_TIMERS[@]}"; do systemctl start "$unit" || failed=1; done' in script
    assert "ACTIVE_CONTACT_DISCOVERY_INSTANCES" in script
    assert "--state=active,activating" in script
    assert 'for unit in "${ACTIVE_CHAIN_SERVICES[@]}" "${ACTIVE_CONTACT_DISCOVERY_INSTANCES[@]}"; do systemctl start "$unit" || failed=1; done' in script
    assert "LEGACY_WRITER_TIMERS" in script
    assert "LEGACY_WRITER_SERVICES" in script
    assert 'systemctl start "$unit"' in script
    assert "contact-discovery worker did not restart" in script


def test_release_pin_disables_all_legacy_contract_writers() -> None:
    source = (ROOT / "deploy" / "confenge" / "pin_release.py").read_text(encoding="utf-8")
    disabled_block = source.split("CHAIN_DISABLED_TIMERS = (", 1)[1].split(")", 1)[0]

    for timer in (
        "pncp-crawl-full.timer",
        "pncp-crawl-inc.timer",
        "extra-crawl-pncp.timer",
    ):
        assert timer in disabled_block
    apply_block = source.split("def apply(", 1)[1].split("def verify(", 1)[0]
    disable_call = '_run(["systemctl", "disable", "--now", *CHAIN_DISABLED_TIMERS])'
    enable_call = '_run(["systemctl", "enable", "--now", *CHAIN_TIMERS])'
    stage_call = "snapshots, staged = _stage_dropins(rendered)"
    assert apply_block.index(stage_call) < apply_block.index(disable_call)
    assert apply_block.index(disable_call) < apply_block.index(enable_call)
    assert "legacy writer did not stop" in apply_block


def test_backup_oneshot_does_not_restart_and_refill_staging() -> None:
    unit = (ROOT / "deploy" / "systemd" / "extra-db-backup.service").read_text(encoding="utf-8")
    assert "Restart=no" in unit
    assert "Restart=on-failure" not in unit
