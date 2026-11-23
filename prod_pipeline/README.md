# Package de Production — DGCMEF Bulletins Pipeline (`prod_pipeline/`)

Ce dossier contient les modules certifiés pour la mise en production du découpage et de la structuration journalière des Bulletins Quotidiens de la DGCMEF (Direction Générale du Contrôle des Marchés Publics et des Engagements Financiers du Burkina Faso).

---

## 1. Charte Couleur Officielle DGCMEF & Tolérances (`colors.py`)

Les PDFs administratifs burkinabè présentent des variations colorimétriques liées aux conversions CMYK/RGB et aux artefacts de compression. Le module `colors.py` intègre des marges de tolérance pour garantir une détection robuste à 100% :

| Rôle Structurel | Composante Visuelle | Couleur Nominale | Espaces Supportés | Marges de Tolérance |
| :--- | :--- | :--- | :--- | :--- |
| **NOIR** | Cadre émetteur (Résultats) | `#000000` | RGB, Grayscale, CMYK | Intensité globale $< 0.18$ ($< 46$ sur 255) ou $K > 0.80$ |
| **ORANGE / OR** | Séparateur de lots (Résultats) | `#FF8C00` / `#FFA500` | RGB, CMYK | $R > 0.70$, $0.35 \le G \le 0.95$, $B < 0.70$, $R - B \ge 0.18$ |
| **ROUGE** | Bandeau Catégorie (Avis) | `#C00000` / `#FF0000` | RGB, CMYK | $R > 0.65$, $G < 0.55$, $B < 0.55$, $R - G \ge 0.18$, $R - B \ge 0.18$ |
| **JAUNE** | Bandeau Émetteur (Avis) | `#FFFF00` / `#FFC000` | RGB, CMYK | $R > 0.65$, $G > 0.60$, $B < 0.55$, $(R-B) \ge 0.20$, $(G-B) \ge 0.20$ |
| **CYAN / BLEU** | Bandeau Objet (Avis) | `#00B0F0` / `#0000FF` | RGB, CMYK | Soit Cyan ($R < 0.65, G > 0.45, B > 0.45, B-R \ge 0.15$), soit Bleu pur ($B > 0.55$) |

- **Filtres géométriques :**
  - Largeur minimale : 20% à 30% de la page (élimine les puces et lettrines).
  - Hauteur : entre 4 px et 90 px (élimine les filets décoratifs fins et bordures de pleine page).
  - Déduplication verticale Y : fusionne les rectangles doubles (contour + remplissage).

---

## 2. Macro-Split de la Section RÉSULTATS

La section RÉSULTATS est découpée et conservée au niveau macro :
1. **Niveau Macro Sous-PDFs (`01_sections_pdf/`) :**
   - `Resultats-MIMOD` : Ministères, Institutions et Maîtrises d'ouvrages déléguées.
   - `Resultats-Region` : Régions et Collectivités territoriales (mairies, communes, conseils régionaux).
2. **Niveau Macro Markdown (`02_sections_md/`) :**
   - `N°XXXX-Resultats-MIMOD.md` : Transcription complète avec préambules et tableaux structurés Markdown de tous les ministères et institutions.
   - `N°XXXX-Resultats-Region.md` : Transcription complète avec préambules et tableaux structurés Markdown de toutes les régions.

---

## 3. Nomenclature et Arborescence par Jour de Parution

Chaque bulletin quotidien traité génère un dossier unique rangé par Année, Mois et Semaine ISO :

```text
telechargements_pdf_classes/
└── 2026/
    └── 10/
        └── Semaine_43/
            └── Jour_2026-10-21_N4514/
                ├── source/
                │   └── Quotidien n°4514.pdf
                ├── 01_sections_pdf/
                │   ├── N°4514-Avis-MIMOD-fournitures_et_services_courants.pdf
                │   ├── N°4514-Avis-MIMOD-prestations_intellectuelles.pdf
                │   ├── N°4514-Avis-MIMOD-travaux.pdf
                │   ├── N°4514-Avis-Region-fournitures_et_services_courants.pdf
                │   ├── N°4514-Resultats-MIMOD.pdf
                │   └── N°4514-Resultats-Region.pdf
                ├── 02_sections_md/
                │   ├── N°4514-Avis-MIMOD-fournitures_et_services_courants.md
                │   ├── N°4514-Avis-MIMOD-prestations_intellectuelles.md
                │   ├── N°4514-Avis-MIMOD-travaux.md
                │   ├── N°4514-Avis-Region-fournitures_et_services_courants.md
                │   ├── N°4514-Resultats-MIMOD.md
                │   └── N°4514-Resultats-Region.md
                ├── 03_avis/
                │   ├── N4514_avis_001_Fournitures_et_services_courants_Acquisition_de_materiel.md
                │   └── ... (annonces unitaires découpées géométriquement avec frontmatter YAML)
                └── rapport_traitement.json
```

---

## 4. Utilisation du CLI de Production

### Traiter un bulletin unique :
```bash
python prod_pipeline/cli.py --file "telechargements_pdf/Quotidien n°4514.pdf"
```

### Traiter tous les bulletins en parallèle :
```bash
python prod_pipeline/cli.py --dir "telechargements_pdf" --workers 4
```

### Forcer le re-traitement avec limitation :
```bash
python prod_pipeline/cli.py --dir "telechargements_pdf" --limit 10 --force
```

