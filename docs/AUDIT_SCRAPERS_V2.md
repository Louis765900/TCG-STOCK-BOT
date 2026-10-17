# Audit des scrapers — Chantier C7

Date des mesures : 17 octobre 2026, depuis un poste Windows (une seule IP, sans proxy ni service
payant). Outil : `python tools/audit_scrapers.py` (lecture seule, aucune alerte Discord, aucune
écriture en base). Mesures brutes reproductibles avec `--json`.

> **Ce qui est mesuré** : un état à un instant donné, depuis une IP. Un site « bloqué » ici peut
> répondre ailleurs (et inversement). « Fonctionnel » signifie : la recherche renvoie des produits
> pertinents, les URL/prix sont plausibles et la relecture de la fiche donne le même stock/prix.
> Ce n'est **pas** une preuve de détection de restock en conditions réelles (aucun restock réel n'a
> pu être observé pendant l'audit).

## Synthèse

| Enseigne | Active par défaut | Verdict | Cause principale |
|---|---|---|---|
| Auchan | oui | **FONCTIONNEL** | HTTP simple |
| LudiJeux (Shopify) | oui | **FONCTIONNEL** | API JSON publique |
| RelicTCG (Shopify) | oui | **FONCTIONNEL** | API JSON publique |
| CoinBarons (WooCommerce) | oui | **FONCTIONNEL** (après correction) | Store API publique |
| Leclerc | oui | **DÉFAILLANT (bloqué)** | HTTP 403 sur l'API de recherche |
| Cultura | non | **DÉFAILLANT** | Site refondu ; résultats chargés côté client ; rendu navigateur vide |
| King Jouet | non | **DÉFAILLANT (bloqué)** | DataDome (403 + challenge) |
| Smyths | non | **DÉFAILLANT (bloqué)** | Imperva « Pardon our interruption » |
| La Grande Récré | non | **DÉFAILLANT** | URL de recherche obsolète (redirige vers l'accueil) ; site refondu |

## Détail par enseigne

Légende : *Produits* = produits uniques trouvés avec 4 mots-clés (JCC = passent le filtre local
Pokémon/One Piece scellé FR) ; *Fiches* = fiches relues et comparées à la recherche.

| Enseigne | Produits (JCC) | En stock | Temps recherche | Fiches OK / stock cohérent / prix cohérent | Erreurs observées | Corrections apportées |
|---|---|---|---|---|---|---|
| Auchan | 39 (7) | 35 | ~1 s | 4/4 · 4/4 · 3/3 | Aucune. Présence de vendeurs **marketplace** (ex. coffret à 207 €, 1 077 €) : prix de revendeurs tiers | Stock : une tuile sans aucun signal était présumée « en stock » → désormais « non en stock » (la fiche tranche). Les revendeurs sont masquables via `MASQUER_REVENDEURS` |
| LudiJeux | 34 (12) | 29 | ~0,4 s | 4/4 · 4/4 · 4/4 | Aucune | — |
| RelicTCG | 34 (12) | 34 | ~0,4 s | 4/4 · 4/4 · 4/4 | Aucune dans le bot. Le JSON-LD de la page HTML expose le prix en centimes (« 21000 » pour 210 €) : sans effet, le bot lit l'API (210.00 correct) | — |
| CoinBarons | 177 (54) | 175 | ~2,5 s | 4/4 · 4/4 · 2/2 | **Faux positifs de stock** : 2 produits `is_in_stock=true` mais `is_purchasable=false` à **0 €** (« Lire la suite ») | Un produit n'est « en stock » que s'il est achetable ET a un prix > 0 ; prix 0 → `N/A` |
| Leclerc | 0 | – | 1,9 s | non testable | `HTTP 403` (page « 403 Forbidden » de 134 octets) sur `/api/rest/live-api/product-search`, alors que la page d'accueil répond 200. Aucun contournement tenté | Statut correctement classé `blocked` ; une fiche absente de l'API est désormais `not_found` (et non une erreur) |
| Cultura | 0 | – | ~40 s | non testable | Ancienne URL `recherche.html` → **404**. `/recherche?q=` renvoie une liste générique sans rapport (1 produit pertinent sur 99). `/search/results?q=` : aucune carte dans le HTML. Navigateur headless : page vide, titre « cultura.com » | Parseur réécrit pour les nouvelles cartes (`data-product-*` : EAN, prix, stock ; marketplace = revendeur) et validé sur HTML réel + test ; URL de recherche corrigée. **Reste inutilisable** tant que les résultats ne sont pas accessibles |
| King Jouet | 0 | – | ~98 s | non testable | DataDome : 403 + iframe `captcha-delivery` | Aucune (protection volontaire du site, non contournée) |
| Smyths | 0 | – | ~86 s | non testable | Imperva : page « Pardon our interruption » (6 Ko) | Aucune (idem) |
| La Grande Récré | 0 | – | ~40 s | non testable | `/catalogsearch/result/?q=` → **301 vers l'accueil** ; plus de page de recherche serveur (application Angular) ; essais d'autres chemins : 404 | Aucune : refonte nécessaire (hors périmètre C7) |

Les sélecteurs des scrapers **King Jouet, Smyths et La Grande Récré n'ont pas pu être vérifiés**
(aucun HTML produit atteint) : ils ne doivent pas être considérés comme fonctionnels.

## Corrections transverses (toutes testées)

1. **Redirections HTTP sécurisées** (`http_fetch.py`) : suivi manuel (5 sauts max) ; chaque saut doit
   rester sur le **même site**, en **https**, sans identifiants ni port exotique, et ne pas viser une
   adresse IP ou `localhost` (anti-SSRF / open-redirect). Sinon : statut `blocked`
   (`redirect_non_fiable`), jamais de requête vers la destination.
2. **Détection de blocage sans faux positifs** (`anti_bot_bypass.detecter_type_blocage`) : avant, la
   simple présence du mot « captcha » ou « datadome » dans une page (ex. reCAPTCHA d'une newsletter)
   la faisait classer « bloquée » — la page d'accueil de RelicTCG l'était à tort. Désormais :
   signatures fortes (iframe de challenge, `cf-chl`…) = blocage ; mentions faibles = blocage
   seulement si la page est courte et sans contenu produit.
3. **Statut `not_found`** (404/410) distinct des blocages et des timeouts : une fiche retirée ne
   dégrade plus la santé de l'enseigne et ne déclenche ni mise en veille ni faux « rupture ».
4. **Stock prudent** : Woo (achetable + prix), Auchan (pas de signal ⇒ non en stock), Cultura (seul
   « EN STOCK EN LIGNE » compte ; « disponible sous X jours » et précommande = non).
5. **Cultura marketplace** ajouté aux vendeurs directs connus (`product_format.VENDEURS_DIRECTS`).
6. Refactorisations sans changement de comportement : `store_domains.py` (domaines/hôtes, source
   unique), `scrapers/registry.py` (construction des scrapers partagée bot/audit).

## Outil de diagnostic

```
python tools/audit_scrapers.py                      # enseignes actives
python tools/audit_scrapers.py --all --browser      # toutes, avec Playwright
python tools/audit_scrapers.py --stores Auchan --samples 6 --json audit.json
```

Verdicts : FONCTIONNEL / PARTIEL / DÉFAILLANT / NON TESTÉ. Règles : recherche en statut ≠ ok ou 0
produit ⇒ défaillant ; résultats sans rapport avec la requête (< 5 % citent Pokémon/One Piece)
⇒ défaillant ; URL hors domaine, prix absents/aberrants, fiches illisibles, incohérences de
stock/prix recherche↔fiche ⇒ partiel. Le secours par proxy/scraping API est forcé à OFF.

## Limites de cet audit

- **Aucun restock réel observé** : la cohérence recherche↔fiche prouve la lecture, pas la
  détection d'une transition. Les transitions sont couvertes par des tests unitaires (C1–C3).
- Vérification **indépendante** du stock (page HTML publique) possible seulement pour RelicTCG
  (JSON-LD : stock concordant 4/4). Pour LudiJeux, CoinBarons et Auchan, la page produit n'expose
  pas de donnée structurée exploitable : seule la concordance API recherche ↔ API fiche est
  établie (la même source côté boutique).
- Échantillon de 4 fiches par enseigne, 4 mots-clés : indicatif, pas exhaustif.
- Pas de test sur plusieurs IP / opérateurs : le 403 de Leclerc et les blocages KingJouet/Smyths
  peuvent être propres à cette IP.
- Les prix « marketplace » d'Auchan (jusqu'à > 1 000 € pour un coffret) sont réels mais ceux de
  revendeurs tiers ; le bot les signale 🔁 ou les masque selon la configuration.

## Problèmes restants (par priorité)

1. **Leclerc** (active par défaut) : bloquée en 403 depuis cette IP — vérifier depuis la machine de
   production ; sinon envisager une source alternative légitime.
2. **Cultura / La Grande Récré** : nécessitent une nouvelle source de données (API publique
   éventuelle, flux produits) ; à traiter avec les nouveaux monitors (C8).
3. **King Jouet / Smyths** : protégées ; à laisser désactivées.
4. Fiches définitivement retirées (`not_found`) : jamais nettoyées automatiquement de la watchlist.
5. Stock Cultura « disponible sous X jours » volontairement traité comme indisponible : à
   reconsidérer si ce statut est jugé utile aux utilisateurs.
