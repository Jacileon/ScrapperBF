# Architecture de déploiement — Veille BF

Guide pour passer du **dev (poste local)** à la **prod sur VPS**, en ne gardant
que le strict nécessaire.

---

## 1. Vue d'ensemble

Le projet a **deux parties indépendantes** :

| Partie | Rôle | Dépendances | Fréquence |
|--------|------|-------------|-----------|
| **Serveur web / API** | Sert le site et l'API REST depuis la base SQLite | légères (`fastapi`, `uvicorn`) | permanent |
| **Pipeline d'ingestion** | Télécharge les bulletins → OCR → découpage → extraction LLM → base + export front | lourdes (OCR, LLM, PDF) | planifié (1×/jour) |

Clé du déploiement : **le serveur web n'a PAS besoin du pipeline**. Il ne lit
que `marches_publics_burkina.db` (+ le front déjà généré). Le pipeline peut
tourner à part (même VPS la nuit, ou une autre machine), puis livrer la base
mise à jour.

```
                        VPS (prod)
   Internet ──▶ Nginx (443, TLS) ──▶ uvicorn 127.0.0.1:8000 ──▶ server_front.py
                  │  sert /assets/ en direct              │
                  │                                        └─▶ marches_publics_burkina.db (SQLite)
                  │                                                     ▲
                  └── (statique: web/app/assets)                        │
                                                                        │
   [Planifié 1×/jour]  veillebf-pipeline.timer ─▶ ingestion ─▶ export ─┘
                        (télécharge, OCR, LLM, écrit la base + data.js)
```

---

## 2. Dev ✦ Prod — ce qui change

| | Dev (actuel, Windows) | Prod (VPS Linux) |
|--|--|--|
| Lancement | `python server_front.py` (127.0.0.1:8000) | `uvicorn … --workers 2` sous **systemd** |
| Accès | localhost | **Nginx** + domaine + **HTTPS** (certbot) |
| Statique | servi par FastAPI | servi par **Nginx** (`/assets/`) |
| Ingestion | scripts lancés à la main | **systemd timer** quotidien |
| Secrets | `model_keys.json` local | `.env` + `model_keys.json` sur le serveur, hors Git |
| CORS | `allow_origins=["*"]` | **restreindre** au domaine (voir §7) |

---

## 3. Ce qu'on garde / ce qu'on jette en prod

**✅ Nécessaire au RUNTIME web (profil léger) :**
- `server_front.py`
- `web/app/` (tout le front)
- `marches_publics_burkina.db` (la donnée)
- `requirements.txt`

**✅ En plus si l'ingestion tourne sur le VPS :**
- `reader_core/`, `prod_pipeline/`
- `extract_*.py`, `pipeline*.py`, `download_and_classify_*.py`, `organiser_*.py`,
  `segment_and_crop_avis.py`, `split_resultats_sections.py`, `sector_classifier.py`,
  `export_db_to_front.py`, `scan_communiques_and_fonts.py`, `pdf_downloader.py`,
  `free_ai_gateway.py`, `config.py`, `check_llm.py`, `database_schema.py`,
  `progression.py`, `runner.py`
- `requirements-pipeline.txt`, `schema_config.yaml`
- Secrets : `.env`, `model_keys.json`

**🗑️ À NE PAS déployer (dev/jetable, régénérable) :**
- `scratch/` — scripts d'audit/debug jetables
- `files/` — scripts legacy/expérimentaux (`new_logic/`)
- `telechargements_pdf_classes/` — PDF bruts + OCR intermédiaires (volumineux)
- `output_pipeline/`, `export_marches/` — sorties régénérables
- `bench_*.json`, `bench_report.md` — bancs d'essai
- `tests/` — utile en CI, inutile au runtime
- caches `__pycache__/`, `.venv/`

> L'image Docker web (`deploy/Dockerfile`) et `.dockerignore` appliquent déjà
> ce tri automatiquement.

---

## 4. Arborescence cible sur le VPS

```
/opt/veillebf/
├── server_front.py
├── web/app/                      # front (pages + assets)
├── marches_publics_burkina.db    # base servie
├── requirements.txt
├── .venv/                        # virtualenv
├── .env                          # secrets (640, hors Git)
├── model_keys.json               # clés LLM (si ingestion ici)
└── (pipeline : reader_core/, prod_pipeline/, extract_*.py, …)
```

---

## 5. Installation pas à pas (Ubuntu 22.04+)

```bash
# 1. Utilisateur dédié + dossier
sudo adduser --system --group veillebf
sudo mkdir -p /opt/veillebf && sudo chown veillebf:veillebf /opt/veillebf

# 2. Déposer le code (git clone, rsync, ou l'image Docker)
#    En rsync, EXCLURE les dossiers jetables (voir §3).

# 3. Environnement Python
cd /opt/veillebf
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt          # web seul
# .venv/bin/pip install -r requirements-pipeline.txt  # si ingestion ici

# 4. Secrets
cp .env.example .env && nano .env                  # OPENROUTER_API_KEYS=...
# (+ model_keys.json si ingestion)

# 5. Service web (systemd)
sudo cp deploy/veillebf.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now veillebf
systemctl status veillebf

# 6. Nginx + HTTPS
sudo cp deploy/nginx.conf /etc/nginx/sites-available/veillebf
sudo ln -s /etc/nginx/sites-available/veillebf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d veille.exemple.bf          # TLS auto

# 7. (option) Ingestion planifiée
sudo cp deploy/veillebf-pipeline.service deploy/veillebf-pipeline.timer /etc/systemd/system/
sudo systemctl enable --now veillebf-pipeline.timer
```

### Variante Docker (web seul)
```bash
docker build -f deploy/Dockerfile -t veillebf-web .
docker run -d --restart unless-stopped -p 127.0.0.1:8000:8000 veillebf-web
# puis Nginx en reverse proxy devant, comme ci-dessus
```

---

## 6. Mises à jour

- **Nouvelles données** : l'ingestion régénère `marches_publics_burkina.db` et
  `web/app/assets/data.js`/`data.json`. Le service web les relit à chaud (pas de
  redémarrage nécessaire pour les données ; l'endpoint `/api/refresh` recharge le
  cache si besoin).
- **Nouveau code** : `git pull` (ou nouvelle image) puis
  `sudo systemctl restart veillebf`.

---

## 7. Sécurité

- **Secrets hors Git** : `.env` et `model_keys.json` sont dans `.gitignore`.
  Sur le serveur : `chmod 640`, propriété `veillebf`.
- **CORS** : en prod, remplacer `allow_origins=["*"]` par le domaine réel dans
  `server_front.py` (ou gérer l'origine au niveau Nginx).
- **Pare-feu** : n'exposer que 80/443 (`ufw allow 'Nginx Full'`). uvicorn reste
  sur `127.0.0.1` (jamais exposé directement).
- **Base en lecture** : le service web ne fait que lire la base ; l'écriture vient
  du pipeline. Garder les deux rôles séparés (utilisateur/droits).

---

## 8. Sauvegarde

Un seul fichier compte vraiment : **`marches_publics_burkina.db`**. Le reste est
régénérable. Sauvegarde quotidienne suffisante :

```bash
sqlite3 /opt/veillebf/marches_publics_burkina.db ".backup /var/backups/veillebf-$(date +%F).db"
```
