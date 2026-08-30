"""Install pinned, license-reviewed Pose V6.7 temporal expert artifacts.

Model files and upstream sources live under the gitignored ``worker/models``
tree. The script never downloads at worker runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import urllib.request
from pathlib import Path


TAR_REPOSITORY = "https://github.com/zgspose/TARViTPose.git"
TAR_REVISION = "42164c2c789a5297544dd836846e509459b0f1f3"
TAR_CHECKPOINT_ID = "1mn-P-5bDa0OrM4ctc8PYrMuh40o3l-8J"
TAR_CHECKPOINT_BYTES = 1_619_532_723
TAR_CHECKPOINT_SHA256 = "89387c8aded9044471163ae52f2ec970c23ccd7f6c7fff5f47dd6cdb33e87c47"
TAP_REPOSITORY = "https://github.com/google-deepmind/tapnet.git"
TAP_REVISION = "c2cbab81cc06092b5f05bfe2da7bfec54e2079c9"
TAP_CHECKPOINT_URL = (
    "https://storage.googleapis.com/gresearch/tapnextpp/tapnextpp_512.ckpt"
)
TAP_CHECKPOINT_BYTES = 2_532_283_010
TAP_CHECKPOINT_SHA256 = "6cd0e793fdcface3063d63f8ed3819bcf74c2c0468fe1fef85acee4de2f3609f"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install official Apache-2.0 TAR-ViTPose and TAPNext++ artifacts",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    root = repository / "worker" / "models" / "temporal"
    sources = root / "sources"
    tar_source = sources / "TARViTPose"
    tap_source = sources / "tapnet"
    _clone_pinned(TAR_REPOSITORY, TAR_REVISION, tar_source, force=args.force)
    _clone_pinned(TAP_REPOSITORY, TAP_REVISION, tap_source, force=args.force)

    tar_target = root / "tar-vitpose" / "tarvitpose_b_17.pt"
    if args.force or not _complete(tar_target, TAR_CHECKPOINT_BYTES, TAR_CHECKPOINT_SHA256):
        try:
            import gdown
        except ImportError as error:
            raise RuntimeError(
                "Install worker/requirements-temporal-experts.txt before downloading TAR"
            ) from error
        tar_target.parent.mkdir(parents=True, exist_ok=True)
        temporary = tar_target.with_suffix(".pt.part")
        gdown.download(
            id=TAR_CHECKPOINT_ID, output=str(temporary), quiet=False, resume=True,
        )
        _promote(temporary, tar_target, TAR_CHECKPOINT_BYTES, TAR_CHECKPOINT_SHA256)

    tap_target = root / "tapnextpp" / "tapnextpp_512.ckpt"
    if args.force or not _complete(tap_target, TAP_CHECKPOINT_BYTES, TAP_CHECKPOINT_SHA256):
        tap_target.parent.mkdir(parents=True, exist_ok=True)
        temporary = tap_target.with_suffix(".ckpt.part")
        _download_with_resume(TAP_CHECKPOINT_URL, temporary)
        _promote(temporary, tap_target, TAP_CHECKPOINT_BYTES, TAP_CHECKPOINT_SHA256)

    for name, path in (("TAR", tar_target), ("TAPNext++", tap_target)):
        print(f"{name}: {path} bytes={path.stat().st_size} sha256={_sha256(path)}")
    return 0


def _clone_pinned(url: str, revision: str, target: Path, *, force: bool) -> None:
    if target.is_dir():
        current = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if current != revision:
            raise RuntimeError(f"unexpected upstream revision in {target}: {current}")
        return
    if target.exists():
        raise RuntimeError(f"refusing to overwrite existing path: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--filter=blob:none", url, str(target)], check=True)
    subprocess.run(["git", "-C", str(target), "checkout", "--detach", revision], check=True)


def _complete(path: Path, expected_bytes: int, expected_sha256: str) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == expected_bytes
        and _sha256(path) == expected_sha256
    )


def _promote(
    temporary: Path,
    target: Path,
    expected_bytes: int,
    expected_sha256: str,
) -> None:
    if not temporary.is_file() or temporary.stat().st_size != expected_bytes:
        actual = temporary.stat().st_size if temporary.exists() else 0
        raise RuntimeError(
            f"artifact size mismatch for {target.name}: {actual} != {expected_bytes}"
        )
    actual_hash = _sha256(temporary)
    if actual_hash != expected_sha256:
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
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
