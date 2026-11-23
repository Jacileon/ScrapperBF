# Architecture et Guide du Pipeline de Lecture Unitaire : `reader_core`

Ce document présente la conception et l'implémentation du nouveau package autonome [reader_core/](file:///c:/Users/DANIEL/Documents/Mes%20projets/ScrapperBF/reader_core) destiné à traiter les Quotidiens DGCMEF **un à un** avec un découpage déterministe et robuste sans regex hasardeuse ni hallucinations.

---

## 1. Vue d'ensemble du Pipeline

```
[Quotidien DGCMEF.pdf]
          │
          ▼
┌────────────────────────────────────────────────────────┐
│  NIVEAU 1 : MACRO-SPLIT (macro_splitter.py)            │
│  - Stratégie A : Sommaire page 2 (regex p.XX + delta)  │
│  - Stratégie B : Marqueurs visuels (barres & couleurs) │
└──────────────────────────┬─────────────────────────────┘
                           │  Plages (AVIS & RÉSULTATS)
                           ▼
┌────────────────────────────────────────────────────────┐
│  NIVEAU 2 : SOUS-PDFs DE ZONES (zone_pdf_generator.py) │
│  - [N°XXXX]_Zone_RESULTATS_pX_pY.pdf                   │
│  - [N°XXXX]_Zone_AVIS_pA_pB.pdf                        │
│  - Sous-PDFs par famille : Travaux, Fournitures...     │
└──────────────────────────┬─────────────────────────────┘
                           │  Zone AVIS isolée
                           ▼
┌────────────────────────────────────────────────────────┐
│  NIVEAU 3 : MICRO-SPLIT DES AVIS (avis_micro_splitter) │
│  - Bandeau ROUGE  -> Catégorie (Travaux/Fournitures...)│
│  - Bandeau JAUNE  -> Émetteur (Autorité contractante)  │
│  - Bandeau CYAN   -> Début d'Annonce                   │
│  - Découpage texte géométrique entre les boîtes        │
│  - Export d'un fichier .md par annonce unitaire        │
└────────────────────────────────────────────────────────┘
```

---

## 2. Détail des Modules Créés

### A. Niveau 1 : Macro-Split ([reader_core/macro_splitter.py](file:///c:/Users/DANIEL/Documents/Mes%20projets/ScrapperBF/reader_core/macro_splitter.py))
* **Stratégie A (Prioritaire - Lecture du Sommaire imprimé) :**
  * Localisation automatique du sommaire en page 2 (index 1).
  * Extraction des références de pages avec l'expression `r"(?<!b\.)\bp\.?\s*(\d{1,4})\b"` pour isoler le début et la fin des sections *« RÉSULTATS »* et *« AVIS »*.
  * Calibration dynamique du décalage (delta) entre le numéro de page imprimé et l'index physique 0-based du document PDF.
* **Stratégie B (Repli automatique) :**
  * Détection des **barres noires / bannières transversales** de largeur `> 50%` de la page pour la zone RÉSULTATS.
  * Détection des **bandeaux colorés** (Cyan, Rouge, Jaune, Magenta) pour la zone AVIS.

### B. Niveau 2 : Génération physique des sous-PDFs ([reader_core/zone_pdf_generator.py](file:///c:/Users/DANIEL/Documents/Mes%20projets/ScrapperBF/reader_core/zone_pdf_generator.py))
* Découpage sans perte via `pypdfium2`.
* Nomenclature rigoureuse :
  * Zone Résultats : `{numero}_Zone_RESULTATS_p{debut}_p{fin}.pdf`
  * Zone Avis Global : `{numero}_Zone_AVIS_p{debut}_p{fin}.pdf`
  * Sous-familles d'avis :
    * `{numero}_AVIS_Fournitures_et_Services.pdf`
    * `{numero}_AVIS_Travaux.pdf`
    * `{numero}_AVIS_Prestations_Intellectuelles.pdf`

### C. Niveau 3 : Micro-Split des Avis ([reader_core/avis_micro_splitter.py](file:///c:/Users/DANIEL/Documents/Mes%20projets/ScrapperBF/reader_core/avis_micro_splitter.py))
* **Détection géométrique sans regex :**
  * **ROUGE** : Catégorie normalisée du marché.
  * **JAUNE** : Autorité contractante émettrice.
  * **CYAN** : Objet du marché et début officiel de l'avis.
* **Gestion multi-annonces par page :** Permet d'isoler 2 à 3 annonces distinctes présentes sur une même page.
* **Sortie Markdown unitaire :**
  * Nommage clair : `{numero}_Avis_{index:02d}_p{debut}-p{fin}_{slug_objet}.md`
  * En-tête YAML frontmatter avec métadonnées structurelles (`bulletin`, `date_parution`, `categorie`, `autorite_contractante`, `objet`, `page_debut`, `page_fin`).
  * Corps textuel nettoyé des mentions résiduelles de pagination.

### D. Orchestrateur Global ([reader_core/pdf_reader_pipeline.py](file:///c:/Users/DANIEL/Documents/Mes%20projets/ScrapperBF/reader_core/pdf_reader_pipeline.py))
* Point d'entrée exécutable en ligne de commande ou importable en Python pour traiter n'importe quel bulletin individuel.
* Produit un bilan synthétique au format JSON `{numero}_bilan_decoupage.json`.

---

## 3. Exemple d'Utilisation

### En ligne de commande :
```bash
python reader_core/pdf_reader_pipeline.py "telechargements_pdf/Quotidien n°4514.pdf" --out-dir output_bulletins
```

### En code Python :
```python
from reader_core.pdf_reader_pipeline import process_single_pdf

rapport = process_single_pdf(
    pdf_path="telechargements_pdf/Quotidien n°4514.pdf",
    output_root="output_bulletins"
)
print("Nombre d'avis extraits :", rapport["total_annonces_avis"])
```
