"""Stage 0: download AIS archives from NOAA Marine Cadastre.

Data index: https://coast.noaa.gov/htdata/CMSP/AISDataHandler/{year}/
Formats served per year: ``.zip`` (2009-2024, daily or zone archives) and
``.csv.zst`` (2025 onward).
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://coast.noaa.gov/htdata/CMSP/AISDataHandler/"
ARCHIVE_SUFFIXES = (".zip", ".csv.zst")
_CHUNK = 1 << 20  # 1 MiB

logger = logging.getLogger(__name__)


def parse_index_links(html: str, suffixes: tuple[str, ...] = ARCHIVE_SUFFIXES) -> list[str]:
    """Extract archive hrefs from a NOAA year index page."""
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if isinstance(href, str) and href.endswith(suffixes):
            links.append(href)
    return links


def list_year_archives(year: int, session: requests.Session | None = None) -> list[str]:
    """Return archive file names available for one year."""
    sess = session or requests.Session()
    response = sess.get(f"{BASE_URL}{year}/index.html", timeout=60)
    response.raise_for_status()
    return parse_index_links(response.text)


def download_year(
    year: int,
    dest_dir: Path,
    session: requests.Session | None = None,
    skip_existing: bool = True,
) -> list[Path]:
    """Download every archive of one year into ``dest_dir``.

    Files are prefixed with the queried year (``{year}_{name}``) so that
    multi-year downloads can share one directory. Returns downloaded paths.
    """
    sess = session or requests.Session()
    dest_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []

    for name in list_year_archives(year, session=sess):
        file_url = f"{BASE_URL}{year}/{name}"
        target = dest_dir / f"{year}_{Path(name).name}"
        if skip_existing and target.exists() and target.stat().st_size > 0:
            logger.info("Skipping existing %s", target.name)
            continue
        logger.info("Downloading %s -> %s", file_url, target)
        with sess.get(file_url, stream=True, timeout=300) as response:
            response.raise_for_status()
            with target.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=_CHUNK):
                    handle.write(chunk)
        downloaded.append(target)

    return downloaded


def download_range(
    start_year: int,
    end_year: int,
    dest_dir: Path,
    skip_existing: bool = True,
) -> list[Path]:
    """Download all archives for an inclusive year range."""
    session = requests.Session()
    downloaded: list[Path] = []
    for year in range(start_year, end_year + 1):
        downloaded.extend(download_year(year, dest_dir, session=session, skip_existing=skip_existing))
    return downloaded
