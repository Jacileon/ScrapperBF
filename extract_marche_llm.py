# -*- coding: utf-8 -*-
"""
Module universel d'extraction LLM pour les annonces de marchés publics (ScrapperBF).
Compatible avec :
- Z.ai / Zhipu AI (GLM-5.3-flash, GLM-4-flash)
- DeepSeek-API local (http://localhost:8000/v1)
- Tout fournisseur OpenAI-compatible gratuit (Groq, OpenRouter, etc.)
"""

import os
import json
import urllib.request
import urllib.error
import sys

PROMPT_EXTRACTION = """Tu es un expert en analyse des marchés publics du Burkina Faso.
Analyse l'avis d'appel d'offres ci-dessous et extrait les informations au format JSON strict avec les clés suivantes :
{
  "numero_avis": "...",
  "autorite_contractante": "...",
  "objet": "...",
  "type_marche": "Travaux | Fournitures | Prestations",
  "secteur_activite": "BTP, Génie Civil & Construction | Santé, Médical & Pharmacie | Informatique & Télécoms | Eau, Forages & Assainissement | ...",
  "financement": "...",
  "montant_total_htva": "...",
  "montant_total_ttc": "...",
  "lots": [
    {
      "numero": 1,
      "designation": "...",
      "montant_htva": "...",
      "montant_ttc": "...",
      "garantie_soumission": "..."
    }
  ],
  "date_limite_depot": "...",
  "heure_limite_depot": "...",
  "lieu_depot": "...",
  "garantie_soumission_globale": "...",
  "delai_validite_offres": "...",
  "contact_renseignements": "...",
  "prix_dossier": "..."
}
Réponds UNIQUEMENT le bloc JSON, sans aucun texte autour."""

class LLMClient:
    def __init__(self, provider='zai', api_key=None, base_url=None, model=None):
        self.provider = provider
        if provider == 'zai':
            self.base_url = base_url or 'https://api.z.ai/api/paas/v4/chat/completions'
            self.api_key = api_key or '2d1556e2fee64e81b14cd86fb3de2217.GVbPpvlw9YgedJ2X'
            self.model = model or 'glm-5.3-flash'
        elif provider == 'deepseek_local':
            self.base_url = base_url or 'http://127.0.0.1:8000/v1/chat/completions'
            self.api_key = api_key or 'sk-no-key-required'
            self.model = model or 'deepseek-chat'
        else:
            self.base_url = base_url
            self.api_key = api_key
            self.model = model

    def extraire(self, texte_annonce):
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        data = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': PROMPT_EXTRACTION},
                {'role': 'user', 'content': texte_annonce}
            ],
            'temperature': 0.1
        }
        
        req = urllib.request.Request(self.base_url, data=json.dumps(data).encode('utf-8'), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res = json.loads(resp.read().decode('utf-8'))
                content = res['choices'][0]['message']['content']
                return {'success': True, 'raw': content, 'usage': res.get('usage')}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8', errors='ignore')
            return {'success': False, 'code': e.code, 'error': err_body}
        except Exception as e:
            return {'success': False, 'error': str(e)}

if __name__ == '__main__':
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
        
    md_path = r'C:\Users\DANIEL\Documents\Mes projets\ScrapperBF\output_pipeline\N4505\annonces_md\N4505_Avis_26_p42-p42_Travaux.md'
    with open(md_path, 'r', encoding='utf-8') as f:
        texte_zorgho = f.read()

    print('=== TEST D EXTRACTION SUR L ANNONCE DE ZORGHO ===')
    print(f'Fichier : {md_path} ({len(texte_zorgho)} car)')
    
    # 1. Z.ai
    print('\n--> 1. Appel Z.ai (GLM-5.3-flash)...')
    client_zai = LLMClient(provider='zai')
    res_zai = client_zai.extraire(texte_zorgho)
    if res_zai['success']:
        print('Succès Z.ai ! Réponse :\n', res_zai['raw'])
    else:
        print(f'Statut Z.ai : Code {res_zai.get("code")} -> {res_zai.get("error")}')

    # 2. DeepSeek Local
    print('\n--> 2. Test DeepSeek-API Local (http://127.0.0.1:8000/v1)...')
    client_ds = LLMClient(provider='deepseek_local')
    res_ds = client_ds.extraire(texte_zorgho)
    if res_ds['success']:
        print('Succès DeepSeek-API ! Réponse :\n', res_ds['raw'])
    else:
        print(f'DeepSeek-API Local statut : {res_ds.get("error")}')
