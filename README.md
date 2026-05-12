# CTF Cybergames 2026

Plateforme CTF web légère, auto-hébergeable, construite avec Flask + SQLite.  
Domaine prévu : **2026.ctfcybergames.win**

---

## Sommaire

1. [Présentation](#1-présentation)
2. [Fonctionnalités](#2-fonctionnalités)
3. [Structure des fichiers](#3-structure-des-fichiers)
4. [Prérequis](#4-prérequis)
5. [Installation locale](#5-installation-locale)
6. [Déploiement production avec Gunicorn](#6-déploiement-production-avec-gunicorn)
7. [Service systemd](#7-service-systemd)
8. [Cloudflare Tunnel](#8-cloudflare-tunnel)
9. [Interface admin](#9-interface-admin)
10. [Gestion des équipes](#10-gestion-des-équipes)
11. [Images des challenges](#11-images-des-challenges)
12. [Docker (optionnel)](#12-docker-optionnel)
13. [Sauvegarde](#13-sauvegarde)
14. [Réinitialisation](#14-réinitialisation)
15. [Sécurité](#15-sécurité)

---

## 1. Présentation

Application Flask en Python, sans dépendances externes lourdes.  
Persistance via SQLite. Interface sobre, responsive, servie côté serveur avec Jinja2.

**Score total possible :** 23 points (20 CTF principal + 3 bonus).

---

## 2. Fonctionnalités

- 14 équipes fixes, créées automatiquement à l'initialisation.
- Rejoindre une équipe d'un clic, sans compte ni mot de passe.
- 9 flags principaux (certains composés de sous-flags), 1 bonus.
- 3 essais par flag ; blocage automatique après 3 mauvaises réponses.
- Normalisation configurable par flag (casse, espaces, apostrophes).
- Scoreboard public trié par score puis par date de dernière résolution.
- Interface admin protégée par HTTP Basic Auth (aucun formulaire HTML).
- Administration : voir la progression, forcer la résolution, verrouiller/déverrouiller, réinitialiser.

---

## 3. Structure des fichiers

```
ctf2026/
├── app.py                  # Application Flask principale
├── init_db.py              # Initialisation DB + données préchargées
├── requirements.txt
├── .env.example            # Exemple de configuration
├── Dockerfile
├── docker-compose.yml
├── README.md
├── static/
│   ├── css/
│   │   └── style.css
│   └── assets/             # ← Placer island.png et ship.png ici
└── templates/
    ├── base.html
    ├── index.html
    ├── team_select.html
    ├── challenges.html
    ├── scoreboard.html
    ├── admin_dashboard.html
    ├── admin_team.html
    └── 404.html
```

---

## 4. Prérequis

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip -y
```

---

## 5. Installation locale

```bash
# 1. Cloner / copier le projet
cd /opt
git clone <repo> ctf2026   # ou copier les fichiers manuellement
cd ctf2026

# 2. Environnement virtuel
python3 -m venv venv
source venv/bin/activate

# 3. Dépendances
pip install -r requirements.txt

# 4. Configuration
cp .env.example .env
nano .env          # Adapter SECRET_KEY, ADMIN_PASSWORD, etc.

# 5. Images des challenges
#    Copier island.png et ship.png dans static/assets/
cp /chemin/vers/island.png static/assets/
cp /chemin/vers/ship.png   static/assets/

# 6. Initialisation de la base
python init_db.py

# 7. Lancement de développement
python app.py
# → http://127.0.0.1:8000
```

> **Remarque :** en développement, vous pouvez passer `DEBUG=true` dans `.env`
> pour activer le rechargement automatique. **Ne jamais utiliser en production.**

---

## 6. Déploiement production avec Gunicorn

```bash
source venv/bin/activate

# Test manuel
gunicorn --bind 127.0.0.1:8000 --workers 2 app:app

# L'application écoute sur 127.0.0.1:8000
# Cloudflare Tunnel se chargera de l'exposer publiquement (voir §8)
```

Gunicorn est inclus dans `requirements.txt`.

---

## 7. Service systemd

Créez un utilisateur dédié (recommandé) :

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin ctf
sudo chown -R ctf:ctf /opt/ctf2026
```

Créez le fichier de service :

```bash
sudo nano /etc/systemd/system/ctf2026.service
```

Contenu :

```ini
[Unit]
Description=CTF Cybergames 2026
After=network.target

[Service]
Type=simple
User=ctf
Group=ctf
WorkingDirectory=/opt/ctf2026
EnvironmentFile=/opt/ctf2026/.env
ExecStart=/opt/ctf2026/venv/bin/gunicorn \
    --bind 127.0.0.1:8000 \
    --workers 2 \
    --timeout 60 \
    app:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Activation :

```bash
sudo systemctl daemon-reload
sudo systemctl enable ctf2026
sudo systemctl start ctf2026
sudo systemctl status ctf2026
```

Logs :

```bash
sudo journalctl -u ctf2026 -f
```

---

## 8. Cloudflare Tunnel

Le tunnel Cloudflare permet d'exposer l'application sans ouvrir de port sur le VPS.

### Installation de cloudflared

```bash
# Sur Ubuntu (AMD64)
curl -L https://pkg.cloudflare.com/cloudflare-main.gpg \
     | sudo gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg

echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] \
https://pkg.cloudflare.com/cloudflared jammy main' \
| sudo tee /etc/apt/sources.list.d/cloudflared.list

sudo apt update && sudo apt install cloudflared -y
```

### Authentification et création du tunnel

```bash
cloudflared tunnel login
cloudflared tunnel create ctf2026
```

Notez l'UUID affiché (ex. `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`).

### Fichier de configuration du tunnel

Créez `/etc/cloudflared/config.yml` :

```yaml
tunnel: <UUID-de-votre-tunnel>
credentials-file: /root/.cloudflared/<UUID-de-votre-tunnel>.json

ingress:
  - hostname: 2026.ctfcybergames.win
    service: http://127.0.0.1:8000
  - service: http_status:404
```

> L'application doit écouter sur `127.0.0.1:8000` (valeur par défaut).
> Adaptez le port si vous avez changé `APP_PORT` dans `.env`.

### DNS Cloudflare

```bash
cloudflared tunnel route dns ctf2026 2026.ctfcybergames.win
```

Cette commande crée automatiquement l'enregistrement CNAME dans Cloudflare.

### Lancement automatique du tunnel

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

L'application est maintenant accessible via `https://2026.ctfcybergames.win`.

---

## 9. Interface admin

| Élément | Valeur |
|---|---|
| URL | `/admin` |
| Authentification | HTTP Basic Auth (popup natif du navigateur) |
| Identifiant | Variable `ADMIN_USERNAME` (défaut : `admin`) |
| Mot de passe | Variable `ADMIN_PASSWORD` |

**Toutes les routes `/admin` et `/admin/*` sont protégées.**  
Il n'existe pas de page de connexion HTML — le navigateur affiche sa propre fenêtre d'authentification.

Fonctionnalités admin :
- Vue d'ensemble des 14 équipes (score, flags, dernière résolution)
- Détail par équipe : statut de chaque flag, compteur d'essais
- Forcer la résolution d'un flag
- Verrouiller / déverrouiller un flag
- Réinitialiser une équipe
- Réinitialiser toute la compétition
- Renommer une équipe

---

## 10. Gestion des équipes

- Les 14 équipes (`Equipe 1` … `Equipe 14`) sont créées automatiquement par `init_db.py`.
- Aucun code d'équipe, aucun mot de passe, aucun compte joueur.
- Un joueur clique sur son équipe → sa session est associée à cette équipe.
- Plusieurs joueurs peuvent rejoindre la même équipe ; ils voient la même progression.
- La progression est persistée en SQLite et survit aux redémarrages.

---

## 11. Images des challenges

Placez les images dans `static/assets/` :

| Fichier | Usage |
|---|---|
| `island.png` | Challenge bonus « Stranded Deep » |
| `ship.png` | Flag 1 — Identifiant du navire |

> **Important :** le nom visible sur la photo du navire ne figure nulle part dans
> le code ou les templates. Les joueurs doivent le lire eux-mêmes sur l'image.

Exemple de copie :

```bash
cp island.png /opt/ctf2026/static/assets/
cp ship.png   /opt/ctf2026/static/assets/
```

---

## 12. Docker (optionnel)

```bash
# Copier les images avant le build
cp island.png static/assets/
cp ship.png   static/assets/

# Construire et lancer
cp .env.example .env
nano .env          # Adapter les variables

docker compose up -d

# Initialiser la DB (première fois)
docker compose exec ctf python init_db.py
```

La base SQLite est persistée via le volume `./ctf.db`.

---

## 13. Sauvegarde

La totalité des données est dans un seul fichier SQLite :

```bash
# Sauvegarde simple
cp /opt/ctf2026/ctf.db /backup/ctf_$(date +%Y%m%d_%H%M%S).db

# Restauration
cp /backup/ctf_20260512_103000.db /opt/ctf2026/ctf.db
sudo systemctl restart ctf2026
```

---

## 14. Réinitialisation

### Réinitialiser toute la compétition (via l'interface admin)

Aller sur `/admin` → bouton **« Réinitialiser toute la compétition »**.

### Réinitialiser via la ligne de commande

```bash
# Depuis le répertoire du projet, venv activé
python init_db.py --force
```

Le flag `--force` supprime toutes les soumissions, tentatives et surcharges,
puis recharge les équipes et challenges.

---

## 15. Sécurité

| Point | Recommandation |
|---|---|
| `SECRET_KEY` | Générer avec `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_PASSWORD` | Mot de passe long et aléatoire |
| `DEBUG` | Toujours `false` en production |
| Base SQLite | Hors de la racine web, permissions 640 |
| Réponses | Jamais exposées dans le HTML, JS, attributs `data-*` ou fichiers statiques |
| Basic Auth | Comparaison en temps constant (`hmac.compare_digest`) pour éviter les timing attacks |

### Générer une SECRET_KEY

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copiez le résultat dans `.env`.
