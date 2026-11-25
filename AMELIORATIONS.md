# Veille BF — Feuille de route des améliorations

> Objectif : dépasser **FasoMarchés** (scoring « vos chances » + WhatsApp, 2 500/5 000 F) et
> **VIGIS** (cockpit data/IA, dataset 20 048 marchés, 15/35/75 000 F) en s'appuyant sur notre
> seul vrai avantage défendable : **l'historique des résultats croisé avec les soumissionnaires**
> (`resultats` + `resultats_soumissionnaires` + `entreprises`), que ni l'un ni l'autre n'exploite à fond.
>
> Chaque fiche indique : **Quoi · Pourquoi on passe devant · Données/technique · Palier · Effort**.
> Paliers = Gratuit / Pro / Entreprise (voir `backend/plans.py`). Effort = S (jours) · M (1–2 sem.) · L (plus).

---

## Table des matières

- [Phase 0 — Parité (rattraper le standard du marché)](#phase-0--parité)
- [Phase 1 — Rétention (faire revenir, empêcher de partir)](#phase-1--rétention)
- [Phase 2 — Originalité & moat (passer devant)](#phase-2--originalité--moat)
- [Phase 3 — Réseau & avancé](#phase-3--réseau--avancé)
- [Récapitulatif & ordre de construction](#récapitulatif--ordre-de-construction)
- [Repositionnement tarifaire](#repositionnement-tarifaire)
- [Nouvelles tables à créer](#nouvelles-tables-à-créer)

---

## Phase 0 — Parité

*Sans ça, on paraît en retard face aux deux concurrents. À faire en premier.*

### 0.1 — Alertes WhatsApp gratuites (tunnel d'acquisition)
- **Quoi** : depuis la page d'accueil, sans inscription, l'utilisateur choisit **1 secteur + 1 type** et son numéro WhatsApp → il reçoit les marchés ouverts de son secteur. Les deux concurrents en font leur porte d'entrée.
- **Pourquoi on passe devant** : c'est le canal roi au Burkina. On ne se *différencie* pas ici, on **évite de perdre** l'acquisition. On fera la différence sur le *contenu* des messages (voir 2.1 et 2.5).
- **Données/technique** : nouvelle table `alertes` (secteur, type, canal, numéro, user_id nullable, double opt-in, actif). Envoi via un provider WhatsApp (Meta Cloud API ou agrégateur local type Twilio/360dialog) derrière une **couche d'abstraction `notifications/`** calquée sur `payments/` (base.py + provider réel + provider « log » pour dev). Cron matinal qui filtre les nouveaux marchés et pousse.
- **Palier** : Gratuit (1 secteur/1 type) · Pro (tous secteurs) · Entreprise (illimité + WhatsApp).
- **Effort** : M (le provider WhatsApp est le point dur ; commencer par e-mail + un provider WhatsApp « simulate »).

### 0.2 — Scoring « Mes chances » GO / NO GO
- **Quoi** : pour un marché, un **score /100**, une reco **GO / À étudier / NO GO**, une **proba de gain estimée**, le **nombre de concurrents attendus**, une **zone de prix compétitive**. Adapté au profil de l'entreprise (secteur, agrément, ancienneté, historique).
- **Pourquoi on passe devant** : FasoMarchés avoue « modèle en cours de validation, peut se tromper ». Notre scoring sera **explicable et prouvé** (voir 2.2) — c'est ça la différence, pas le score brut.
- **Données/technique** : modèle heuristique v1 (pas de ML lourd) basé sur les **attributions comparables réelles** (même secteur/type/autorité) : nb de plis moyen, fourchette des montants retenus, taux d'infructueux. Nouvelle route `POST /api/scoring` + table `profils_candidature` (le profil entreprise de l'utilisateur).
- **Palier** : aperçu en Gratuit (score flouté/essai), complet en Pro.
- **Effort** : M.

---

## Phase 1 — Rétention

*Ce qui transforme un visiteur en utilisateur quotidien. Deux ressorts : la **peur de rater** (FOMO) et le **travail qui vit chez nous**.*

### 1.1 — Fil quotidien « fait pour moi »
- **Quoi** : à la connexion, l'utilisateur voit d'abord **ses** marchés (ses secteurs, sa région, sa fourchette de budget), avec un badge « 3 nouveaux depuis hier ».
- **Pourquoi on passe devant** : les concurrents affichent une liste générique. Ici, ouvrir Veille BF devient un **réflexe du matin**.
- **Données/technique** : `profils_candidature` (secteurs, région, budget) + tri/filtre côté `routes_data`. Marqueur « vu le » par user pour calculer le « depuis hier ».
- **Palier** : Gratuit (basique) · Pro (multi-secteurs + budget).
- **Effort** : S.

### 1.2 — Alerte matinale + « dernière chance » (FOMO)
- **Quoi** : chaque matin, WhatsApp/e-mail « 2 nouveaux marchés BTP à Ouaga, dépôt dans 6 jours ». Et le rappel **J-3 / J-1** sur les marchés suivis : « ⏰ Dépôt demain pour le marché que tu suis ».
- **Pourquoi on passe devant** : le rappel « dernière chance » sur **les favoris de l'utilisateur** est personnel et quasi impossible à ignorer. Supprime la pire douleur du métier : rater une date limite.
- **Données/technique** : table `suivis` (favoris) + cron de rappels qui lit les dates limites + `notifications/`.
- **Palier** : Pro.
- **Effort** : S (une fois 0.1 et 1.6 en place).

### 1.3 — Suivi de dossier + checklist + compte à rebours
- **Quoi** : « Mes marchés suivis » : pour chaque marché, **jours restants**, **checklist des pièces à fournir** à cocher, statut (à étudier / en préparation / déposé).
- **Pourquoi on passe devant** : dès qu'un utilisateur a 3 dossiers en préparation chez nous, **son travail vit dans l'outil** → il ne part plus. FasoMarchés le fait ; il faut au moins l'égaler, avec une checklist plus claire.
- **Données/technique** : tables `dossiers` (user_id, avis_id, statut) + `dossier_pieces` (libellé, coché). Pièces par défaut selon le type de marché.
- **Palier** : Pro · Entreprise (avec validation d'équipe, voir 3.4).
- **Effort** : M.

### 1.4 — Radar concurrent (« qui va me battre ? »)
- **Quoi** : l'utilisateur suit 2–3 entreprises rivales → **alerte quand elles gagnent** un marché, + leur fiche (marchés remportés, autorités clientes, montants).
- **Pourquoi on passe devant** : c'est **émotionnel** (surveiller ses concurrents) et **on est seuls à pouvoir le faire proprement** grâce à `resultats_soumissionnaires`. VIGIS a de l'« intelligence concurrentielle » générique ; nous, un **radar personnel**.
- **Données/technique** : table `radar_concurrents` (user_id, entreprise_id) + cron sur nouvelles attributions + `entreprises`/`resultats_soumissionnaires` déjà en base.
- **Palier** : Pro (1–3 concurrents) · Entreprise (illimité).
- **Effort** : M.

### 1.5 — Mon tableau de bord perso
- **Quoi** : nb de marchés suivis / soumissionnés / gagnés, **mon taux de réussite** vs la moyenne de mon secteur, montant total remporté cette année.
- **Pourquoi on passe devant** : des **stats personnelles** donnent une raison de revenir **même sans nouveau marché**. Les deux concurrents n'ont que des stats globales.
- **Données/technique** : agrège `dossiers` (statut déposé/gagné déclaré par l'utilisateur) + comparaison aux agrégats `resultats`.
- **Palier** : Pro.
- **Effort** : S.

### 1.6 — Favoris / suivi d'un marché (socle technique)
- **Quoi** : bouton « Suivre ce marché ». Base de 1.2, 1.3, 2.1.
- **Pourquoi on passe devant** : brique indispensable à toute la rétention.
- **Données/technique** : table `suivis` (user_id, avis_id, cree_le) + routes `POST/DELETE /api/suivis`.
- **Palier** : Gratuit (quota) · Pro (illimité).
- **Effort** : S.

### 1.7 — Profil qui s'enrichit (effet « coffre »)
- **Quoi** : l'utilisateur saisit une fois ses infos (IFU, RCCM, agréments, documents) → scores personnalisés + dossiers pré-remplis.
- **Pourquoi on passe devant** : plus il investit dans son profil, **plus il est coûteux de partir**. Alimente 0.2 et 3.5.
- **Données/technique** : extension `profils_candidature` + `coffre_documents` (fichiers chiffrés/stockés). Réutilise le gating `require_feature`.
- **Palier** : Pro (profil) · Entreprise (coffre partagé équipe).
- **Effort** : M.

### 1.8 — Résumé hebdomadaire WhatsApp
- **Quoi** : chaque lundi « Ta semaine : 12 marchés dans tes secteurs, 3 résultats te concernant, ton concurrent X a gagné 1 marché ».
- **Pourquoi on passe devant** : un **rendez-vous régulier** = une habitude ancrée.
- **Données/technique** : cron hebdo qui compile fil perso + radar + résultats favoris, via `notifications/`.
- **Palier** : Pro.
- **Effort** : S.

---

## Phase 2 — Originalité & moat

*Les fonctionnalités que **ni FasoMarchés ni VIGIS ne peuvent copier vite**, parce qu'elles exigent notre historique résultats × soumissionnaires.*

### 2.1 — ⭐ Alerte résultat « boucle fermée » (l'idée phare)
- **Quoi** : quand un marché **mis en favori** est attribué → notification :
  > 📣 « Le marché [objet] que tu suivais a été attribué à **BADRO SERVICES** pour **16,9 M FCFA**, face à 3 offres. »

  Avec les **3 crochets** :
  1. **Débrief** — « Montant retenu 16,9 M — notre estimation était 15–18 M ✅ » (prouve le scoring).
  2. **Miroir perso** — si l'utilisateur avait coché « je soumissionne » : « le gagnant était ~8 % sous ta fourchette ».
  3. **Rebond** — « BADRO t'a battu ? Ajoute-le à ton radar » / « 2 marchés similaires sont ouverts ».
- **Pourquoi on passe devant** : ferme la boucle suivi → résultat → apprentissage → re-suivi. **Aucun des deux n'en fait un cycle.** Rétention + preuve + émotion en un seul message.
- **Données/technique** : cron qui matche les nouvelles lignes `resultats` aux `suivis` (par `avis_id`/référence) → `notifications/`. Débrief = comparaison au scoring stocké au moment du suivi.
- **Palier** : Pro (Gratuit peut recevoir une version courte sans débrief, pour donner envie).
- **Effort** : M.

### 2.2 — Scoring explicable et prouvé
- **Quoi** : sous chaque score, **les 3–5 attributions comparables réelles** qui le fondent (objet, autorité, gagnant, montant, nb de plis). Et un **compteur public de fiabilité** : « nos estimations de prix sont justes à X % sur les 90 derniers jours ».
- **Pourquoi on passe devant** : on transforme la **transparence** en marque, pile là où FasoMarchés admet sa faiblesse. On ne demande pas de *croire* le score, on le *montre*.
- **Données/technique** : la requête de comparables alimente déjà 0.2 ; il suffit de **renvoyer les preuves** au front. Le compteur de fiabilité = job qui compare estimation vs résultat réel à mesure que les attributions tombent.
- **Palier** : Pro.
- **Effort** : S (si 0.2 fait) · le compteur de fiabilité : M.

### 2.3 — 🔮 Veille prédictive (marchés récurrents / saisonniers)
- **Quoi** : détecter les marchés que les autorités **republient chaque année** (nettoyage, gardiennage, carburant, fournitures…) et prévenir **avant** publication : « Le CHU-B relance son gardiennage ~chaque novembre — attendu dans ~3 semaines, prépare-toi. »
- **Pourquoi on passe devant** : **personne ne fait de veille prédictive** au Burkina. Effet « waouh » maximal, et ça crée une dépendance (on anticipe à leur place).
- **Données/technique** : analyse de périodicité sur l'historique `resultats`/avis par (autorité, objet normalisé). Table `marches_attendus` (autorité, secteur, mois probable, confiance). Cron mensuel.
- **Palier** : Pro (teaser) · Entreprise (liste complète + alertes).
- **Effort** : L (normalisation des objets + détection de récurrence).

### 2.4 — Indice de fiabilité / intégrité par autorité
- **Quoi** : par autorité contractante : taux d'**infructueux**, **concentration** des attributions (part des 2–3 mêmes gagnants = signal de favoritisme), montant moyen, délais. Un « indice » synthétique.
- **Pourquoi on passe devant** : angle **transparence/intégrité** inédit, excellent pour la **presse et le SEO**, et utile à l'utilisateur (« ça vaut le coup de répondre chez eux ? »).
- **Données/technique** : agrégations sur `resultats` + `resultats_soumissionnaires` + `authorities` (déjà en base). Nouvelle route + page autorité enrichie.
- **Palier** : aperçu Gratuit · détail Pro.
- **Effort** : M.

### 2.5 — Tendances en **temps réel** (vs Observatoire mensuel de VIGIS)
- **Quoi** : un tableau de bord qui **bouge chaque jour** : montants publiés cette semaine, secteurs qui chauffent, autorités les plus actives *en ce moment*, nouveaux entrants.
- **Pourquoi on passe devant** : l'Observatoire de VIGIS n'est qu'une **photo mensuelle** (produit de com/SEO). On offre la même intelligence **vivante**.
- **Données/technique** : agrégats glissants sur les tables existantes ; rafraîchi par le pipeline quotidien. Réutilise `/api/stats` étendu.
- **Palier** : Gratuit (global) · Pro (filtré par mes secteurs).
- **Effort** : S/M.

### 2.6 — Prix gagnants réels par autorité / objet
- **Quoi** : pour un type de marché/une autorité, la **fourchette réelle des offres retenues** (« prix plancher » basé sur des faits, pas une estimation vague).
- **Pourquoi on passe devant** : FasoMarchés vend un « prix plancher » estimé ; nous l'adossons aux **montants réellement attribués** de notre base.
- **Données/technique** : requête sur `resultats` (montants) filtrée par secteur/autorité/objet.
- **Palier** : Pro (Entreprise : séries historiques + export).
- **Effort** : S.

---

## Phase 3 — Réseau & avancé

*Effets de réseau et montée en gamme. Plus long, mais augmente le moat et le ticket moyen.*

### 3.1 — 🤝 « Groupements » (matching, effet réseau)
- **Quoi** : l'utilisateur voit un marché mais **n'a pas l'agrément** requis → on lui propose les entreprises de notre base qui **ont cet agrément et soumissionnent dans ce secteur** pour former un groupement.
- **Pourquoi on passe devant** : crée un **effet réseau** (plus d'entreprises = plus utile) que les concurrents ne peuvent pas copier sans la même base. Ouvre un futur annuaire/marketplace.
- **Données/technique** : `entreprises` + agréments (à enrichir) + un opt-in « je suis ouvert aux groupements ». Mise en relation via WhatsApp.
- **Palier** : Pro · Entreprise.
- **Effort** : L.

### 3.2 — 🤖 Bot WhatsApp conversationnel (two-way)
- **Quoi** : l'utilisateur **écrit** « marchés BTP à Bobo cette semaine » et le bot **répond** dans WhatsApp.
- **Pourquoi on passe devant** : les deux concurrents **envoient** sur WhatsApp mais ne **répondent pas**. Conversationnel = là où l'utilisateur vit déjà.
- **Données/technique** : webhook entrant WhatsApp → parsing d'intention (règles simples d'abord, LLM ensuite) → requête `routes_data` → réponse. S'appuie sur `notifications/`.
- **Palier** : Pro · Entreprise.
- **Effort** : L.

### 3.3 — Agenda des dépôts
- **Quoi** : tous les marchés suivis dans un **calendrier** avec compte à rebours, export **Google/Outlook (.ics)**, rappels J-7/J-3/J-1.
- **Pourquoi on passe devant** : anti-oubli absolu, intégré à leur outil habituel.
- **Données/technique** : génération `.ics` à partir de `suivis` ; les rappels réutilisent 1.2.
- **Palier** : Pro.
- **Effort** : S.

### 3.4 — Espace équipe (Entreprise)
- **Quoi** : multi-utilisateurs, rôles, **validation des candidatures**, tableau de bord collaboratif, workflows internes.
- **Pourquoi on passe devant** : atteint la parité avec l'offre Entreprise de VIGIS (75 000 F) et justifie notre palier haut.
- **Données/technique** : `team_members` existe déjà ; ajouter rôles + partage de `dossiers`/`coffre_documents`.
- **Palier** : Entreprise.
- **Effort** : L.

### 3.5 — Générateur de dossier (assistance à la soumission)
- **Quoi** : pré-remplir les pièces types (lettre de soumission, etc.) depuis le **profil coffre** (1.7).
- **Pourquoi on passe devant** : on passe d'« informer » à « **faire le travail** » — personne ne va jusque-là.
- **Données/technique** : templates + données `profils_candidature`/`coffre_documents` → génération PDF.
- **Palier** : Entreprise.
- **Effort** : L.

### 3.6 — API & intégrations
- **Quoi** : API publique (clés déjà gérées via `api_keys`), exports programmables.
- **Palier** : Entreprise.
- **Effort** : M (socle déjà présent dans `routes_billing`).

### 3.7 — Distribution : pages SEO + baromètre
- **Quoi** : pages SEO par **secteur/région** (« Marchés publics BTP Burkina Faso ») et un **baromètre** périodique — les deux grands moteurs de trafic de VIGIS, que FasoMarchés n'a pas.
- **Pourquoi on passe devant** : acquisition organique durable, pas seulement WhatsApp.
- **Données/technique** : pages générées depuis les agrégats ; réutilise les routes friendly de `backend/main.py`.
- **Palier** : public.
- **Effort** : M, continu.

---

## Récapitulatif & ordre de construction

| # | Idée | Phase | Palier | Effort | Moat (dur à copier) |
|---|------|-------|--------|--------|:---:|
| 1.6 | Favoris / suivi d'un marché | 1 | Gratuit/Pro | S | socle |
| 0.1 | Alertes WhatsApp gratuites | 0 | tous | M | — |
| 0.2 | Scoring GO/NO GO | 0 | Pro | M | ★ |
| 2.1 | **Alerte résultat boucle fermée** | 2 | Pro | M | ★★★ |
| 1.2 | Alerte matinale + dernière chance | 1 | Pro | S | ★ |
| 1.3 | Suivi de dossier + checklist | 1 | Pro | M | ★ |
| 1.4 | Radar concurrent | 1 | Pro | M | ★★★ |
| 2.2 | Scoring prouvé/transparent | 2 | Pro | S | ★★ |
| 1.1 | Fil quotidien perso | 1 | Gratuit/Pro | S | ★ |
| 1.5 | Tableau de bord perso | 1 | Pro | S | ★ |
| 2.4 | Indice fiabilité autorité | 2 | Pro | M | ★★ |
| 2.6 | Prix gagnants réels | 2 | Pro | S | ★★ |
| 2.5 | Tendances temps réel | 2 | Gratuit/Pro | S/M | ★ |
| 1.7 | Profil coffre | 1 | Pro/Ent | M | ★ |
| 1.8 | Résumé hebdo WhatsApp | 1 | Pro | S | ★ |
| 2.3 | **Veille prédictive** | 2 | Pro/Ent | L | ★★★ |
| 3.3 | Agenda des dépôts | 3 | Pro | S | — |
| 3.1 | Groupements (réseau) | 3 | Pro/Ent | L | ★★★ |
| 3.2 | Bot WhatsApp conversationnel | 3 | Pro/Ent | L | ★★ |
| 3.4 | Espace équipe | 3 | Ent | L | — |
| 3.5 | Générateur de dossier | 3 | Ent | L | ★★ |
| 3.7 | SEO + baromètre | 3 | public | M | — |

**Sprint recommandé (ordre réel de build) :**
1. **1.6 Favoris** → socle de tout le reste.
2. **0.1 Alertes (e-mail + WhatsApp « simulate »)** → acquisition + tuyau de notification.
3. **2.1 Alerte résultat boucle fermée** → notre signature, branchée sur 1.6.
4. **0.2 + 2.2 Scoring prouvé** → parité + preuve.
5. **1.4 Radar concurrent** → le moat émotionnel.
6. Ensuite 1.2 / 1.3 / 1.5 (rétention), puis Phase 2 restante, puis Phase 3.

Logique : d'abord le **socle** (favoris + notifications), puis les **3 fonctionnalités que personne ne peut copier** (2.1, 1.4, 2.3), le reste consolide.

---

## Repositionnement tarifaire

Notre grille actuelle (Pro 15 000 / Entreprise 50 000) est **la pire des deux mondes** : plus chère que FasoMarchés (Plus 2 500 / Pro 5 000) **sans** la profondeur data/IA de VIGIS pour justifier le prix. Trois options :

- **A — Attaquer par le bas** : Pro ~**5 000–7 000 F**, pour prendre le marché volume face à FasoMarchés. Simple, agressif.
- **B — Milieu assumé** : Pro ~**10 000 F**, Entreprise ~**40 000 F**, **justifié** par le radar concurrent + l'alerte boucle fermée + la veille prédictive (features uniques).
- **C — Pay-per-market** : comme FasoMarchés, une analyse à l'unité (~2 500 F/marché) pour les non-abonnés → tunnel vers l'abonnement.

Recommandation : **B** (milieu justifié par le moat) **+ C** (porte d'entrée sans engagement). Garder les prix dans `backend/plans.py` comme aujourd'hui.

---

## Nouvelles tables à créer

Au-delà de l'existant (`plans`, `users`, `subscriptions`, `payments`, `usage_counters`, `api_keys`, `team_members`, `resultats`, `resultats_soumissionnaires`, `entreprises`, `authorities`) :

- `suivis` — favoris (user_id, avis_id, scoring_snapshot, cree_le)
- `alertes` — abonnements d'alerte (user_id nullable, secteur, type, region, canal, numero, actif, opt_in)
- `notifications` — journal des envois (user_id, type, canal, payload, statut, envoye_le)
- `profils_candidature` — profil entreprise de l'utilisateur (secteurs, region, budget, agrements, anciennete, historique)
- `dossiers` + `dossier_pieces` — suivi de soumission + checklist
- `radar_concurrents` — entreprises surveillées (user_id, entreprise_id)
- `coffre_documents` — documents de l'entreprise (user_id/team, fichier, type)
- `marches_attendus` — prédictions de récurrence (autorite, secteur, mois_probable, confiance)

Plus un package **`backend/notifications/`** (base.py + provider WhatsApp réel + provider « log » pour dev), calqué sur `backend/payments/`, et des **crons** (matin, J-1, hebdo, mensuel prédictif).

---

*Document de travail — à transformer en tickets au fil des sprints.*
