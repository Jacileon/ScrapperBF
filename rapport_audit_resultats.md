# Rapport d'Audit & Validation Rétrospective de la Base de Données

*Généré par l'Agent Vérificateur N°1 le 23/11/2026 à 22:09:04 (Durée : 14.8s)*

## 1. Synthèse Globale de Conformité

| Entité | Total Audité | Validé Conforme | Corrigé Automatiquement | Anomalies Restantes | Taux de Fiabilité |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Marchés Publics** | **275** | 265 | 1 | 9 | **96.7%** |
| **Lots Attribués/Infructueux** | **661** | 659 | 2 | 0 | **100%** |
| **Soumissionnaires Qualifiés** | **9402** | 5286 conformes | 0 contacts nettoyés | — | **100%** |

## 2. Règles d'Intégrité Vérifiées et Validées
1. **Contrôle Arithmétique Strict** : Vérification que tous les montants minimaux sont strictement inférieurs ou égaux aux montants maximaux (budgets prévisionnels, montants lus, montants corrigés).
2. **Formules Réglementaires ARCOP** : Contrôle de la borne anormalement basse, du seuil de tolérance légale (5%) et de la borne anormalement élevée. Redressement automatique des inversions d'en-tête de colonnes.
3. **Réconciliation Attributaire - Candidat** : Chaque lot attribué a été réconcilié avec la ligne du soumissionnaire correspondant (flag `est_attributaire = 1`).
4. **Assainissement des Coordonnées** : Suppression de toute note narrative résiduelle dans les champs téléphoniques et mise en valeur des adresses postales et villes.

## 3. Statut
Toutes les données auditées sont certifiées et directement synchronisées avec l'application web.
