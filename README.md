<div align="center">

# 🃏 TCG-STOCK-BOT

**Surveillance de stock en temps réel des cartes Pokémon & One Piece (françaises)
sur les boutiques en ligne, avec alertes Discord instantanées.**

Boosters · Displays · ETB · Coffrets · Bundles — uniquement du **scellé**, uniquement en **français**.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Async](https://img.shields.io/badge/asyncio-aiohttp-009688)
![Discord](https://img.shields.io/badge/Alertes-Discord-5865F2?logo=discord&logoColor=white)
![Tests](https://img.shields.io/badge/tests-11%2F11-success)

</div>

---

## ✨ Fonctionnalités

- 🔎 **Multi-enseignes** — surveille en parallèle plusieurs boutiques FR (Leclerc, Auchan, et boutiques spécialisées Shopify/WooCommerce).
- 🎯 **Filtrage intelligent** — ne retient que le **JCC scellé** (Pokémon + One Piece), en français. Élimine jouets, livres, figurines, imports JP/EN, autres TCG…
- ⚡ **Alertes Discord** — nouveauté, **restock** et **baisse de prix**, avec image, prix, vendeur, liens d'achat, recherche EAN (Google/eBay/Cardmarket) et **graphique d'historique de prix**.
- 🛡️ **Anti-blocage robuste** — empreinte navigateur (curl_cffi), backoff automatique, filet de secours via proxies, mise en veille des enseignes récalcitrantes.
- 🏷️ **Vendeurs officiels vs revendeurs** — pastille ✅/🔁, ou masquage complet des marketplaces.
- 🔁 **24h/24** — boucle résiliente qui se relance toute seule ; résumé quotidien sur Discord.

---

## 📁 Structure du projet

```
TCG-STOCK-BOT/
├── src/                  # ⚙️  Cœur du bot (mode terminal)
│   ├── main.py           #     Boucle principale (point d'entrée)
│   ├── config.py         #     Configuration (.env + couches)
│   ├── database.py       #     Stockage SQLite (stocks, prix, historique)
│   ├── filter_utils.py   #     Filtre « est-ce du JCC scellé FR ? »
│   ├── http_fetch.py     #     Requêtes HTTP (curl_cffi + repli aiohttp)
│   ├── proxy_fetch.py    #     Filet de secours anti-bot (proxies en cascade)
│   ├── discord_webhook.py#     Construction & envoi des alertes
│   ├── discord_bot.py    #     Passerelle bot (boutons, commandes /)
│   ├── price_chart.py    #     Graphiques d'historique de prix
│   └── scrapers/         #     Un module par type de source
├── desktop/              # 🖥️  Application graphique (PySide6/QML) — mise de côté
├── docs/                 # 📚  Documentation détaillée
│   ├── JOURNAL.md        #     Avancement, chantier par chantier (langage simple)
│   ├── GUIDE_TOM.md      #     Guide utilisateur final
│   └── PACKAGING.md      #     Empaquetage en .exe (archivé)
├── tests/                # ✅  Suite de tests (python tests/run_all.py)
├── tools/                # 🔧  Diagnostics (sondes scrapers / proxies)
├── lancer_bot.bat        # ▶️  Lanceur Windows tout-en-un (24h/24)
├── requirements.txt
└── .env.example          #     Modèle de configuration
```

> 💡 L'application de bureau (`desktop/`) existe et fonctionne, mais la **voie de
> livraison retenue est le mode terminal** (plus simple à maintenir).

---

## 🚀 Démarrage rapide

### Le plus simple (Windows)
Double-clique **`lancer_bot.bat`**. Au premier lancement, il installe les dépendances
tout seul, puis démarre le bot et le **relance automatiquement** s'il s'arrête.

### Manuel (toutes plateformes)
```bash
# 1. Dépendances
pip install -r requirements.txt

# 2. Configuration
cp .env.example .env        # (Windows : Copy-Item .env.example .env)
#   puis renseigne DISCORD_WEBHOOK_URL dans .env

# 3. Lancement
python src/main.py
```

> ℹ️ **Pas besoin de navigateur** : les enseignes par défaut sont servies en HTTP/JSON
> (« mode léger »). Le bot tourne en boucle — laisse la fenêtre ouverte (Ctrl+C pour arrêter).

### Obtenir un webhook Discord
Discord → ton salon → ⚙️ *Modifier le salon* → *Intégrations* → *Webhooks* →
*Nouveau webhook* → *Copier l'URL*. Colle-la dans `.env`.

---

## ⚙️ Configuration (`.env`)

| Clé | Rôle | Défaut |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | Où envoyer les alertes (mode simple) | *(obligatoire\*)* |
| `DISCORD_BOT_TOKEN` + `DISCORD_CHANNEL_ID` | Mode **bot** : débloque les boutons cliquables | — |
| `DISCORD_ALERT_ROLE_ID` | Rôle à mentionner (notification instantanée) | — |
| `ENABLED_STORES` | Enseignes surveillées (séparées par virgules) | Auchan,Leclerc,LudiJeux,RelicTCG,CoinBarons |
| `MIN_SLEEP` / `MAX_SLEEP` | Pause (s) entre deux cycles | 60 / 180 |
| `DEAL_DROP_PERCENT` | Seuil d'alerte « baisse de prix » (%) | 15 |
| `MASQUER_REVENDEURS` | N'alerter que sur les vendeurs officiels | false |
| `HEARTBEAT_INTERVAL` | Résumé périodique Discord (s ; 0 = off) | 86400 |
| `RUN_ONCE` | `true` = un seul cycle puis arrêt (test) | false |
| `SCRAPINGBEE_KEY` / `ZENROWS_KEY` / `CRAWLBASE_TOKEN` | Filet de secours anti-bot (optionnel) | — |

<sub>\* Soit le webhook, soit le couple bot+salon doit être renseigné.</sub>

---

## 🧠 Comment ça marche

1. **Cycle de découverte** — interroge chaque enseigne sur une liste de mots-clés, filtre le JCC scellé FR, et enregistre les produits.
2. **Cycles de surveillance** — re-vérifie chaque produit connu ; n'alerte que sur une **vraie transition** (rupture → stock) ou une baisse de prix.
3. **Anti-blocage en couches** :
   - 🥇 **curl_cffi** imite l'empreinte TLS/HTTP2 de Chrome (la plupart des protections sont transparentes) ;
   - 🥈 **backoff** automatique sur throttling temporaire (429/503) ;
   - 🥉 **proxies de secours** (ScrapingBee → ZenRows → Crawlbase) en dernier recours seulement ;
   - 🛡️ **mise en veille** d'une enseigne qui échoue en boucle (l'IP récupère).

---

## 🛒 Sources prises en charge

| Type | Mécanisme | Exemples |
|---|---|---|
| Grande distribution | API JSON interne | Leclerc, Auchan |
| Boutiques **Shopify** | API publique `suggest.json` | LudiJeux, RelicTCG |
| Boutiques **WooCommerce** | Store API `wc/store/v1` | CoinBarons |

> Ajouter une boutique Shopify/WooCommerce ne demande **pas de code** : vérifie-la avec
> `python tools/tester_boutique.py <domaine>`, puis ajoute-la dans `.env`
> (`SHOPIFY_SHOPS` / `WOO_SHOPS` + `ENABLED_STORES`).

---

## ✅ Tests & diagnostics

```bash
python tests/run_all.py            # suite complète (doit afficher 11/11)
python tools/diag_scrapers.py      # sonde live des enseignes
python tools/diag_proxy.py         # teste le filet de secours proxy
```

---

## 🤖 Mode bot & commandes (optionnel)

Renseigne `DISCORD_BOT_TOKEN` + `DISCORD_CHANNEL_ID` pour activer les **boutons**
d'achat et les **commandes slash** : `/help`, `/stats`, `/watchlist`, `/add <url>`,
`/pause`, `/resume`. Détails dans [docs/GUIDE_TOM.md](docs/GUIDE_TOM.md).

> ⚠️ **Sécurité** : `.env` (jeton Discord, clés API) ne doit **jamais** être publié.
> Il est ignoré par git.

---

## 📚 Documentation

- 📒 [docs/JOURNAL.md](docs/JOURNAL.md) — l'histoire du projet, chantier par chantier.
- 👤 [docs/GUIDE_TOM.md](docs/GUIDE_TOM.md) — guide pour l'utilisateur final.
- 📦 [docs/PACKAGING.md](docs/PACKAGING.md) — empaquetage de l'appli graphique (archivé).
