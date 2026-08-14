"""Fail-closed national contract / universe truth gates.

Shipped decision functions for issues #300 #307 #251 #267 #293 #308 #310 #316 #318 #345.
Pure guards stay separate from live HTTP/VPS I/O. No LOCAL_READY / VPS_OPERATIONAL claim.
"""

from __future__ import annotations

WAVE_ISSUES: tuple[int, ...] = (300, 307, 251, 267, 293, 308, 310, 316, 318, 345)

__all__ = ["WAVE_ISSUES"]
