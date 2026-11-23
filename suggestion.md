# Stratégies d'Optimisation de la Consommation de Tokens (ScrapperBF)

Ce document consigne les recommandations et leviers concrets pour **diviser par 3 à 5 le nombre de tokens consommés** lors de l'extraction de métadonnées et de mots-clés sur les avis de marchés publics DGCMEF.

---

## 1. Filtrage et élagage du texte administratif bavard (-55% de tokens d'entrée)

Dans un bulletin DGCMEF, **60% à 70% du texte d'une annonce est du jargon administratif récurrent** (conditions générales de participation, mentions légales de réclamation, nombre d'exemplaires papier, interdiction des faillites, etc.).

### Règle d'or :
Toutes les métadonnées utiles sont situées :
* Dans les **25 premières lignes** (autorité, objet, référence, type de marché, financement, montants).
* Dans les **10 dernières lignes** (date limite, heure, lieu de dépôt, caution de soumission, signature).

### Implémentation recommandée :
```python
def compacter_texte_annonce(texte: str, max_debut: int = 1200, max_fin: int = 400) -> str:
    """Conserve uniquement les zones riches en métadonnées utiles."""
    if len(texte) <= (max_debut + max_fin):
        return texte
    return texte[:max_debut] + "\n\n[... TEXTE ADMINISTRATIF TRONQUÉ ...]\n\n" + texte[-max_fin:]
```

---

## 2. Compaction du Prompt Système et du Schéma (-85% de tokens de prompt)

Au lieu d'envoyer un prompt verbeux avec de longues descriptions explicatives pour chaque champ, envoyer un prompt direct avec un template JSON concis. Les LLMs modernes (DeepSeek, GLM, GPT-4) n'ont pas besoin de phrases redondantes.

### Avant (~600 tokens) :
```json
{
  "autorite_emettrice": "Nom officiel du ministère, institution, direction ou commune émettrice",
  "objet": "Intitulé complet du marché / objet de l'avis",
  "numero_reference": "Numéro de référence complet de l'avis",
  "financement": "Source de financement mentionnée"
}
```

### Après (~90 tokens) :
```text
Rôle: Extracteur JSON pour avis de marchés publics.
Extrais UNIQUEMENT les champs présents dans le texte. Omets les clés absentes.
Template JSON attendu :
{"aut":"","obj":"","ref":"","cat":"","finc":"","mt":"","caut":"","dl":"","delai":""}
```

---

## 3. Utilisation de clés courtes en sortie (-30% de tokens de complétion)

Chaque nom de clé généré en sortie par le LLM est facturé token par token.

### Remplacement par abréviations :
| Clé longue | Clé courte | Clé finale en base Python |
|---|---|---|
| `autorite_emettrice` | `aut` | `autorite_emettrice` |
| `objet` | `obj` | `objet` |
| `numero_reference` | `ref` | `numero_reference` |
| `categorie` | `cat` | `categorie` |
| `financement` | `finc` | `financement` |
| `montant_previsionnel` | `mt` | `montant_previsionnel` |
| `caution_soumission` | `caut` | `caution_soumission` |
| `date_limite_depot` | `dl` | `date_limite_depot` |

### Renommage automatique en Python :
```python
CLE_MAPPING = {
    "aut": "autorite_emettrice", "obj": "objet", "ref": "numero_reference",
    "cat": "categorie", "finc": "financement", "mt": "montant",
    "caut": "caution_soumission", "dl": "date_limite_depot", "delai": "delai_execution"
}
propre = {CLE_MAPPING.get(k, k): v for k, v in json_brut.items()}
```

---

## 4. Omission stricte des valeurs nulles (-20% de tokens de complétion)

Par défaut, un modèle interrogé avec un schéma écrit :
`"caution_soumission": null, "delai_validite": null, "lieu_depot": null, ...`
Chaque mention de `null` consomme 2 à 3 tokens inutilement.

### Consigne à inclure :
> *"N'inclus que les données trouvées dans le document. Ne génère pas de clés pour les valeurs nulles."*

---

## 5. Pré-remplissage déterministe via la géométrie (-25% de charge globale)

Grâce à la détection par bandeaux couleur de `pdfplumber` :
* La **catégorie** est déjà connue (Bandeau Rouge).
* L'**autorité émettrice** est déjà connue (Bandeau Jaune).
* Le **titre d'ouverture** est déjà connu (Bandeau Cyan).

Il est inutile de dépenser des tokens pour faire ré-extraire ces 3 champs par un LLM. On ne demande à l'IA d'extraire **que les variables internes au corps de texte** :
1. `ref` (Référence du dossier)
2. `mt` (Montants HTVA / TTC)
3. `finc` (Source de financement)
4. `dl` (Date et heure limites)
5. `caut` (Caution éventuelle)

---

## Synthèse du gain attendu

| Poste de coût | Avant | Après optimisation | Économie |
|---|---|---|---|
| Prompt système | ~600 tokens | ~90 tokens | **-85 %** |
| Texte de l'annonce | ~800 tokens | ~350 tokens | **-55 %** |
| Réponse JSON (sortie) | ~300 tokens | ~80 tokens | **-73 %** |
| **TOTAL PAR AVIS** | **~1 700 tokens** | **~520 tokens** | 📉 **Facture divisée par 3,2** |

Avec un forfait de 10 millions de tokens (comme sur DeepSeek ou GLM) :
* Capacité avant optimisation : **~5 800 avis** traités.
* Capacité après optimisation : **~19 200 avis** traités.
