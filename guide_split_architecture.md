# Guide Complet : Découpage, Split et Conversion des Bulletins DGCMEF

Ce guide documente la structure, la logique algorithmique et l'organisation des répertoires pour le traitement complet des Quotidiens DGCMEF : du **Macro-Split** jusqu'au **Micro-Split géométrique des avis**, avec conversion en **Markdown (.md)** et arborescence classée par jour.

---

## 1. Organisation Cible des Répertoires (Classé par Jour)

Chaque parution quotidienne est rangée dans une arborescence chronologique claire (`Année / Mois / Jour_Date`), garantissant que **chaque dossier correspond exactement à un jour de parution** :

```
telechargements_pdf_classes/
└── 2026/
    └── 10/
        ├── Jour_2026-10-21_N4514/
        │   ├── source/
        │   │   └── Quotidien_n4514.pdf                    # PDF complet du jour
        │   ├── 01_sections_pdf/                          # Sous-PDFs découpés par section (Niveau 1 & 2)
        │   │   ├── N4514-Avis-MIMOD-fournitures_et_services_courants.pdf
        │   │   ├── N4514-Avis-MIMOD-travaux.pdf
        │   │   ├── N4514-Avis-MIMOD-prestations_intellectuelles.pdf
        │   │   ├── N4514-Avis-Region-fournitures_et_services_courants.pdf
        │   │   ├── N4514-Avis-Region-travaux.pdf
        │   │   ├── N4514-Avis-Region-prestations_intellectuelles.pdf
        │   │   ├── N4514-Resultats-MIMOD.pdf
        │   │   └── N4514-Resultats-Region.pdf
        │   ├── 02_sections_md/                           # Conversion intégrale en Markdown de chaque section
        │   │   ├── N4514-Avis-MIMOD-fournitures_et_services_courants.md
        │   │   ├── N4514-Avis-MIMOD-travaux.md
        │   │   ├── N4514-Avis-MIMOD-prestations_intellectuelles.md
        │   │   ├── N4514-Avis-Region-fournitures_et_services_courants.md
        │   │   ├── N4514-Avis-Region-travaux.md
        │   │   ├── N4514-Avis-Region-prestations_intellectuelles.md
        │   │   ├── N4514-Resultats-MIMOD.md
        │   │   └── N4514-Resultats-Region.md
        │   └── 03_annonces_unitaires_md/                  # Micro-Split géométrique : 1 fichier .md par annonce
        │       ├── N4514_Avis_01_p32-p33_Acquisition_imprimantes_tickets.md
        │       ├── N4514_Avis_02_p33-p34_Acquisition_outils_foration.md
        │       └── ...
        └── Jour_2026-10-20_N4513/
            └── ...
```

---

## 2. Étape 1 : Le Macro-Split (Séparation AVIS vs RÉSULTATS)

Un bulletin standard compte de 40 à 120 pages et se divise en deux grandes parties : les **Résultats de dépouillements** et les **Avis d'appels d'offres**.

```
┌────────────────────────────────────────────────────────┐
│                  Sommaire (Page 2)                     │
│  RÉSULTATS DE DÉPOUILLEMENTS                           │
│    - Marchés des Ministères et Institutions ..... P. 5 │
│    - Marchés des Régions ........................ P. 22│
│  AVIS D'APPELS D'OFFRES                                │
│    - Ministères et Institutions (MIMOD)                │
│        * Fournitures et services courants ....... P. 32│
│        * Travaux ................................ P. 37│
│        * Prestations intellectuelles ............ P. 39│
│    - Régions et Collectivités                          │
│        * Fournitures ............................ P. 41│
│        * Travaux ................................ P. 42│
└────────────────────────────────────────────────────────┘
```

### Stratégie A (Prioritaire) : Analyse du Sommaire en Page 2
1. **Extraction de la page 2** du document.
2. **Parsing des sections et références** via l'expression régulière :
   ```python
   re.search(r'(.*?)\.?\b(?<!B\.)P\.\s*(\d+)', line, re.IGNORECASE)
   ```
   * Le préfixe négatif `(?<!B\.)` évite les faux positifs liés aux boîtes postales (*B.P. 7222*).
3. **Détection du contexte** :
   * **RÉSULTATS** : déclenché par les mots `RESULTATS` ou `DEPOUILLEMENTS`.
   * **AVIS** : déclenché par le mot `AVIS`.
4. **Détection de la macro-catégorie** :
   * `MIMOD` : ministères, institutions, maîtrises d'ouvrages déléguées.
   * `Region` : conseils régionaux, mairies, communes.
5. **Détection du type de marché** :
   * `fournitures_et_services_courants`
   * `travaux`
   * `prestations_intellectuelles`
6. **Calibration du Delta (Page imprimée vs Index réel PDF)** :
   * La page imprimée « P. 5 » correspond à l'index physique 4 (`index = page_imprimee - 1 + delta`).
   * L'alignement est vérifié en contrôlant l'en-tête de la page cible.

### Stratégie B (Repli) : Détection par Marqueurs Visuels
Si le sommaire est scanné ou absent :
* **Zone RÉSULTATS** : détectée par la présence de **barres noires transversales** (largeur `> 50%` de la page, hauteur `≥ 6 px`).
* **Zone AVIS** : détectée par la présence de **bandeaux colorés** (Cyan, Rouge, Jaune).

---

## 3. Étape 2 : Génération Physique des Sous-PDFs (Nomenclature Spécifique)

À partir des plages de pages délimitées, les sous-PDFs sont générés avec une convention de nommage claire et standardisée :

### Format des noms de fichiers générés :
* **Section Résultats :**
  * `N°[NUMERO]-Résultats-MIMOD.pdf`
  * `N°[NUMERO]-Résultats-Region.pdf`
* **Section Avis (par macro-secteur et type de marché) :**
  * `N°[NUMERO]-Avis-MIMOD-fournitures_et_services_courants.pdf`
  * `N°[NUMERO]-Avis-MIMOD-travaux.pdf`
  * `N°[NUMERO]-Avis-MIMOD-prestations_intellectuelles.pdf`
  * `N°[NUMERO]-Avis-Region-fournitures_et_services_courants.pdf`
  * `N°[NUMERO]-Avis-Region-travaux.pdf`
  * `N°[NUMERO]-Avis-Region-prestations_intellectuelles.pdf`

---

## 4. Étape 3 : Conversion Sectionnelle en Markdown (.md)

Chaque sous-PDF de section est converti en son équivalent Markdown portant exactement le même radical :
* `N°3827-Avis-MIMOD-fournitures_et_services_courants.pdf` ➔ `N°3827-Avis-MIMOD-fournitures_et_services_courants.md`
* `N°3827-Résultats-MIMOD.pdf` ➔ `N°3827-Résultats-MIMOD.md`

Cette étape permet une lecture textuelle rapide tout en préservant la structure des tableaux pour les résultats.

---

## 5. Étape 4 : Le Micro-Split des AVIS (Découpage Unitaire par Annonce)

Dans la zone AVIS, **une même page contient fréquemment 2 à 3 annonces distinctes** ou, à l'inverse, **une annonce s'étend sur 2 pages consécutives**.

### Logique Géométrique Déterministe (sans regex hasardeuse ni LLM)
Sur les Quotidiens DGCMEF, la charte graphique officielle utilise un **triplet de bandeaux colorés** :

```
┌────────────────────────────────────────────────────────┐
│ [BANDEAU ROUGE]  -> CATÉGORIE DU MARCHÉ                │  (ex: Fournitures et Services)
│ [BANDEAU JAUNE]  -> AUTORITÉ CONTRACTANTE              │  (ex: Université Joseph KI-ZERBO)
│ [BANDEAU CYAN]   -> DÉBUT D'ANNONCE & OBJET DU MARCHÉ  │  (ex: Acquisition de matériels informatiques)
├────────────────────────────────────────────────────────┤
│ Corps de l'annonce 1...                                │
│ Financement, caution, date limite...                   │
├────────────────────────────────────────────────────────┤
│ [BANDEAU CYAN]   -> DÉBUT ANNONCE 2                    │  (ex: Entretien des espaces verts)
│ Corps de l'annonce 2...                                │
└────────────────────────────────────────────────────────┘
```

1. **Identification par code couleur** :
   * **ROUGE** (`r > 0.75, g < 0.45, b < 0.45`) : Catégorie du marché.
   * **JAUNE** (`r > 0.70, g > 0.70, b < 0.50`) : Émetteur / Autorité contractante.
   * **CYAN** (`r < 0.60, g > 0.60, b > 0.60`) : **Point d'ancrage obligatoire ouvrant une annonce unitaire**.
2. **Délimitation géométrique** :
   * L'annonce démarre à la coordonnée verticale `bottom` du bandeau CYAN.
   * Elle s'étend jusqu'au bandeau CYAN suivant (même page ou pages suivantes).
   * Si aucun bandeau CYAN ne suit, elle s'arrête à la fin de la section.
3. **Nettoyage et exclusion** :
   * Les bas de page répétitifs (`www.dgcmef.gov.bf`, pagination isolée) sont filtrés sans altérer le texte métier.

### Format du fichier Markdown unitaire généré :
Chaque annonce est sauvegardée sous le format :
`N[NUMERO]_Avis_[INDEX]_p[DEBUT]-p[FIN]_[SLUG_OBJET].md`

Exemple de contenu avec frontmatter YAML complet :
```markdown
---
bulletin: "N°4514"
date_parution: "Mercredi 21 octobre 2026"
index_annonce: 1
page_debut: 32
page_fin: 33
categorie: "Fournitures et Services courants"
autorite_contractante: "BURKINA YIN WISGR META"
objet: "Acquisition de trois (03) imprimantes de tickets pour le stade du 4 août"
methode_decoupage: "geometrique_bandeaux_couleur"
---

# Avis N°01 — Acquisition de trois (03) imprimantes de tickets pour le stade du 4 août

- **Bulletin :** N°4514 (Mercredi 21 octobre 2026)
- **Pages d'origine :** Page 32 à 33
- **Catégorie :** Fournitures et Services courants
- **Autorité contractante :** BURKINA YIN WISGR META

---

### Texte Intégral de l'Annonce

Avis de demande de prix
N°2026-012/BYM/DG/PRCP
Financement : Budget BYM, Exercice 2026
Montant prévisionnel : 20 000 000 FCFA TTC
...
Date limite de dépôt : 30/10/2026 à 09 heures
```

---

## 6. Synthèse du Flux d'Exécution

```
                  [Quotidien N°XXXX.pdf]
                            │
               ┌────────────┴────────────┐
               ▼                         ▼
      [Page 2 : Sommaire]     [Pages suivantes : Marqueurs]
               │                         │
               └────────────┬────────────┘
                            │ Macro-Split
                            ▼
           ┌─────────────────────────────────┐
           │     Génération des Sous-PDFs    │
           │  (MIMOD / Région / Catégories)  │
           └────────────────┬────────────────┘
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
   [Sous-PDFs de Sections]       [Sous-MDs de Sections]
   - N°XXXX-Avis-...pdf          - N°XXXX-Avis-...md
   - N°XXXX-Resultats-...pdf     - N°XXXX-Resultats-...md
            │
            ▼
   [Micro-Split Géométrique AVIS]
   (Bandeaux Cyan, Jaune, Rouge)
            │
            ▼
   [Fichiers .md Unitaires]
   - N°XXXX_Avis_01_pX-pY.md
   - N°XXXX_Avis_02_pY-pZ.md
```

