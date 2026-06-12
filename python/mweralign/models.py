"""
Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

On-demand download of the pre-trained, character-preserving (identity
normalization) SentencePiece models used for tokenized alignment.

The models are published as individual assets on a GitHub Release, so the
package itself stays small. A model is fetched the first time it is requested,
verified against a known SHA-256 checksum, and cached on disk for reuse.

Resolution order for the cache directory:
  1. ``$MWERALIGN_SPM_DIR`` if set (also where reproduction users put models
     copied from the cluster);
  2. ``$XDG_CACHE_HOME/mweralign/models`` if ``XDG_CACHE_HOME`` is set;
  3. ``~/.cache/mweralign/models``.
"""

import hashlib
import logging
import os
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("mweralign")

# GitHub Release that hosts the SPM model assets.
_REPO = "mjpost/mweralign"
RELEASE_TAG = "spm-models-v1"
_BASE_URL = f"https://github.com/{_REPO}/releases/download/{RELEASE_TAG}"

# Canonical model name -> SHA-256 of the corresponding ``<name>.model`` asset.
# The name is also the ``-m``/``--tokenizer`` value and the cached filename.
MODELS: Dict[str, str] = {
    "spm32k": "bdf64c0ad08e9514f8aa174294756c3230c950315d8b4369a79ec1176aa2dad8",
    "spm64k": "2ccc4fd82d0ee0ff0956745911e26c7703ef7474b1196a5d000affebe42b48c2",
    "spm128k": "9abd430f20af65b9bacd9905c4651f1c48ecbdf2d3e73c8f7c9a7a191d02273e",
    "spm256k": "7d8fd4d5ea33e63f8b7407ddbf6088ef5a52e6b059e578d023fc5a093d56914e",
}

# Friendly shorthand: ``spm`` defaults to 256k, matching the experiment harness.
ALIASES: Dict[str, str] = {
    "spm": "spm256k",
}


def is_model_name(name: str) -> bool:
    """True if ``name`` is a known model name or alias (e.g. ``spm32k``)."""
    return name in MODELS or name in ALIASES


def cache_dir() -> Path:
    """Directory where downloaded models are stored (created on demand)."""
    env = os.environ.get("MWERALIGN_SPM_DIR")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "mweralign" / "models"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    """Download ``url`` to ``dest`` atomically (temp file + rename)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent), suffix=".part")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out:
            with urllib.request.urlopen(url) as resp:  # nosec B310 - fixed https GitHub URL
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    out.write(chunk)
        tmp.replace(dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def model_path(name: str, download: bool = True) -> Path:
    """Return the local path to the identity SPM model ``name`` (e.g. ``spm32k``).

    Downloads and verifies the model into the cache directory if it is not
    already present (when ``download`` is True).
    """
    name = ALIASES.get(name, name)
    if name not in MODELS:
        raise ValueError(
            f"Unknown SPM model {name!r}; "
            f"available: {sorted(MODELS)}"
        )

    filename = f"{name}.model"
    expected = MODELS[name]

    # Prefer an existing copy in the cache dir (or MWERALIGN_SPM_DIR).
    cached = cache_dir() / filename
    if cached.exists():
        return cached

    if not download:
        raise FileNotFoundError(
            f"SPM model {filename} not found at {cached} and download=False."
        )

    url = f"{_BASE_URL}/{filename}"
    logger.info("Downloading SPM model %s -> %s", url, cached)
    _download(url, cached)

    actual = _sha256(cached)
    if actual != expected:
        cached.unlink(missing_ok=True)
        raise RuntimeError(
            f"Checksum mismatch for {filename}: expected {expected}, got "
            f"{actual}. The download may be corrupt or the release asset "
            f"changed."
        )
    return cached


def resolve(name_or_path: str, download: bool = True) -> str:
    """Resolve a ``-m``/``--tokenizer`` value to a usable model path.

    If ``name_or_path`` is a known alias (e.g. ``spm32k``) the corresponding
    model is fetched/cached and its local path returned. Otherwise the value is
    returned unchanged so existing filesystem paths keep working.
    """
    if is_model_name(name_or_path):
        return str(model_path(name_or_path, download=download))
    return name_or_path


def download_all(download: bool = True) -> Dict[str, Path]:
    """Fetch every known model into the cache; returns {name: path}."""
    return {name: model_path(name, download=download) for name in MODELS}


def main(argv: Optional[list] = None) -> int:
    """CLI: ``python -m mweralign.models [--all | NAME ...]``."""
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Download the pre-trained identity SPM models used for "
                    "tokenized alignment."
    )
    parser.add_argument(
        "names", nargs="*", metavar="NAME",
        help=f"Models to fetch ({', '.join([*MODELS, *ALIASES])}). Default: all.",
    )
    parser.add_argument("--all", action="store_true", help="Fetch all models.")
    args = parser.parse_args(argv)

    try:
        if args.all or not args.names:
            paths = download_all()
            for name, p in paths.items():
                print(f"{name}: {p}")
        else:
            for name in args.names:
                if not is_model_name(name):
                    print(f"unknown model '{name}'; choices: {', '.join([*MODELS, *ALIASES])}",
                          file=sys.stderr)
                    return 2
                print(f"{name}: {resolve(name)}")
    except (RuntimeError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
