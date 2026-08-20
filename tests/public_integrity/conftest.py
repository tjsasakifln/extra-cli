"""This slice must stay fast under the repo pytest.ini.

Root addopts enable ``--cov=scripts`` plus HTML for the whole tree (~5 min).
That is outside this exclusive area and blows skeptic/CI wait budgets.
Unregister the cov plugin for tests collected here.
"""

from __future__ import annotations


def pytest_configure(config) -> None:  # type: ignore[no-untyped-def]
    plugin = config.pluginmanager.get_plugin("_cov")
    if plugin is not None:
        config.pluginmanager.unregister(plugin)
    if hasattr(config.option, "cov_report"):
        config.option.cov_report = set()
    if hasattr(config.option, "no_cov"):
        config.option.no_cov = True
