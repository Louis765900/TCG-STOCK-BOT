# Rapport C8B — Optimisation des monitors Shopify / WooCommerce

Mesures du 17 octobre 2026, une seule IP, sans proxy, base temporaire, **envoi Discord remplacé
par un enregistreur (0 alerte réelle)**. Outil reproductible : `python tools/bench_monitors.py`
(requêtes HTTP réellement émises, durées, parité lot ↔ fiche).

## Principe

Avant : chaque cycle relisait **chaque produit suivi** (`/products/<h>.js`, ou `?slug=` en Woo).
Après : une **lecture groupée** (`scraper_lot`) lit le catalogue public une seule fois et en
déduit stock et prix de tous les produits suivis ; ce que le catalogue ne tranche pas est relu
individuellement. Le moteur (`main.cycle_watchlist`) combine les deux ; `WATCHLIST_LOT=false`
rétablit l'ancien comportement.

| Plateforme | Source groupée | Repli individuel |
|---|---|---|
| Shopify | collections « scellé Pokémon / One Piece » (`/collections/<h>/products.json`, 250 produits par requête, ruptures incluses), détectées automatiquement via `/collections.json` et mises en cache 6 h | `.js` pour tout produit absent des collections, sans variante, ou hors lot |
| WooCommerce | listes `search=<univers>` (déjà utilisées pour la découverte) + requêtes groupées `slug=a,b,c` pour les produits hors listes | `?slug=` unitaire (utilisé aussi en direct) |

## Mesures avant / après

### Par enseigne, cycle de watchlist (moyenne de 2 cycles)

| Enseigne | Produits suivis | Avant (req / durée) | Après (req / durée) | Parité lot ↔ fiche |
|---|---|---|---|---|
| Dracaugames | 127 → 250* | 127 / 9,8 s | **15 / 3,5 s** | 250/250 identiques |
| CoinBarons (Woo) | 53 | 53 / 5,8 s | **3 / 2,8 s** | 52/52 identiques |
| LudiJeux | 57 | 57 / 5,6 s | **14 / 1,6 s** | 56/56 identiques |
| RelicTCG | 50 | 50 / 3,5 s | **12 / 1,6 s** | 49/49 identiques |
| **Total** | | **287 req** | **44 req (−85 %)** | **407/407 (100 %)** |

\* Dracaugames : le nombre de produits suivis passe de 127 à 250 parce que la découverte par
collections trouve **tout le scellé** (le crawl de C8A, plafonné à 20 pages sur un catalogue de
plus de 10 000 articles, en manquait la moitié). Le coût par cycle baisse malgré tout.

### Moteur complet, 5 enseignes en parallèle (Carrefour inclus), 1 cycle de watchlist

| Mode | Requêtes | Durée du cycle | Alertes |
|---|---|---|---|
| Fiche par fiche (`WATCHLIST_LOT=false`) | 440 | 25,1 s | 0 |
| Lecture groupée | **76 (−83 %)** | **12,0 s (−52 %)** | 0 |

La durée restante est celle de Carrefour (31 fiches, 2 en parallèle, pauses de politesse), non
concernée par C8B.

### Découverte
Dracaugames : 20 req / 14,6 s (crawl partiel) → **16 req / 1,6 s** avec 250 produits (au lieu de
127). Les collections peuvent aussi servir aux autres boutiques Shopify (option
`SHOPIFY_CATALOGUE_COMPLET`, **non activée par défaut** : sur installation existante elle peut
déclencher quelques alertes « nouveauté » sur des produits déjà en rayon). Mesuré : LudiJeux
57 → **246** produits suivis (13 req), RelicTCG 50 → **149** (12 req) ; le suivi des ruptures
devient exhaustif.

## Fiabilité

* **Parité** : sur 407 produits, la lecture groupée donne exactement le même stock et le même prix
  que la fiche individuelle (bench `--parite`, exécuté dans la foulée).
* **Jamais deviné** : un produit absent du catalogue, sans variante exploitable, ou dont la
  lecture est ambiguë revient `a_verifier` et est relu individuellement ; une boutique qui bloque
  renvoie l'erreur à tous les produits sans multiplier les requêtes ; collections indisponibles ⇒
  tout est relu individuellement.
* **Pas de faux restock** : voir variantes et rupture confirmée ci-dessous ; les statuts
  `blocked`/`timeout`/`inconnu`/`not_found` ne modifient jamais l'état de stock.

### Variantes (stock par variante)
Constat réel sur Dracaugames : certains produits ont des variantes d'**état** (« Comme Neuf » /
« Endommagé »). L'ancien calcul (« une variante quelconque disponible ») annonçait « en stock »
un coffret dont seule la version abîmée restait, avec le prix de la version abîmée. Désormais
(`lire_variantes`) :
* les variantes d'état ou de langue non voulus sont **ignorées** pour le stock et le prix
  (`SHOPIFY_VARIANTES_EXCLUES` : endommagé, abîmé, occasion, used, damaged, anglais, japonais…) ;
* en stock = au moins une variante **retenue** disponible ; prix = la moins chère des retenues
  disponibles ; sans aucune variante ⇒ `inconnu` (jamais « en stock » par défaut) ;
* appliqué à l'identique au catalogue, au lot et à la fiche `.js` (prix en centimes géré).
WooCommerce : les produits **variables** (stock par déclinaison indisponible dans la Store API)
sont ignorés en découverte et `inconnu` en suivi (1 produit sur 136 chez CoinBarons).
`low_stock_remaining` (« plus que 4 en stock »), donnée réelle de la boutique, alimente
`stock_quantity` ; aucune quantité n'est jamais déduite.

### Produits disparus
* Un 404 isolé ne change rien. Un produit n'est déclaré **disparu** qu'après
  `DISPARU_MIN_ECHECS` (5) constats consécutifs **et** `DISPARU_APRES_HEURES` (6 h) d'absence
  continue ; il est alors marqué indisponible (sans alerte) et relu seulement toutes les
  `DISPARU_RECHECK_HEURES` (6 h) ; s'il revient en stock, c'est un vrai restock (compteurs remis à
  zéro). Nouvelles colonnes `introuvables`, `introuvable_depuis`, `prochaine_verif` (migration
  automatique, données existantes intactes).
* Une enseigne dont la majorité des fiches sont introuvables/inconnues passe en `parser_error`
  (plus de « healthy » trompeur).

### Prix
* `N/A` n'écrase plus le dernier prix connu (la référence de comparaison était perdue).
* **Baisse de prix** : alerte « DEAL » seulement si le **même** nouveau prix est lu
  `PRIX_CONFIRMATIONS` (2) fois de suite ; le prix en base reste l'ancien tant que la baisse n'est
  pas confirmée. Un prix glitché qui revient à la normale ne déclenche rien. Coût : un cycle de
  retard sur un vrai deal ; `PRIX_CONFIRMATIONS=1` rétablit l'alerte immédiate.
* L'historique de prix n'ajoute plus un point à chaque cycle : seulement si le prix ou le stock
  change, ou après 6 h (base plus légère, graphiques inchangés dans leur lecture).

## Tests (18/18)

Nouveau `test_lot_monitors` : variantes (état, langue, centimes, prix invalides, sans variante),
sélection des collections (mot entier : « Mugiwara » n'est pas un « mug »), lot Shopify
(3 requêtes pour 6 produits, cache des collections, repli, boutique bloquée, collections en 404),
lot Woo (3 requêtes pour 6 produits dont 2 hors liste, variable, not_found, boutique bloquée),
moteur (seuls les produits non tranchés sont relus, `WATCHLIST_LOT=false`, disparition à seuil,
absence de fausse rupture, retour en stock ⇒ restock, relecture espacée), historique sans
doublons. `test_main_logic` couvre la confirmation de baisse et le glitch de prix.

## Limites et points de vigilance

* **Fraîcheur du catalogue** : `products.json` n'est pas mis en cache par le CDN
  (`cf-cache-status: DYNAMIC`) et la parité est parfaite sur 407 produits ; en revanche aucun
  restock réel n'a été chronométré, donc un éventuel décalage de quelques secondes à minutes de
  Shopify entre catalogue et fiche n'est pas exclu (non mesuré).
* `products_count` de `collections.json` est inexact (469 annoncé / 70 réels) : il n'est utilisé
  que pour ignorer une collection vide. La détection automatique repose sur les noms de
  collections (univers Pokémon / One Piece, exclusions : unité, gradé, accessoire, japonais…) ;
  `SHOPIFY_COLLECTIONS` permet de la forcer.
* Un produit hors des collections suivies reste correct mais coûte une requête individuelle.
* La découverte par recherche prédictive (boutiques non passées en collections) ne voit pas les
  variantes : un « nouveau produit » dont seule la version abîmée est disponible pourrait être
  annoncé à tort ; passer la boutique en `SHOPIFY_CATALOGUE_COMPLET` supprime ce cas.
* Le lot réduit les requêtes mais lit des pages plus grosses (jusqu'à 250 produits) : charge
  globale bien inférieure, volume par requête supérieur.
* Carrefour n'est pas concerné (fiches uniquement).

## Améliorations possibles

1. Passer LudiJeux / RelicTCG en `SHOPIFY_CATALOGUE_COMPLET` après une première exécution
   silencieuse (suivi exhaustif des ruptures, découverte plus rapide).
2. Chronométrer la fraîcheur du catalogue sur un vrai restock.
3. Adapter le lot à d'autres plateformes (PrestaShop avec flux, Magento) lors de l'ajout de
   nouvelles enseignes.
