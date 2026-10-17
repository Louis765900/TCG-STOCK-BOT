# ROADMAP V2 — POKÉPLACE MONITOR

Branche de travail : `pokeplace-v2` (ne jamais toucher `master`).
Légende : ⬜ à faire · 🔄 en cours · ✅ validé (tests + commit)

## Audit initial (état au départ)

Architecture : boucle asyncio unique (`src/main.py`) → cycles « recherche » (1 cycle sur
`SEARCH_INTERVAL`) et « watchlist » (relecture des fiches connues) → transition de stock
(`stock_state.py`) → alerte Discord (webhook ou bot). SQLite via aiosqlite. 6 enseignes
dédiées + boutiques Shopify/WooCommerce configurables. GUI PySide6 présente mais mise de côté.
Tests : `python tests/run_all.py` (11/11 au départ).

Points faibles relevés :

| # | Constat | Impact |
|---|---------|--------|
| A1 | Enseignes traitées **l'une après l'autre** dans chaque cycle | Latence de détection = somme des enseignes |
| A2 | `database.py` ouvre/ferme une connexion SQLite **à chaque requête**, sans WAL | Lenteur, verrous, I/O inutiles |
| A3 | Anti-doublon d'alerte = lecture puis écriture non atomiques | Risque de double alerte (concurrence) ; alerte « consommée » même si l'envoi Discord échoue |
| A4 | `envoyer_alerte` avale les erreurs et ne renvoie rien | Impossible de savoir si une alerte est partie |
| A5 | Pas de mesure de durée de cycle / latence par enseigne | Pilotage à l'aveugle |
| A6 | Pas de stock par magasin ni par département | Fonctionnalité absente |
| A7 | Un seul canal Discord, pas de routage par enseigne/catégorie | Peu configurable |
| A8 | Catégories limitées à Pokémon/One Piece scellé FR | Pas d'extension (Lorcana, Magic, Yu-Gi-Oh…) |

## P1 — Fondations (fiabilité, vitesse, anti-doublons)

- ✅ **C1 — Socle performance & fiabilité**
  - ✅ C1.1 DB : connexion partagée + WAL + index (A2)
  - ✅ C1.2 Cycles : enseignes en parallèle, durée de cycle mesurée (A1, A5)
  - ✅ C1.3 Anti-doublon atomique + restitution si l'envoi échoue + session HTTP Discord réutilisée (A3, A4)
  - ✅ C1.4 Tests : concurrence (10 détections → 1 alerte), échec d'envoi, parallélisme (12/12)
- ✅ **C2 — Cadence de détection** : pause calculée pour viser une *période* (`MIN_SLEEP`–`MAX_SLEEP` incluent la durée du cycle) + plancher `MIN_CYCLE_GAP`.
  - ⬜ C2b (reporté) : boucles indépendantes par enseigne, watchlist chaude/froide.
- ✅ **C3 — Robustesse des lectures** : rupture confirmée après `RUPTURE_CONFIRMATIONS` (=2) lectures « indisponible » consécutives → plus de faux restock après un glitch de page.
  - ⬜ C3b (reporté) : persistance de l'état de santé des enseignes.
- ✅ **C4 — Observabilité** : `database.stats_enseignes` (taux OK, durée moyenne/p95 sur 24 h) + commande Discord `/status`.
  - ⬜ C4b (reporté) : journal structuré JSON.

## P1 — Discord

- ✅ **C5 — Routage des alertes (par enseigne)** : `DISCORD_WEBHOOKS_BY_STORE` / `DISCORD_CHANNELS_BY_STORE`, repli sur le canal par défaut.
  - ⬜ C5b : routage par catégorie de produit et rôles par catégorie (dépend de C11).
- ✅ **C6 — Watchlist depuis Discord** : `/watch`, `/unwatch`, `/list` (paginé, filtre enseigne) ; `/add` et `/watchlist` conservés.

## P1 — Enseignes françaises

- ✅ **C7 — Audit scraper par scraper** : `tools/audit_scrapers.py` + `docs/AUDIT_SCRAPERS_V2.md`. Fonctionnels (testés en réel) : Auchan, LudiJeux, RelicTCG, CoinBarons. Défaillants : Leclerc (403), Cultura, King Jouet, Smyths, La Grande Récré.
  - ⬜ C7b : rétablir Leclerc (à vérifier depuis la machine de production), nouvelles sources pour Cultura / La Grande Récré (avec C8).
- ⬜ **C8 — Nouvelles enseignes FR** (Fnac, Carrefour, Micromania, Philibert…) — uniquement après test concluant.

## P2 — Magasins & géographie

- ⬜ **C9 — Stock en magasin** (modèle de données `stock_magasin`, scrapers compatibles).
- ⬜ **C10 — Départements** : abonnement par département, filtre des alertes.

## P2 — Catalogue

- ⬜ **C11 — Nouvelles catégories** : Lorcana, Magic, Yu-Gi-Oh, Dragon Ball, accessoires (classeurs, sleeves).
- ⬜ **C12 — Tableau de bord / GUI** réaménagé sur les nouvelles fonctions.

## Règles de conduite

- Aucun scraper n'est déclaré « fonctionnel » sans test réel concluant.
- Aucune modification de configuration de production ni déploiement.
- Un commit descriptif par chantier ; cette roadmap est mise à jour à chaque fois.

## Journal des chantiers validés

### C1 — Socle performance & fiabilité
- `database.py` : une connexion SQLite partagée par base/boucle (mode WAL, `busy_timeout`),
  thread daemon, `fermer()` pour l'arrêt propre ; nouvel index ; `reserver_alerte()` atomique.
- `main.py` : cycles recherche/watchlist exécutés enseigne par enseigne **en parallèle**
  (concurrence watchlist désormais par enseigne) ; la durée du cycle est loguée.
- `_alerter` : réservation atomique avant envoi ; si Discord échoue, la réservation est rendue
  (plus de faux « doublon » qui étouffe un vrai restock).
- `discord_webhook.py` : `envoyer_alerte` renvoie un booléen ; session aiohttp partagée
  (pas de poignée de main TLS par alerte).
- Tests : `test_cycles_paralleles` (nouveau), cas concurrence/échec dans `test_main_logic`.
- Aucun scraper réel testé dans ce chantier (hors périmètre) ; aucune donnée utilisateur modifiée
  (schéma inchangé hors index).

### C2 + C3 — Cadence & confirmation des ruptures
- `stock_state.calculer_pause` : le temps passé à scraper est déduit de la pause (cadence stable).
- `stock_state.ConfirmationRupture` : état mémoire ; tant que la rupture n'est pas confirmée,
  la base reste « en stock » (aucune transition, aucun faux restock). Réglable via `.env`.
- Tests : `test_stock_state` (confirmation, pause), `test_main_logic` (glitch isolé vs rupture réelle).

### C4 — Observabilité
- `stats_enseignes()` agrège `cycle_logs` (taux de succès, durée moyenne, p95, dernier statut).
- Commande `/status` (lecture seule, éphémère) ; ajoutée à `/help`.
- Test : `test_observabilite` (13/13 au total). `.env.example` complété (MIN_CYCLE_GAP, RUPTURE_CONFIRMATIONS).

### C5 — Routage Discord par enseigne
- `config` : deux tables optionnelles (webhook / salon par enseigne) ; `.env.example` documenté.
- `discord_webhook` : `webhook_pour()` / `canal_pour()` avec repli par défaut ; l'enseigne est transmise jusqu'au transport.
- Test : `test_discord.test_routage_par_enseigne` (routage, repli, envoi sans webhook par défaut). 13/13.
- Aucune configuration de production modifiée : comportement identique tant que les variables sont vides.

### C6 — Watchlist depuis Discord
- `/watch <url>` (alias `/add`), `/unwatch <url>` : réservés à l'administrateur (ou `DISCORD_OWNER_ID`) ; `/list [page] [enseigne]` ouvert à tous, 10 produits par page.
- `normaliser_url` : https uniquement, pas d'identifiants ni de port exotique, pas de caractères de contrôle, longueur ≤ 500 ; fragment et paramètres de suivi (`utm_*`, `fbclid`…) retirés → pas de doublon. L'hôte doit correspondre exactement à une enseigne connue (dédiées + Shopify/Woo configurées) et l'enseigne doit être active (`ENABLED_STORES`), sinon refus explicite.
- Prise en compte par le moteur : la watchlist est relue en base à chaque cycle. **Correctif important** : colonne `manuel` (migration automatique, testée sur ancienne base) ; les produits ajoutés à la main ne sont plus purgés par le filtre JCC (le titre déduit de l'URL pouvait les faire supprimer en silence).
- Tests : `test_watchlist_discord` (validation/SSRF, doublons, /unwatch, pagination, filtre, échappement Markdown, moteur : restock détecté sur un ajout manuel, produit retiré non surveillé). 14/14.
- Limite connue : les commandes slash elles-mêmes (couche discord.py) ne sont pas testées contre l'API Discord réelle ; seule la logique sous-jacente et `est_autorise` le sont. Le titre d'un ajout manuel est déduit de l'URL (pas de lecture de la fiche à l'ajout).

### C7 — Audit et fiabilisation des scrapers
- Audit réel (17/10/2026) de 9 enseignes : 4 fonctionnelles, 5 défaillantes (détail et limites dans `docs/AUDIT_SCRAPERS_V2.md`).
- Sécurité : redirections HTTP validées saut par saut (même site, https, pas d'IP/localhost) ; domaines centralisés dans `store_domains.py`.
- Fiabilité : détection de blocage sans faux positifs (RelicTCG était classé « captcha » à tort) ; statut `not_found` ; stock prudent (Woo non achetable à 0 € ne compte plus, Auchan sans signal = non en stock) ; parseur Cultura réécrit (non exploitable en pratique) ; vendeurs directs Cultura.
- Outils : `tools/audit_scrapers.py` (lecture seule, sans Discord, sans proxy payant), `scrapers/registry.py`.
- Tests : `test_detection_blocage`, `test_scrapers_parsing` (16/16 au total). Aucun envoi Discord pendant les tests réseau.
