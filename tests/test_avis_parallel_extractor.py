"""Tests unitaires pour avis_parallel_extractor.py (file d'attente et retry dynamique)."""
from pathlib import Path
import avis_parallel_extractor as ape


def test_load_rules():
    rules = ape.load_rules()
    assert "RÈGLES D'EXTRACTION DES AVIS" in rules
    assert "SCHÉMA JSON ATTENDU" in rules
    assert "autorite_emettrice" in rules


def test_extractor_queue_and_retry(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    extractor = ape.AvisParallelExtractor("mock rules", out_dir)

    # Création de faux fichiers markdown
    f1 = tmp_path / "annonce_1.md"
    f1.write_text("Texte annonce 1", encoding="utf-8")
    extractor.add_announcement_file(f1)

    assert extractor.total_tasks == 1
    assert not extractor.task_queue.empty()

    # Simulation d'un appel échoué une première fois puis réussi
    calls = []

    def mock_call(provider, rules, prompt):
        calls.append(provider["model"])
        if len(calls) == 1:
            raise RuntimeError("Mock 429 RateLimit")
        return {"objet": "Test réussi", "autorite_emettrice": "Ministère Test"}

    monkeypatch.setattr(ape, "call_llm_api", mock_call)

    # Worker unique
    prov = {"kind": "openrouter", "model": "mock-model", "api_key": "dummy"}
    extractor.worker_loop(prov)

    # L'annonce a bien été extraite après son retour dans la queue
    assert extractor.completed_tasks == 1
    assert len(extractor.results) == 1
    assert extractor.results[0]["objet"] == "Test réussi"
