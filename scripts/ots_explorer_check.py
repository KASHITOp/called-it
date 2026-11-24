"""D-26(c): cross-check a completed OpenTimestamps proof against two public block explorers.

    python scripts/ots_explorer_check.py PROOF --digest HEX [--before ISO]

The proof's file digest must equal ``--digest``. For every Bitcoin block attestation in the
proof, the merkle root the proof commits to must equal the ``merkle_root`` that BOTH
blockstream.info and mempool.space report for that block height, and (with ``--before``) the
block's timestamp must be earlier than that instant.

Exit codes: 0 every check passed, 1 a check failed, 2 pending (no Bitcoin attestation yet).
This trusts two explorers, not your own node; the preregistration says so (section 11).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from opentimestamps.core.notary import BitcoinBlockHeaderAttestation
from opentimestamps.core.serialize import BytesDeserializationContext
from opentimestamps.core.timestamp import DetachedTimestampFile

EXPLORERS = (
    ("blockstream.info", "https://blockstream.info/api"),
    ("mempool.space", "https://mempool.space/api"),
)
USER_AGENT = "called-it-ots-check"
TIMEOUT = 20

EXIT_PASS, EXIT_FAIL, EXIT_PENDING = 0, 1, 2


def _get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read().decode("ascii").strip()


def block_info(base: str, height: int) -> dict:
    block_hash = _get(f"{base}/block-height/{height}")
    return json.loads(_get(f"{base}/block/{block_hash}"))


def _parse_before(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def check(proof_path: Path, digest: str, before: str | None) -> int:
    ctx = BytesDeserializationContext(Path(proof_path).read_bytes())
    detached = DetachedTimestampFile.deserialize(ctx)
    ok = True

    proof_digest = detached.file_digest.hex()
    if proof_digest == digest.lower():
        print(f"PASS digest: the proof's file digest equals {digest[:12]}...")
    else:
        print("FAIL digest: the proof's file digest differs from --digest")
        return EXIT_FAIL

    attested = [
        (msg, att)
        for msg, att in detached.timestamp.all_attestations()
        if isinstance(att, BitcoinBlockHeaderAttestation)
    ]
    if not attested:
        print("PENDING: no Bitcoin attestation in the proof yet")
        return EXIT_PENDING

    limit = _parse_before(before) if before else None
    for msg, att in attested:
        merkle_root = bytes(reversed(msg)).hex()  # displayed byte-reversed, as explorers do
        print(f"block {att.height}: proof merkle root {merkle_root}")
        for name, base in EXPLORERS:
            try:
                info = block_info(base, att.height)
            except Exception as exc:  # noqa: BLE001 - report the class only
                print(f"FAIL {name}: could not read block {att.height} ({type(exc).__name__})")
                ok = False
                continue
            if info.get("merkle_root") == merkle_root:
                print(f"PASS {name}: merkle root matches")
            else:
                print(f"FAIL {name}: merkle root differs")
                ok = False
            if limit is not None:
                stamp = datetime.fromtimestamp(int(info["timestamp"]), tz=UTC)
                if stamp < limit:
                    print(f"PASS {name}: block time {stamp:%Y-%m-%dT%H:%M:%SZ} is before the limit")
                else:
                    print(f"FAIL {name}: block time {stamp:%Y-%m-%dT%H:%M:%SZ} is not before")
                    ok = False
    return EXIT_PASS if ok else EXIT_FAIL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proof", type=Path)
    parser.add_argument("--digest", required=True, help="hex sha256 the proof must be over")
    parser.add_argument(
        "--before", help="ISO instant (YYYY-MM-DDTHH:MM:SSZ) the block must precede"
    )
    args = parser.parse_args(argv)
    return check(args.proof, args.digest, args.before)


if __name__ == "__main__":
    sys.exit(main())
