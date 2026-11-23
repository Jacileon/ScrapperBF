"""
prod_pipeline — Package de production pour le traitement structuré des Bulletins DGCMEF.

Composants principaux :
- colors : Charte graphique officielle DGCMEF avec marges de tolérance colorimétrique.
- light_ocr : Repli OCR léger et détection de corruption de texte.
- macro_splitter : Macro-Split dual-stratégie (Sommaire p.2 avec auto-calibration + repli visuel).
- sections_generator : Découpage physique des sous-PDFs et conversion intégrale en Markdown (Avis & Résultats MIMOD / Régions).
- avis_micro_splitter : Découpage unitaire géométrique des AVIS (multi-annonces / page).
- daily_orchestrator : Orchestrateur unitaire journalier (1 dossier par jour de parution).
"""

__version__ = "2.0.0"
__author__ = "ScrapperBF Production Team"

