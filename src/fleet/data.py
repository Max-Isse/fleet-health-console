"""Download, verify and read the NASA C-MAPSS turbofan data."""

from __future__ import annotations

import hashlib
import io
import logging
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from fleet.config import config, settings

log = logging.getLogger(__name__)

SETTINGS = ["op_setting_1", "op_setting_2", "op_setting_3"]
SENSORS = [f"s{i}" for i in range(1, 22)]
COLUMNS = ["engine_id", "cycle", *SETTINGS, *SENSORS]
ARCHIVE_NAME = "cmapss_nasa.zip"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def raw_dir() -> Path:
    return settings().data_dir / "raw"


def fetch(force: bool = False) -> Path:
    """Download the archive once, check it against the pinned SHA-256 and extract the text files."""
    src = config()["source"]
    archive = raw_dir() / ARCHIVE_NAME
    archive.parent.mkdir(parents=True, exist_ok=True)
    if force or not archive.exists():
        log.info("downloading %s", src["url"])
        with urllib.request.urlopen(src["url"], timeout=300) as r:  # noqa: S310 - fixed official NASA URL
            archive.write_bytes(r.read())
    digest = _sha256(archive)
    if digest != src["archive_sha256"]:
        raise ValueError(f"archive checksum {digest} does not match the pinned {src['archive_sha256']}")
    out = raw_dir() / "cmapss"
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as outer:
        inner_name = next(n for n in outer.namelist() if n.endswith(src["inner_archive"]))
        inner = zipfile.ZipFile(io.BytesIO(outer.read(inner_name)))
    for name in inner.namelist():
        if name.endswith(".txt") and "/" not in name and ".." not in name:
            (out / name).write_bytes(inner.read(name))
    log.info("extracted C-MAPSS text files to %s", out)
    return out


def read_cmapss(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=r"\s+", header=None, names=COLUMNS)
    return df.astype({"engine_id": "int64", "cycle": "int64"})


def read_split(split: str, dataset: str | None = None) -> pd.DataFrame:
    dataset = dataset or config()["source"]["dataset"]
    return read_cmapss(raw_dir() / "cmapss" / f"{split}_{dataset}.txt")


def read_test_rul(dataset: str | None = None) -> pd.Series:
    dataset = dataset or config()["source"]["dataset"]
    values = pd.read_csv(raw_dir() / "cmapss" / f"RUL_{dataset}.txt", header=None).iloc[:, 0]
    values.index = pd.RangeIndex(1, len(values) + 1, name="engine_id")
    return values
