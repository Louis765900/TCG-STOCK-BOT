# Rapport C8C.1 — Validation des alertes

Tests : 20/20. Distinction explicite entre ce qui est **simulé** (tests automatisés) et ce qui a
été **réellement vérifié** sur les boutiques (17 octobre 2026, une IP, sans proxy, envoi Discord
remplacé par un enregistreur : 0 alerte réelle).

## 1. Réapparition ≠ changement de disponibilité

**Problème (introduit en C8C).** Une fiche déclarée « disparue » qui revenait en stock après
≥ 24 h déclenchait un `RESTOCK`, même si le produit était déjà en stock avant de disparaître :
aucune disponibilité n'avait changé.

**Règle désormais appliquée** (`main._traiter_resultat_watchlist`). Le stock en base est le
dernier état *réel* connu (la disparition ne le modifie pas) ; seule sa comparaison avec la
lecture actuelle dit s'il y a eu changement :

| Dernier état réel | Lecture au retour | Résultat |
|---|---|---|
| rupture | en stock | **RESTOCK** (vraie transition, même si la fiche a disparu entre-temps) |
| en stock | en stock | **aucun RESTOCK**. Réapparition comptée et journalisée ; alerte distincte « Réapparu » seulement si `ALERTER_REAPPARITION=true` et absence ≥ `REAPPARITION_ALERTE_HEURES` (24 h). Désactivée par défaut |
| en stock | rupture | chemin normal (rupture confirmée sur 2 lectures, sans alerte) |
| rupture | rupture | rien |

`StoreReport.reapparitions` compte les retours par enseigne ; le libellé Discord « Réapparu » est
distinct de « Restock ». `/list` affiche ⚫ pour un produit disparu.

## 2. L'alerte manquante du « scénario combiné » de C8C

**Cause (reproduite avec diagnostics, données réelles).** Le produit choisi comme cible,
« (DRI 007) Rosélia de Cynthia – … Carte », est une **carte à l'unité**. Il était entré en base
via la recherche prédictive (mode initial) ; en mode collections, le scraper l'exclut
correctement (`product_type` « Cartes à l'Unité ») : `redécouvert par le scraper: []`. Aucune
alerte n'était donc due. Ce n'était pas un défaut du moteur d'alertes, mais :
* un **défaut de mon test** (cible mal choisie) ;
* une **vraie fuite du filtre** : les codes de carte entre parenthèses sans dénominateur
  (« (DRI 007) », « (MEP 009) ») passaient `est_tcg_valide_local`, donc des cartes seules
  pouvaient être suivies. Corrigé (`_CODE_CARTE_PAREN_RE` : 3–4 lettres + espace + 3 chiffres ;
  les codes de set des produits scellés « (ME05) », « (EV06.5) », « (ETB) » ne sont pas touchés).

## 3. Tests d'intégration (SIMULES)

`tests/test_integration_alertes.py` : une fausse boutique Shopify (collections, recherche,
fiches `.js`) et une fausse boutique WooCommerce évoluent dans le temps, avec le **vrai moteur,
les vrais scrapers et une vraie base** ; chaque étape vérifie la liste **exacte** des alertes.
Le temps est simulé en modifiant les dates d'absence en base ; la **déclaration de disparition est
faite par le moteur lui-même**.

Shopify : première découverte silencieuse → produit « abîmé seul » vu en rupture dès la recherche →
catalogue qui grossit (30 produits déjà en rayon) + bascule collections = **0 alerte** (cartes
seules non suivies) → vraie nouveauté en stock = **exactement 1 `NOUVEAUTE`**, même après
plusieurs cycles de découverte et de watchlist → nouveauté en rupture = 0, puis en stock =
**1 `RESTOCK`** → variante abîmée seule = 0, puis version neuve = **1 `RESTOCK`** → fiche
« [ENDOMMAGÉ] » et cartes seules = jamais d'alerte → rupture isolée d'une lecture (glitch) = 0, vraie
rupture puis retour = **1 `RESTOCK`** → boutique bloquée = 0 alerte, états inchangés →
réapparition d'un produit en stock = 0 (`restocks == 0`, `reapparitions == 1`) → réapparition d'un
produit qui était en rupture = **1 `RESTOCK`** → retour en rupture = 0 → option
`ALERTER_REAPPARITION` = 1 alerte `REAPPARITION` (jamais `RESTOCK`), et 0 si absence courte.
Bilan final : exactement `NOUVEAUTE nouveau`, `RESTOCK bientot`, `RESTOCK neuf-ko`,
`RESTOCK etb`, `RESTOCK display`, sans doublon.

WooCommerce : nouveauté = 1 alerte ; produit non achetable à 0 €, produit variable, prix nul = 0 ;
produit qui devient achetable = 1 `RESTOCK` ; restock classique = 1 ; réapparition = 0.

**Les tests détectent bien les régressions** : 8 mutations du code, chacune réintroduisant un bug
(réapparition → RESTOCK, adoption supprimée, regex de carte supprimée, disparition → rupture
forcée, variantes non filtrées, rupture sans confirmation, recherche non vérifiée, Woo non
achetable compté en stock), sont **toutes détectées**. Deux mutations avaient d'abord échappé au
test (disparition simulée par écriture directe en base ; pas de variante abîmée à la première
découverte) : le test a été corrigé en conséquence.

## 4. Vérifications RÉELLES

* Installation simulée en mode recherche sur LudiJeux, RelicTCG, Dracaugames (175 produits, **0
  carte à l'unité suspecte en base**), bascule en collections : **0 alerte**, cycles suivants 0.
* Pour chaque boutique, un produit **scellé en stock** retiré de la base puis redécouvert
  déclenche **exactement 1 alerte `NOUVEAUTE`** (LudiJeux : Display Pokémon EV02 ; RelicTCG :
  Booster Méga-Évolution ; Dracaugames : Coffret Collection Illustration EV06.5), toujours 1
  après un 2ᵉ cycle, aucune autre alerte.

## 5. Ce qui n'est PAS vérifié

* Aucune réapparition ni disparition **réelle** de fiche n'a été observée : ces comportements
  sont démontrés en simulation uniquement.
* Aucun vrai restock chronométré sur ces boutiques (les restocks sont simulés).
* Le seuil de 24 h de l'option `ALERTER_REAPPARITION` n'est pas validé sur des cas réels.
* La détection des cartes seules reste lexicale (formats `NNN/NNN`, `TG07/TG30`, `(ABC 123)`) ;
  un format de numérotation inédit pourrait passer.
