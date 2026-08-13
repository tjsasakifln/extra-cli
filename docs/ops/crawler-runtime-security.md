# Crawler runtime security contract

The continuous crawler uses `extra-crawl-scheduler.service` and two to four
instances of `extra-crawl-worker@.service`. These units run as the dedicated
`extra-consultoria` user and read `/etc/extra-consultoria/crawler.env`, which
must be owned by that user and have mode `0600`. The `ExecStartPre` check fails
closed when either condition is false.

The repository gate requires at least 90% of the ten systemd sandbox controls
listed in `scripts/ops/validate_crawler_runtime_security.py`; both shipped units
score 100%. On a provisioned host, also retain the native report as deployment
evidence:

```bash
systemd-analyze security extra-crawl-scheduler.service
systemd-analyze security extra-crawl-worker@1.service
```

This static score is not a claim that a VPS is operational. Host evidence must
come from the installed units at their exact deployed commit.
