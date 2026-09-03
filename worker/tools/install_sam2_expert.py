"""Install pinned, license-reviewed SAM 2.1 sources and checkpoints.

The production worker never downloads code or weights. Run this setup tool
explicitly before enabling the optional Pose V6.8 silhouette expert.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import urllib.request
from pathlib import Path


SAM2_REPOSITORY = "https://github.com/facebookresearch/sam2.git"
SAM2_REVISION = "2b90b9f5ceec907a1c18123530e92e794ad901a4"
CHECKPOINTS = {
    "sam2.1_hiera_base_plus": {
        "url": "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_base_plus.pt",
        "bytes": 323_606_802,
        "sha256": "a2345aede8715ab1d5d31b4a509fb160c5a4af1970f199d9054ccfb746c004c5",
    },
    "sam2.1_hiera_large": {
        "url": "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt",
        "bytes": 898_083_611,
        "sha256": "2647878d5dfa5098f2f8649825738a9345572bae2d4350a2468587ece47dd318",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install official Apache-2.0 SAM 2.1 silhouette artifacts",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--model",
        choices=("base_plus", "large", "all"),
        default="all",
    )
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    root = repository / "worker" / "models" / "sam2"
    source = root / "sources" / "sam2"
    _clone_pinned(source, force=args.force)
    selected = {
        "base_plus": ("sam2.1_hiera_base_plus",),
        "large": ("sam2.1_hiera_large",),
        "all": tuple(CHECKPOINTS),
    }[args.model]
    for name in selected:
        metadata = CHECKPOINTS[name]
        target = root / "checkpoints" / f"{name}.pt"
        if args.force or not _complete(target, metadata):
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".pt.part")
            _download_with_resume(str(metadata["url"]), temporary)
            _promote(temporary, target, metadata)
        print(
            f"{name}: {target} bytes={target.stat().st_size} "
            f"sha256={_sha256(target)}"
        )
    return 0


def _clone_pinned(target: Path, *, force: bool) -> None:
    if target.is_dir():
        current = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if current != SAM2_REVISION:
            raise RuntimeError(f"unexpected SAM2 revision in {target}: {current}")
        return
    if target.exists():
        raise RuntimeError(f"refusing to overwrite existing path: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--filter=blob:none", SAM2_REPOSITORY, str(target)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(target), "checkout", "--detach", SAM2_REVISION],
        check=True,
    )


def _complete(path: Path, metadata: dict[str, object]) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == int(metadata["bytes"])
        and _sha256(path) == str(metadata["sha256"])
    )


def _promote(
    temporary: Path,
    target: Path,
    metadata: dict[str, object],
) -> None:
    expected_bytes = int(metadata["bytes"])
    actual_bytes = temporary.stat().st_size if temporary.is_file() else 0
    if actual_bytes != expected_bytes:
        raise RuntimeError(
            f"artifact size mismatch for {target.name}: "
            f"{actual_bytes} != {expected_bytes}"
        )
    actual_hash = _sha256(temporary)
    if actual_hash != str(metadata["sha256"]):
        raise RuntimeError(
            f"artifact SHA256 mismatch for {target.name}: {actual_hash}"
        )
    temporary.replace(target)


def _download_with_resume(url: str, destination: Path) -> None:
    offset = destination.stat().st_size if destination.is_file() else 0
    request = urllib.request.Request(
        url,
        headers={"Range": f"bytes={offset}-"} if offset else {},
    )
    with urllib.request.urlopen(request) as response:
        partial = getattr(response, "status", None) == 206
        mode = "ab" if offset and partial else "wb"
        with destination.open(mode) as handle:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                handle.write(chunk)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
