from __future__ import annotations

from pathlib import Path
from uuid import UUID

RCE_PROOF_MARKER = b"MODELGATE_RCE_PROOF"


def rce_proof_observed(proof_root: str, proof_id: UUID) -> bool:
    """Check one fixed marker without returning attacker-controlled file content."""

    marker = Path(proof_root) / str(proof_id)
    try:
        if not marker.is_file() or marker.stat().st_size != len(RCE_PROOF_MARKER):
            return False
        return marker.read_bytes() == RCE_PROOF_MARKER
    except OSError:
        return False
