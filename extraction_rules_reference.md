# Guide & Règles Officielles d'Extraction des Avis de Marchés Publics (DGCMEF - Burkina Faso)

> **Document de Référence pour les Modèles d'Extraction LLM**  
> **Version :** 1.0 — Novembre 2026  
> **Format de sortie exigé :** Un objet JSON unique, valide, sans formatage Markdown superflu (sauf si demandé), respectant strictement le schéma ci-dessous.

---

## 1. Principes et Règles Fondamentales d'Extraction

1. **Règle d'Or anti-hallucination :**
   - Ne **jamais** inventer, déduire ou extrapoler une information absente du texte.
   - Si une information n'apparaît pas explicitement ou ne peut être formellement identifiée, assigner strictement la valeur `null` (qui sera interprétée comme `None`).

2. **Règle des Nombres et Montants :**
   - Tous les montants financiers (`budget_previsionnel_fcfa`, `garantie_soumission_fcfa`, `cout_acquisition_dossier_fcfa`) doivent être extraits sous forme **d'entiers numériques purs** (ex: `18923644` et non `"18 923 644 FCFA"`).
   - Les montants exprimés en lettres (ex: *"dix-huit millions neuf cent vingt-trois mille six cent quarante-quatre"*) doivent être convertis en chiffres ou récupérés depuis la mention entre parenthèses.

3. **Règle des Dates et Heures :**
   - Format de date standardisé : `JJ/MM/AAAA` (ex: `27/03/2026`).
   - Format d'heure : `HH:MM` ou texte explicite (ex: `"09:00 TU"`).

4. **Règle du Champ `remarque` (Signalement et Contrôle Qualité) :**
   Ce champ est **obligatoire**. Il permet au modèle de consigner son auto-évaluation sur la qualité de l'annonce :
   - `null` : Annonce claire, propre et complète sans aucune anomalie.
   - `"a verifier"` : Ambigüité sur un montant, une date ou un libellé contradictoire.
   - `"plusieurs valeurs non dispo"` : Plusieurs informations majeures (montant, date limite, caution) sont absentes de l'annonce.
   - `"double annonce sur la meme page"` : Le texte découpé contient visiblement deux avis distincts qui n'ont pas été séparés.
   - `"presence de metadonnees tableau"` : Présence de tableaux complexes, lignes de bordereaux de prix ou fragment d'un tableau récapitulatif.
   - *Autre remarque pertinente* : Description textuelle concise de toute particularité (ex: *"rectificatif / additif à un avis précédent"*, *"marché annulé / reporté"*).

---

## 2. Dictionnaire Détaillé des 28 Champs d'Extraction

### BLOC A : Identification & Métadonnées Générales

#### 1. `numero_bulletin`
- **Source :** En-tête YAML (`bulletin:`) ou texte du bas de page.
- **Règle :** Chaîne de caractères standardisée.
- **Exemple :** `"Quotidien N°4359"`

#### 2. `date_parution`
- **Source :** En-tête YAML (`date_parution:`) ou couverture/pied de page.
- **Règle :** Date complète en français.
- **Exemple :** `"Mercredi 18 mars 2026"`

#### 3. `pages`
- **Source :** En-tête YAML (`pages:`).
- **Règle :** Pagination officielle imprimée détectée.
- **Exemple :** `"p. 85"` ou `"p. 32 à 33"`

#### 4. `categorie_marche`
- **Source :** En-tête YAML (`categorie:`) ou Bandeau Rouge.
- **Valeurs admises :** `"Travaux"`, `"Fournitures et Services courants"`, `"Prestations intellectuelles"`.
- **Défaut :** `null` si non identifiable.

#### 5. `type_procedure`
- **Mots-clés déclencheurs :** `Avis de demande de prix`, `Appel d’offres ouvert`, `Appel d’offres restreint`, `Manifestation d’intérêt`, `Demande de cotation`.
- **Règle :** Libellé de la procédure officielle de passation.
- **Exemple :** `"Demande de prix"` ou `"Appel d’offres ouvert"`

#### 6. `reference_dossier`
- **Mots-clés déclencheurs :** `N° :`, `N°`, `Réf :`, `Dossier N°`, `du [Date]`.
- **Règle :** Référence administrative complète du dossier d'appel d'offres.
- **Exemple :** `"2026-16/MS/SG/CHR-G/DG/PRCP du 10/03/2026"`

#### 7. `autorite_contractante` (ou `autorite_emettrice`)
- **Source :** En-tête YAML (`autorite_contractante:`), Bandeau Jaune, et corps du texte.
- **Règle :** Extraire l'autorité contractante émettrice complète et précise, incluant la structure rattachée (ex: Ministère de tutelle + Direction/Établissement rattaché).
- **Exemple :** `"Ministère de la Santé - Service d’Aide Médicale Urgente (SAMU)"` ou `"CENTRE HOSPITALIER REGIONAL DE GAOUA"`

#### 8. `ministere_tutelle`
- **Mots-clés déclencheurs :** `Ministère de`, `Présidence du Faso`, `Primature`.
- **Règle :** Ministère de rattachement ou institution de tutelle s'il est mentionné.
- **Exemple :** `"Ministère de la Santé"`

---

### BLOC B : Objet du Marché & Allotissement

#### 9. `objet_marche`
- **Source :** En-tête YAML (`objet:`) ou Bandeau Cyan complété par le texte.
- **Règle :** Libellé exhaustif et fidèle de l'objet de la commande.
- **Exemple :** `"Acquisition d’équipements de protection individuelle au profit du Centre Hospitalier Régional de Gaoua"`

#### 10. `allotissement_type`
- **Mots-clés déclencheurs :** `lot: unique`, `en lot unique`, `décomposent en [N] lots`, `réparti en`.
- **Valeurs admises :** `"Lot unique"` ou `"Lots multiples"`.
- **Défaut :** `null` si non précisé.

#### 11. `nombre_lots`
- **Règle :** Nombre entier (`int`). `1` pour un lot unique, sinon le décompte des lots mentionnés.
- **Exemple :** `1` ou `3`

#### 12. `detail_lots`
- **Règle :** Tableau d'objets `[{"numero_lot": "Lot 1", "titre": "...", "description": "...", "montant_fcfa": null, "caution_fcfa": null}]`.
- **Détails exigés :**
  - Si plusieurs lots existent, extraire impérativement chaque lot avec son intitulé complet, son budget prévisionnel ou prix estimé si précisé, et sa caution spécifique.
  - Si lot unique sans décomposition financière, mettre une liste vide `[]`.
- **Exemple multi-lots :**
  ```json
  [
    {
      "numero_lot": "Lot 1",
      "titre": "Fourniture de groupes électrogènes",
      "description": "Acquisition et installation de 2 groupes 100 kVA",
      "montant_fcfa": 25000000,
      "caution_fcfa": 500000
    },
    {
      "numero_lot": "Lot 2",
      "titre": "Fourniture de kits solaires",
      "description": "Installation de panneaux solaires",
      "montant_fcfa": 15000000,
      "caution_fcfa": 300000
    }
  ]
  ```

---

### BLOC C : Données Financières & Garanties

#### 13. `budget_previsionnel_fcfa`
- **Mots-clés déclencheurs :** `budget prévisionnel est de`, `enveloppe prévisionnelle`, `montant prévisionnel`, `francs CFA TTC`, `francs CFA HT`.
- **Règle :** Montant en nombre entier pur sans devise.
- **Exemple :** `20000000`

#### 14. `garantie_soumission_fcfa`
- **Mots-clés déclencheurs :** `garantie de soumission d’un montant`, `caution de soumission`, `caution bancaire`, `déclaration de garantie ou d’une garantie financière d’un montant`.
- **Règle :** Extraire le montant numérique entier pur en FCFA. Si la garantie est sous forme de simple déclaration sans montant chiffré, noter `"Déclaration de garantie"` ou `0`.
- **Exemple réel :** *"garantie de soumission sous la forme d’une déclaration de garantie ou d’une garantie financière d’un montant Deux millions (2 000 000) francs CFA"* -> `2000000`

#### 15. `cout_acquisition_dossier_fcfa`
- **Mots-clés déclencheurs :** `montant non remboursable de`, `somme non remboursable`, `coût d’acquisition`, `retirer [...] à la caisse`.
- **Règle :** Montant en nombre entier pur des frais de retrait du DAO.
- **Exemple :** `30000`

#### 16. `source_financement`
- **Mots-clés déclencheurs :** `Financement :`, `Budget de`, `Fonds propres`, `Ressources propres`, `Banque Mondiale`, `BAD`, `Coopération`.
- **Règle :** Origine des crédits alloués au marché.
- **Exemple :** `"Budget du CHR de Gaoua"`

#### 17. `exercice_budgetaire`
- **Mots-clés déclencheurs :** `exercice [AAAA]`, `gestion [AAAA]`.
- **Règle :** Année budgétaire sous forme de chaîne ou d'entier.
- **Exemple :** `"2026"`

---

### BLOC D : Calendrier, Délais & Procédure de Dépôt

#### 18. `date_limite_depot`
- **Mots-clés déclencheurs :** `avant le [Date]`, `au plus tard le [Date]`, `devront parvenir [...] avant le`.
- **Règle :** Format standardisé `JJ/MM/AAAA`.
- **Exemple :** `"27/03/2026"`

#### 19. `heure_limite_depot`
- **Mots-clés déclencheurs :** `à [HH] heures [MM] minute TU`, `à [HH]h[MM]`, `heures TU`.
- **Règle :** Heure limite de remise des offres.
- **Exemple :** `"09:00 TU"`

#### 20. `delai_execution_jours`
- **Mots-clés déclencheurs :** `délai d’exécution du contrat est de`, `délai de livraison est de`.
- **Règle :** Entier représentant le nombre de jours (convertir si mentionné en mois : 1 mois = 30 jours, 2 mois = 60 jours, ou laisser en texte si ambigu).
- **Exemple :** `45`

#### 21. `delai_validite_offres_jours`
- **Mots-clés déclencheurs :** `resteront engagés par leurs offres pour un délai de`, `délai de validité des offres`.
- **Règle :** Entier représentant le nombre de jours de validité de l'offre.
- **Exemple :** `60` ou `90`

#### 22. `lieu_depot_offres`
- **Mots-clés déclencheurs :** `remises à l’adresse suivante :`, `remises au secrétariat de`, `Direction Générale`, `bureau de la Personne Responsable de la Commande Publique`, `service courrier`.
- **Règle :** Extraire l'adresse ou bureau exact de dépôt mentionné.
- **Exemple réel :** *"remises à l’adresse suivante : bureau de la Personne Responsable de la Commande Publique sis à la Direction Générale du SAMU"*

#### 23. `date_heure_ouverture_plis`
- **Mots-clés déclencheurs :** `ouverture des plis sera faite immédiatement`, `le [Date] à [Heure]`.
- **Règle :** Date et heure de la séance d'ouverture.
- **Exemple :** `"27/03/2026 à 09:00 TU"`

#### 24. `lieu_ouverture_plis`
- **Mots-clés déclencheurs :** `salle de réunion`, `dans les bureaux de`, `à la direction`.
- **Règle :** Lieu précis de tenue de la commission d'ouverture des offres.
- **Exemple :** `"Salle de réunion de la Direction Générale"`

---

### BLOC E : Conditions Particulières, Contacts & Remarques

#### 25. `marche_reserve`
- **Mots-clés déclencheurs :** `marché réservé aux`, `exclusivement réservé aux PME`, `moyennes entreprises`, `artisans`.
- **Règle :** Description de la restriction d'accès aux soumissionnaires, ou `null` si ouvert à tous.
- **Exemple :** `"Réservé aux moyennes entreprises"` ou `"Réservé aux PME"`

#### 26. `qualifications_ou_agrement`
- **Mots-clés déclencheurs :** `Les exigences en matière de qualifications sont :`, `Voir Données Particulières de l’Appel d’Offres (DPAO)`, `agrément technique`, `qualification requise`.
- **Règle :** Conditions techniques préalables ou renvoi aux documents contractuels.
- **Exemple réel :** *"Voir Données Particulières de l’Appel d’Offres (DPAO) pour les informations détaillées"* ou *"Agrément technique BTP catégorie B"*

#### 27. `contacts_renseignements`
- **Mots-clés déclencheurs :** `Les candidats intéressés peuvent obtenir des informations auprès de`, `Secrétariat Exécutif de`, `BP `, `Tel `, `Tél :`, `E-mail :`, `Email :`.
- **Règle :** Coordonnées exhaustives (lieu, BP, téléphone, email) pour obtenir des renseignements ou consulter le DAO.
- **Exemple réel :** *"Secrétariat Exécutif de l’ARCEP sise à OUAGA 2000 BP 6437 Ouaga 01, TEL : 00 226 25 37 53 60"*

#### 28. `signataire_nom_fonction`
- **Mots-clés déclencheurs :** `Le Président de la Commission d’attribution des marchés`, `Directeur Général`, `Personne responsable de la commande publique`.
- **Règle :** Nom et titre de l'autorité signataire en bas de l'annonce.
- **Exemple réel :** *"Le Président de la Commission d’attribution des marchés / Assane TRAORE"*

#### 29. `remarque` *(CHAMP DE CONTRÔLE QUALITÉ & INFORMATIONS PERTINENTES HORS-RÈGLES)*
- **Rôle double :**
  1. **Audit qualité standard :** `null` (si parfait), `"a verifier"`, `"plusieurs valeurs non dispo"`, `"double annonce sur la meme page"`, `"presence de metadonnees tableau"`.
  2. **Capture d'informations précieuses non prévues dans les autres champs :** Toute clause ou précision majeure présente dans le texte (ex: *"Séance d'information préalable obligatoire le 10/11/2026"*, *"Paiement par virement bancaire uniquement"*, *"Dossier consultable gratuitement en ligne"*).

---

## 3. Schéma JSON de Référence (Template de sortie)

```json
{
  "numero_bulletin": "Quotidien N°4359",
  "date_parution": "Mercredi 18 mars 2026",
  "pages": "p. 85",
  "categorie_marche": "Fournitures et Services courants",
  "type_procedure": "Demande de prix",
  "reference_dossier": "2026-16/MS/SG/CHR-G/DG/PRCP du 10/03/2026",
  "autorite_contractante": "CENTRE HOSPITALIER REGIONAL DE GAOUA",
  "ministere_tutelle": "Ministère de la Santé",
  "objet_marche": "Acquisition d’équipements de protection individuelle au profit du Centre Hospitalier Régional de Gaoua",
  "allotissement_type": "Lot unique",
  "nombre_lots": 1,
  "detail_lots": [],
  "budget_previsionnel_fcfa": 20000000,
  "garantie_soumission_fcfa": 600000,
  "cout_acquisition_dossier_fcfa": 30000,
  "source_financement": "Budget du CHR de Gaoua",
  "exercice_budgetaire": "2026",
  "date_limite_depot": "27/03/2026",
  "heure_limite_depot": "09:00 TU",
  "delai_execution_jours": 45,
  "delai_validite_offres_jours": 60,
  "lieu_depot_offres": "Secrétariat de la Direction Générale du Centre Hospitalier Régional de Gaoua, BP 167",
  "date_heure_ouverture_plis": "27/03/2026 à 09:00 TU",
  "lieu_ouverture_plis": "Salle de réunion de la Direction Générale",
  "marche_reserve": "Réservé aux moyennes entreprises",
  "qualifications_ou_agrement": null,
  "contacts_renseignements": "BP 167 Gaoua, Tel: 61 34 90 92, Email: traoreassane90@gmail.com",
  "signataire_nom_fonction": "Assane TRAORE, Administrateur des services de santé (Président CAM)",
  "remarque": null
}
```
