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
- ⬜ **C4 — Observabilité** : commande `/status` détaillée, latence p50/p95 par enseigne, journal structuré.

## P1 — Discord

- ⬜ **C5 — Routage des alertes** : un salon/webhook par enseigne ou catégorie, rôles par catégorie, mise en forme enrichie.
- ⬜ **C6 — Commandes** : `/watch`, `/unwatch`, `/list`, `/stats`, filtres par enseigne.

## P1 — Enseignes françaises

- ⬜ **C7 — Audit scraper par scraper** (test réel de chaque enseigne, statut honnête dans le README).
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
