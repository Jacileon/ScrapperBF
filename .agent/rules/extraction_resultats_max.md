# Règle d'extraction maximale des résultats (DGCMEF)

Pour chaque fichier `.md` de résultats traité par un agent cognitif ou extracteur, extraire **le maximum d'informations** sans omission ni résumé réducteur :

1. **En-tête du marché (`resultats_marches`)** :
   - `bulletin` : numéro exact (ex. `Quotidien N°4306(bis)`).
   - `date_parution` : date complète incluant le jour, le mois et l'année (ex. `Vendredi 02 janvier 2026`).
   - `reference_dossier` : numéro complet du marché / DAO / DC / DP / AMI (ex. `N°2025-012/MESFPT/SG/DAMP`).
   - `objet` : titre complet et exact du marché.
   - `autorite_contractante` : ministère, région, commune, établissement ou projet.
   - `secteur_activite`, `financement` (budget national, bailleur, etc.), `methode_selection`, `score_technique_min_requis`.
   - `date_depouillement`, `date_deliberation`, `budget_previsionnel_min_fcfa`, `budget_previsionnel_max_fcfa`.
   - `est_rectificatif` et `decision_arcop_ref` (si rectificatif ou décision ARCOP / recours mentionné).

2. **Détails de chaque lot (`resultats_lots`)** :
   - `numero_lot`, `intitule_lot`, `nombre_plis_recus`.
   - `budget_lot_min_fcfa`, `budget_lot_max_fcfa`, `moyenne_offres_fcfa`, `borne_inf_basse_fcfa`, `seuil_tolerance_5pct_fcfa`, `borne_sup_elevee_fcfa`.
   - `attributaire_nom` : **toujours renseigné** dès qu'il y a au moins un attributaire/retenu (en multi-attributaires ou base de données fournisseurs, joindre tous les noms retenus par ` ; `).
   - `montant_attribue_min_fcfa` / `montant_attribue_max_fcfa` (en FCFA, HTVA/TTC précisé dans les remarques si nécessaire) et `delai_execution`.
   - `contacts_entreprises` : extraire **tous les contacts et identifiants** disponibles pour chaque entreprise (téléphone, email, adresse physique, boîte postale, ville, IFU, RCCM, représentant légal).
   - `remarques_autorite` : extraire **mot pour mot ou fidèlement toutes les remarques, observations, réserves et motifs** formulés par l'autorité émettrice / commission d'attribution (motifs de rejet, pièces manquantes, non-conformités techniques/administratives, anomalies de prix, recommandations).
   - `est_infructueux` et `motif_infructueux` (ex. `Pas eu de soumissionnaire`, `Offres hors enveloppe`, `Non conforme`).

3. **Soumissionnaires (`soumissionnaires`)** :
   - Lister **chaque soumissionnaire** (retenu, non retenu, écarté, hors enveloppe) avec :
     - `nom` complet,
     - `montant_lu_htva`, `montant_lu_ttc`, `montant_corrige_htva`, `montant_corrige_ttc`,
     - rang / statut (`retenu`, `non retenu`, `écarté`),
     - motif détaillé de rejet ou observation spécifique de la commission.
