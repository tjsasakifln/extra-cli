"""Multi-channel hybrid retrieval — channels independent; union is authoritative."""
from scripts.ops.hybrid_sector.retrieval.fusion import fuse_candidates
from scripts.ops.hybrid_sector.retrieval.hybrid import run_hybrid_retrieval

__all__ = ["fuse_candidates", "run_hybrid_retrieval"]
