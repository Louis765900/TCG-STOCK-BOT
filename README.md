# 🛒 TCG-STOCK-BOT

Bot qui **surveille les stocks** de produits Pokémon dans plusieurs magasins en ligne
et **envoie une alerte Discord** dès qu'un article est disponible, avec le lien d'achat.

> 📒 L'avancement du projet est raconté simplement dans [JOURNAL.md](JOURNAL.md).

---

## ✅ Ce qu'il te faut avant de commencer

1. **Python 3.10 ou plus récent** — https://www.python.org/downloads/
   (Sur Windows, coche bien **"Add Python to PATH"** pendant l'installation.)
2. **Git** (pour récupérer le code) — https://git-scm.com/downloads
3. Un **salon Discord** avec un **webhook** (voir l'étape 4 plus bas).

---

## 🚀 Installation pas à pas

### 1. Récupérer le code
```bash
git clone <URL_DU_DEPOT> TCG-STOCK-BOT
cd TCG-STOCK-BOT
```
*(Si tu as déjà le dossier, ouvre juste un terminal dedans.)*

### 2. Créer un environnement Python isolé
Ça évite de mélanger les dépendances avec le reste de la machine.

**Windows (PowerShell) :**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Mac / Linux :**
```bash
python3 -m venv venv
source venv/bin/activate
```
> 💡 Tu sauras que c'est activé quand tu vois `(venv)` au début de la ligne.

### 3. Installer les dépendances
```bash
pip install -r requirements.txt
playwright install chromium
```
> La 2ᵉ ligne télécharge le navigateur utilisé pour les sites protégés. C'est normal
> que ce soit un peu long la première fois.

### 4. Configurer le bot (fichier `.env`)
Copie le modèle puis remplis-le :

**Windows :**
```powershell
Copy-Item .env.example .env
```
**Mac / Linux :**
```bash
cp .env.example .env
```

Ouvre `.env` et renseigne au minimum **l'adresse du webhook Discord** :
```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxx/yyy
```

**Comment obtenir un webhook Discord ?**
Dans Discord → ta chaîne → ⚙️ *Modifier la chaîne* → *Intégrations* → *Webhooks*
→ *Nouveau webhook* → *Copier l'URL du webhook*. Colle cette URL dans `.env`.

### 5. Lancer le bot
```bash
python main.py
```
Le bot tourne en boucle et envoie les alertes sur Discord. Laisse la fenêtre ouverte.

---

## ⚙️ Réglages utiles (dans `.env`)

| Réglage | À quoi ça sert | Défaut |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | Où envoyer les alertes | *(obligatoire)* |
| `MIN_SLEEP` / `MAX_SLEEP` | Temps d'attente (secondes) entre 2 tours de surveillance | 60 / 180 |
| `REQUEST_TIMEOUT_MS` | Temps max pour charger une page (ms) | 30000 |
| `RUN_ONCE` | `true` = fait **un seul** tour puis s'arrête (pratique pour tester) | false |
| `LOG_LEVEL` | Niveau de détail des messages (`INFO` ou `DEBUG`) | INFO |
| `SEARCH_KEYWORDS` | Mots-clés cherchés, séparés par des virgules | liste intégrée |

> Les autres réglages (anti-bot, proxies…) ont des valeurs par défaut qui marchent.
> Pas besoin d'y toucher pour démarrer.

---

## 🤖 Activer les boutons « Acheter » (mode bot — optionnel)

Par défaut le bot envoie les alertes par **webhook** (sans boutons). Pour avoir des
**boutons** dans les alertes (« 🛒 Acheter » + fondation autobuy), il faut créer un
**bot Discord** (gratuit). C'est facultatif : sans ça, tout fonctionne quand même.

1. Va sur https://discord.com/developers/applications → **New Application**.
2. Onglet **Bot** → **Add Bot** → **Reset Token** → **copie le token**.
   → colle-le dans `.env` : `DISCORD_BOT_TOKEN=...`
3. Onglet **OAuth2 → URL Generator** : coche `bot`, puis la permission
   **Send Messages**. Copie l'URL générée, ouvre-la, et **ajoute le bot à ton serveur**.
4. Dans Discord, active le **Mode développeur** (Paramètres → Avancés), puis
   **clic droit sur ta chaîne → Copier l'identifiant du salon**.
   → colle-le dans `.env` : `DISCORD_CHANNEL_ID=...`
5. Relance `python main.py`. Si tu vois « Mode bot Discord activé », c'est bon ✅.

> ⚠️ Le **token du bot est un secret** : ne le partage jamais, ne le mets pas sur
> GitHub. Le fichier `.env` ne doit pas être publié.

### (Optionnel) Être notifié instantanément : ping d'un rôle
Pour qu'une alerte te **mentionne** (et déclenche une notif sur ton téléphone) :
1. Crée un rôle sur ton serveur (ex. `@drop`) et attribue-le-toi.
2. Mode développeur activé → **clic droit sur le rôle** (Paramètres serveur → Rôles)
   → **Copier l'identifiant**.
3. Colle-le dans `.env` : `DISCORD_ALERT_ROLE_ID=...`

Désormais chaque alerte stock commence par `@drop` → notification immédiate.

### Commandes disponibles dans Discord (mode bot)
Une fois le bot connecté, tape `/` dans ta chaîne pour les voir :
| Commande | Rôle |
|---|---|
| `/help` | Affiche toutes les commandes |
| `/stats` | Produits surveillés, en stock, état des alertes |
| `/watchlist` | Liste des produits suivis |
| `/add <url>` | Ajouter un produit à surveiller |
| `/pause` / `/resume` | Couper / réactiver les alertes (sans arrêter le bot) |

> Les commandes apparaissent quelques secondes après le démarrage du bot
> (« commandes slash prêtes » dans la console).

---

## ❓ Questions fréquentes

**« Je veux juste tester vite, sans attendre des heures. »**
Mets `RUN_ONCE=true` dans `.env`, lance `python main.py` : il fait un seul tour et s'arrête.

**« `python` n'est pas reconnu. »**
Python n'est pas dans le PATH. Réinstalle-le en cochant *"Add Python to PATH"*,
ou essaie `py` au lieu de `python` sur Windows.

**« `playwright install` échoue / le navigateur ne se lance pas. »**
Relance `playwright install chromium`. Vérifie ta connexion internet (gros téléchargement).

**« Je n'ai aucune alerte Discord. »**
1. Vérifie que `DISCORD_WEBHOOK_URL` est bien collée dans `.env`.
2. Lance avec `LOG_LEVEL=DEBUG` pour voir ce qui se passe.
3. Certains magasins sont protégés (voir [JOURNAL.md](JOURNAL.md)) : c'est normal que
   certains soient bloqués pour l'instant.

**« Comment l'arrêter ? »**
Dans la fenêtre du terminal, appuie sur **Ctrl + C**.

**« Comment vérifier que tout marche après une modif ? »**
Lance la suite de tests : `python tests/run_all.py` → doit afficher « réussis ».

**« Comment le faire tourner 24h/24 ? »**
Utilise **`lancer_bot.bat`** (double-clic) : il lance le bot **et le relance tout seul**
s'il s'arrête (crash, coupure réseau…). Laisse la fenêtre ouverte.
Une **IP maison** (box internet) passe mieux les protections qu'un serveur en ligne —
c'est donc l'idéal pour ce bot.

> 💡 Le bot poste un petit **résumé quotidien** sur Discord (« 💓 résumé ») pour
> prouver qu'il tourne. Règle la fréquence avec `HEARTBEAT_INTERVAL` (0 = désactivé).
> Pour un démarrage automatique à l'allumage du PC : Planificateur de tâches Windows
> → nouvelle tâche → action « démarrer un programme » → `lancer_bot.bat`.

---

## 🗂️ Organisation du projet (pour s'y retrouver)

| Fichier / dossier | Rôle |
|---|---|
| `main.py` | Le chef d'orchestre : lance la boucle de surveillance. |
| `scrapers/` | Un fichier par magasin (comment lire ses pages). |
| `anti_bot_bypass.py` | Le "déguisement" pour les sites protégés. |
| `discord_webhook.py` | Construit et envoie les alertes Discord. |
| `product_format.py` | Met en forme les infos produit (nom, prix, image…). |
| `database.py` | Mémorise les stocks/prix (fichier SQLite). |
| `config.py` | Lit les réglages depuis `.env`. |
| `JOURNAL.md` | L'histoire du projet, chantier par chantier. |
