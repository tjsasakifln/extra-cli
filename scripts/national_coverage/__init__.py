"""Versioned national coverage denominator (#302 residual, SEO/research gate)."""

from scripts.national_coverage.evaluate import evaluate_from_dict
from scripts.national_coverage.models import SCHEMA_VERSION, CoverageRecord

__all__ = ["SCHEMA_VERSION", "CoverageRecord", "evaluate_from_dict"]
