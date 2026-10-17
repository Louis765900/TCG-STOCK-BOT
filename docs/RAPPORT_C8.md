# Rapport C8 (partie 1) — Extension des monitors français

Date des mesures : 17 octobre 2026. Une seule IP (poste Windows), sans proxy ni service payant,
requêtes espacées, **aucune alerte Discord réelle** (envoi remplacé par un enregistreur pendant
tous les tests de bout en bout). Aucun CAPTCHA ni protection contourné.

## Résultat en une phrase

**Fnac : inaccessible** (DataDome). **Carrefour : exploitable** via les pages de rayon et les
fiches produit (la recherche est protégée). **Dracaugames** (Shopify, spécialiste TCG français)
ajouté comme enseigne de remplacement. Aucune autre grande enseigne testée n'était exploitable.

## Sources testées

| Enseigne | Source | Résultat observé | Décision |
|---|---|---|---|
| **Fnac** | Recherche `SearchResult/ResultList.aspx` | HTTP 403, en-tête `x-datadome: protected`, iframe `captcha-delivery` | Bloqué |
| Fnac | Accueil, `sitemapindex-master.xml` (pourtant cité par robots.txt), fiche produit | Tous en 403 DataDome | **Bloqué : aucun connecteur** |
| **Carrefour** | Recherche `/s?q=` | HTTP 429, `cf-mitigated: challenge` (Cloudflare) | Non utilisée |
| Carrefour | Accueil, fiches `/p/<slug>-<EAN>` | HTTP 200, HTML serveur, JSON-LD `Product` avec offres par vendeur | **Utilisée (fiches)** |
| Carrefour | Rayon `/r/jeux-jouets/jeux-societe-puzzle/jeux-classiques+licence,pokemon` (+ `one-piece`) | HTTP 200, 85 résultats Pokémon (3 pages de 30), 15 One Piece, rendu serveur | **Utilisée (découverte)** |
| Carrefour | Rayons génériques `+licence,pokemon` sans catégorie | 35 cartes dont les 5 premières sont des produits sponsorisés hors sujet ; mélange jouets/figurines | Écartée (bruit) |
| **Dracaugames** | Shopify `/products.json` et `.js` | HTTP 200, catalogue complet (ruptures incluses) | **Utilisée** |
| Micromania | Recherche Demandware | HTTP 200 mais corps « Request unsuccessful. Incapsula incident » | Bloqué (Imperva) |
| Joué Club | Recherche | 404 (application Angular, prix et stocks rendus côté client). Page marque `/nos-heros/pokemon.html` : 52 produits dont 2 cartes ; fiches avec JSON-LD | Écartée : découverte inexploitable |
| Philibert | Recherche | 302 vers l'accueil | Écartée |
| Maxi Toys | Accueil | 403 DataDome | Bloqué |
| Cdiscount, Boulanger | Accueil | Page de 14 Ko / 400 (protection) | Non retenus |
| Ultrajeux | Recherche | 410 Gone | Écartée |

`robots.txt` de Carrefour n'interdit ni `/r/` ni `/p/` (il interdit `/b`, `/g`, `/webview`,
`/set-store`). Celui de Fnac n'interdit pas non plus les sitemaps, mais DataDome les bloque.

## Carrefour — fonctionnement

* **Découverte** (`CarrefourScraper.scraper_recherche`) : lecture des pages de rayon
  (2 licences × jusqu'à 4 pages, pause 1,5–3 s entre pages), pré-filtre sur le titre
  (`est_tcg_valide_local`), puis **lecture de la fiche de chaque candidat** : le rayon n'indique
  pas le stock, il n'est jamais présumé. Une fiche illisible écarte le produit.
* **Fiche** (`analyser_fiche`, fonction pure testée) : le JSON-LD liste chaque offre avec
  `seller` et `availability`.
  * **`en_stock`** = une offre « Carrefour » ou « Carrefour Livraison » est `InStock`.
  * **`rupture`** = Produit lu, aucune offre de livraison Carrefour en stock.
  * **`inconnu`** = JSON-LD `Product` absent ou illisible. Statut dédié `inconnu` : le moteur
    ne modifie pas l'état, n'alerte pas, et compte l'incident (si **toutes** les fiches d'une
    enseigne sont `inconnu`, elle passe en `parser_error` au lieu de rester « healthy »).
  * **Marketplace** : les marchands tiers ne comptent **jamais** comme stock Carrefour (leur
    prix n'est pas exposé) sauf `CARREFOUR_INCLURE_MARKETPLACE=true` ; dans ce cas le vendeur est
    le tiers, affiché 🔁 « revendeur » et masquable par `MASQUER_REVENDEURS`. « Carrefour » =
    vendeur officiel ✅.
  * **« Carrefour Drive » / `InStoreOnly`** : dépend du magasin → traité comme **non disponible
    en ligne**, signalé dans le champ `drive` pour le futur chantier « stock magasin ».
  * Prix : celui de l'offre Carrefour ; jamais celui d'un tiers ; `N/A` si absent ou ≤ 0.
  * Quantité : jamais inventée (`stock_quantity = None`).
* Politesse : 2 fiches simultanées maximum (`CONCURRENCE_WATCHLIST`, nouvel attribut respecté par
  le moteur), pause aléatoire 0,3–0,8 s par fiche ; un challenge/429 est classé `blocked` et la
  mise en veille automatique de l'enseigne s'applique.

### Mesures réelles (Carrefour)

| Mesure | Valeur |
|---|---|
| Cartes listées / candidats JCC / produits vérifiés | 31 vérifiés (rayon Pokémon + One Piece) |
| Durée d'un cycle de découverte | ≈ 23 s |
| Durée d'un cycle watchlist (31 fiches) | 11–15 s |
| Répartition | 4 en stock chez Carrefour, 12 en rupture côté Carrefour, 15 vendus **uniquement par des marchands tiers** (jamais d'alerte) |
| Cohérence recherche ↔ fiche (5 fiches) | 5/5 stock, 5/5 prix |

## Dracaugames — fonctionnement

Boutique Shopify : réutilise `ShopifyScraper`, avec un **nouveau mode « catalogue complet »**
(`/products.json`, 250 articles par page, repli sur la recherche classique si l'endpoint est
indisponible). Raison : la recherche prédictive **masque les produits épuisés** (constat : 120/120
« en stock » alors que la boutique compte plus de 636 articles Pokémon/One Piece en rupture) ; un
produit épuisé n'était donc jamais connu du bot. Le catalogue donne aussi le prix et le code-barres
des produits en rupture.

* La boutique vend ≈ 90 % de **cartes à l'unité** : ignorées (`product_type`) et **nouveau rejet
  global dans le filtre** des titres portant un numéro de carte (`105/086`, `TG07/TG30`), qui
  passaient jusque-là grâce au code d'extension. Les produits scellés restent valides (tests).
* Mesures : 127–152 produits scellés (≈ 87 en stock, ≈ 65 en rupture suivis), catalogue lu en
  6–15 s ; 8/8 fiches relues cohérentes (stock et prix) avec le catalogue. Le stock est géré par
  Shopify (`inventory_management=shopify`), donc `available` reflète l'inventaire.

## Intégration au moteur

* Registre : `scrapers/registry.py` (Carrefour), `store_domains.py` (`carrefour.fr`),
  libellés et couleurs (`product_format`), vendeurs directs Carrefour.
* **Amorçage silencieux par enseigne** (nouveau) : une enseigne sans aucun produit en base est
  découverte sans alerte, comme au premier lancement. Sans cela, activer Carrefour ou
  Dracaugames sur une installation existante aurait envoyé une alerte « Nouveauté » par produit
  déjà en rayon (≈ 150).
* Robustesse : une exception dans `scraper_produit` ne fait plus perdre le cycle de l'enseigne
  (la fiche est traitée `inconnu`) ; un prix non numérique dans une offre Carrefour ne plante plus
  (bug détecté par les tests).
* **Configuration** : `ENABLED_STORES` par défaut = Auchan, Leclerc, **Carrefour**, LudiJeux,
  RelicTCG, CoinBarons, **Dracaugames** (`config.py`, `.env.example`, README, réglages Windows
  d'exemple et placeholder de l'écran Réglages). **Les installations existantes qui définissent
  déjà `ENABLED_STORES` (`.env` ou `settings.json`) ne sont pas modifiées.**
  Nouvelles options : `CARREFOUR_INCLURE_MARKETPLACE`, `SHOPIFY_CATALOGUE_COMPLET`
  (défaut : Dracaugames).
* Discord : `/watch` accepte les URL Carrefour et Dracaugames (domaines reconnus ; `?s=<vendeur>`
  retiré pour Carrefour afin d'éviter les doublons).

## Tests

`python tests/run_all.py` : **17/17**. Nouveaux : `test_carrefour` (fiches : livraison/drive/
marketplace/option marketplace/aucune offre/prix invalide/`inconnu` ; listing ; découverte avec
fiche illisible ; moteur : `inconnu` ⇒ `parser_error` sans changement d'état ni alerte, erreur
réseau ⇒ aucune rupture, vrai restock ⇒ 1 alerte, amorçage par enseigne), catalogue Shopify
(types exclus, rupture suivie, repli), filtre (cartes à l'unité vs scellés).
Vérification réelle de bout en bout (moteur réel, base temporaire, Discord simulé) : amorçage de
158 produits sans alerte, watchlist (Carrefour 31 + Dracaugames 127) sans transition ni alerte,
2ᵉ découverte sans nouveauté.

## Limites (non vérifiées ou assumées)

* **Aucun restock Carrefour/Dracaugames réel n'a été observé** : la détection de transition est
  couverte par tests, pas par un événement réel.
* Interprétation de `schema.org/availability` de Carrefour (« Livraison » `InStoreOnly` ≠ achat en
  ligne possible) déduite des données, **non confirmée par un parcours de commande**.
* Le rayon Carrefour ne couvre que la catégorie « Jeux classiques » : un produit rangé ailleurs
  n'est pas découvert (il reste ajoutable avec `/watch`). La recherche étant challengée, aucune
  découverte par mot-clé.
* Carrefour peut durcir Cloudflare (volume, IP) : le connecteur s'arrêtera proprement
  (`blocked` → veille 1 h) mais ne contourne rien.
* Dracaugames : ≈ 127 fiches `.js` relues à chaque cycle (≈ 8 s). Les précommandes sont
  considérées « en stock » si Shopify les juge achetables.
* Mesures depuis une seule IP, à un instant donné.

## Améliorations possibles

1. Dracaugames/Shopify : lire l'état de stock directement dans `/products.json` (≈ 15 requêtes)
   au lieu de 127 fiches `.js` par cycle.
2. Carrefour : exploiter le champ `drive` pour le chantier « stock magasin / départements ».
3. Étendre le catalogue complet aux autres boutiques Shopify (LudiJeux, RelicTCG) pour suivre
   aussi leurs ruptures dès la découverte.
4. Joué Club / La Grande Récré (même plateforme Angular) : étudier l'API de leur moteur de
   recherche si elle est publique.

## Prochaines enseignes à intégrer

* **Boutiques spécialisées Shopify/WooCommerce françaises** (zéro code : `tools/tester_boutique.py`
  puis une ligne de config) — les plus rentables.
* **Joué Club / La Grande Récré** : après analyse de leur API publique.
* **Cultura** (parseur prêt, source de résultats inaccessible) : à reprendre si une API publique
  apparaît.
* À écarter tant que protégées : Fnac, Micromania, Maxi Toys, King Jouet, Smyths.
