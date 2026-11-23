"""Tests unitaires pour pdf_downloader.py."""
from datetime import date
from pathlib import Path
import pdf_downloader as dl


def test_calibration_fallback(tmp_path):
    slope, max_num, max_ym = dl.load_calibration(tmp_path / "inexistant.txt")
    assert max_num == 4468
    assert max_ym == (2026, 8)
    assert round(slope, 1) == 21.7


def test_generate_catchup_wordlist():
    candidates = dl.generate_catchup_wordlist(4468, (2026, 8), date(2026, 10, 30))
    assert len(candidates) > 0
    # Vérifie que les patterns couvrent août, septembre et octobre
    assert any("2026-08" in u for u in candidates)
    assert any("2026-09" in u for u in candidates)
    assert any("2026-10" in u for u in candidates)
    # Vérifie qu'on teste bien les numéros attendus (ex: N°4505)
    assert any("4505" in u for u in candidates)


def test_filename_templates():
    names = [tpl(4505) for tpl in dl.FILENAME_TEMPLATES]
    assert "Quotidien N°4505.pdf" in names
    assert "Quotidien n°4505.pdf" in names


def test_check_only_no_download(tmp_path, monkeypatch):
    class MockResp:
        status_code = 200
        headers = {"Content-Type": "application/pdf"}

    class MockSession:
        def head(self, url, **kwargs):
            return MockResp()

    res = dl.check_and_download_url("https://dgcmef.gov.bf/test.pdf", MockSession(), tmp_path, check_only=True)
    assert res["ok"] is True
    assert res["downloaded"] is False
    # Vérifie qu'aucun fichier n'a été créé sur le disque
    assert list(tmp_path.glob("*")) == []
