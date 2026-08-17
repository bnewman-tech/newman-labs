"""Run the local document-security boundary against inert PDF fixtures."""

import json
import time
from pathlib import Path

from libs.document_intelligence.security import (
    _scan_document,
    shutdown_document_security,
)

FIXTURE_DIRECTORY = Path(__file__).parents[1] / "tests" / "fixtures"
EXPECTED_SCANS = [
    ("active_content_cold", "active-content.pdf", "block"),
    ("benign_cold", "benign.pdf", "allow"),
    ("benign_warm", "benign-second.pdf", "allow"),
    ("benign_cached", "benign.pdf", "allow"),
    ("encrypted", "encrypted-marker.pdf", "block"),
    ("prompt_injection", "prompt-injection.pdf", "block"),
]


if __name__ == "__main__":
    outcomes = []
    try:
        for case, filename, expected_verdict in EXPECTED_SCANS:
            started = time.perf_counter()
            scan = _scan_document(
                content=(FIXTURE_DIRECTORY / filename).read_bytes(),
                filename=filename,
            )
            outcomes.append({
                "case": case,
                "filename": filename,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                **scan.model_dump(mode="json"),
            })
            if scan.verdict.value != expected_verdict:
                raise RuntimeError(f"{filename} expected {expected_verdict}, got {scan.verdict.value}")
    finally:
        shutdown_document_security()

    print(json.dumps(outcomes, indent=2))
