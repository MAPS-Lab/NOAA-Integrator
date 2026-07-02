"""Tests for NOAA index parsing and download plumbing."""

from pathlib import Path

from noaa_integrator.download import download_year, parse_index_links

INDEX_HTML = """
<html><body>
<a href="AIS_2024_01_01.zip">AIS_2024_01_01.zip</a>
<a href="AIS_2024_01_02.zip">AIS_2024_01_02.zip</a>
<a href="ais_2025-01-01.csv.zst">ais_2025-01-01.csv.zst</a>
<a href="index.html">index</a>
<a href="../">up</a>
<a>no href</a>
</body></html>
"""


def test_parse_index_links_finds_zip_and_zst() -> None:
    links = parse_index_links(INDEX_HTML)
    assert links == ["AIS_2024_01_01.zip", "AIS_2024_01_02.zip", "ais_2025-01-01.csv.zst"]


def test_parse_index_links_suffix_filter() -> None:
    assert parse_index_links(INDEX_HTML, suffixes=(".csv.zst",)) == ["ais_2025-01-01.csv.zst"]


class _FakeResponse:
    def __init__(self, text: str = "", content: bytes = b"") -> None:
        self.text = text
        self._content = content

    def raise_for_status(self) -> None:
        pass

    def iter_content(self, chunk_size: int):
        yield self._content

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        pass


class _FakeSession:
    def __init__(self) -> None:
        self.requests: list[str] = []

    def get(self, url: str, **kwargs: object) -> _FakeResponse:
        self.requests.append(url)
        if url.endswith("index.html"):
            return _FakeResponse(text=INDEX_HTML)
        return _FakeResponse(content=b"archive-bytes")


def test_download_year_writes_prefixed_files(tmp_path: Path) -> None:
    session = _FakeSession()
    downloaded = download_year(2024, tmp_path, session=session)  # type: ignore[arg-type]

    names = sorted(path.name for path in downloaded)
    assert names == [
        "2024_AIS_2024_01_01.zip",
        "2024_AIS_2024_01_02.zip",
        "2024_ais_2025-01-01.csv.zst",
    ]
    for path in downloaded:
        assert path.read_bytes() == b"archive-bytes"


def test_download_year_skips_existing(tmp_path: Path) -> None:
    existing = tmp_path / "2024_AIS_2024_01_01.zip"
    existing.write_bytes(b"already-here")

    session = _FakeSession()
    downloaded = download_year(2024, tmp_path, session=session)  # type: ignore[arg-type]

    assert existing.read_bytes() == b"already-here"
    assert existing not in downloaded
    assert len(downloaded) == 2
