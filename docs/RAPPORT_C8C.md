# Rapport C8C — Fiabilisation de la découverte et des alertes Shopify / WooCommerce

Vérifications réelles du 17 octobre 2026 (une IP, sans proxy, base temporaire, envoi Discord
remplacé par un enregistreur : **0 alerte réelle**). Tests : 19/19.

> **Correctif (C8C.1)** : le point 3 ci-dessous décrivait un retour « en stock avant / en stock
> après, absence ≥ 24 h » comme un RESTOCK. C'était une erreur de conception : une réapparition
> n'est pas un changement de disponibilité. Elle n'envoie plus de RESTOCK (voir
> `docs/RAPPORT_C8C1.md`). De même, l'échec de l'alerte attendue dans le « scénario combiné »
> vient d'une carte à l'unité mal choisie comme cible, pas d'un défaut du moteur d'alertes.

## Risques identifiés puis traités

| # | Risque (constat) | Traitement |
|---|---|---|
| 1 | La recherche prédictive Shopify renvoie `variants: []` : un produit annoncé « disponible » pouvait ne l'être que par une variante endommagée/étrangère. Des fiches « [ENDOMMAGÉ] … » existent aussi comme produits à part. | Tout produit JCC annoncé disponible par la recherche est **vérifié sur sa fiche** (`.js`) avec la règle commune des variantes ; fiche illisible ⇒ produit **écarté** (jamais annoncé sans preuve). Le filtre global rejette les titres « endommagé / abîmé / occasion / damaged / reconditionné » avant toute liste blanche. |
| 2 | Règles de stock/prix différentes selon le chemin (recherche, catalogue, lot, fiche). | Une seule règle (`lire_variantes`) pour Shopify, une seule (`_produit`) pour Woo ; la recherche indisponible affiche `N/A` au lieu d'un prix non vérifiable par variante. Test de **cohérence des 3 chemins** (découverte = lot = fiche, + recherche vérifiée). |
| 3 | Un produit « disparu » était forcé en rupture : à son retour, **faux restock** même s'il était en stock avant de disparaître. | La disparition **ne modifie plus le stock** (dernier état réel conservé). Au retour : il était en rupture → vraie transition, alerte ; il était en stock → alerte **seulement** si l'absence a duré ≥ `REAPPARITION_ALERTE_HEURES` (24 h) ; sinon trou technique, aucune alerte ; retour en rupture → jamais d'alerte. `/list` et `/stats` montrent ⚫ (disparu) et ne comptent plus un disparu « en stock ». |
| 4 | Activer le catalogue complet sur LudiJeux / RelicTCG créerait des centaines de « nouveautés » (catalogue déjà en rayon). | **Cycle d'adoption silencieux** : le moteur mémorise le mode de découverte de chaque enseigne (table `meta`) ; au passage « recherche → collections » le premier cycle réussi enregistre tout **sans alerte**. Le repli collections → recherche ne rend pas silencieux et ne rétrograde pas le marqueur ; un cycle vide n'écrit rien (l'adoption reste due). Le catalogue complet devient le **défaut** pour toutes les boutiques Shopify (`SHOPIFY_CATALOGUE_COMPLET=*`), opt-out possible. |
| 5 | Plafond de vérification (40) trop bas : 44 produits légitimes écartés en mode repli (détecté par la vérification réelle). | Plafond relevé à 150, test dédié. |

## Vérifications réelles

* **Activation du catalogue complet sur installation « existante »** (LudiJeux, RelicTCG,
  Dracaugames d'abord suivies en mode recherche : 147 produits) : bascule en collections ⇒
  **646 produits (+499), 0 alerte**, marqueurs enregistrés ; 2ᵉ découverte : 0 nouveauté ;
  watchlist de 646 produits : 42 requêtes, 2,7 s, **0 alerte / 0 restock / 0 rupture**.
* **Détection d'une vraie nouveauté après adoption** : un produit en stock retiré de la base puis
  redécouvert déclenche bien une alerte `NOUVEAUTE` (test isolé réel ; dans le scénario
  combiné, l'alerte ne s'est pas produite, vraisemblablement parce que le stock du produit
  choisi avait changé entre-temps — non démontré).
* **Recherche vérifiée vs catalogue** (mode repli) : 0 écart de stock sur 143 produits
  comparables (LudiJeux 56, RelicTCG 49, Dracaugames 38).
* La vérification par fiche n'a **modifié aucun stock réel** : aucun cas « variante abîmée
  seule » n'était en rayon pendant les tests. Ce cas (observé sur le catalogue lors de C8B :
  « Comme Neuf » rupture / « Endommagé » disponible) est couvert par les tests, pas par un
  événement réel.

## Tests ajoutés (19/19)

`test_fiabilite_c8c` : titres dégradés, découverte vérifiée (variante abîmée seule ⇒ rupture,
rupture ⇒ `N/A` sans requête, fiche bloquée ⇒ écarté, hors JCC non vérifié), plafond,
cohérence Shopify (5 cas : nominal, rupture, variante abîmée, deux variantes, langue étrangère)
et Woo (4 cas), adoption (300 produits ⇒ 0 alerte ; vraie nouveauté ensuite ; repli ; cycle vide ;
boutique en mode recherche inchangée ; enseigne sans mode inchangée ; restock toujours détecté),
**migration d'une ancienne base** (données, historique de prix et dernière alerte préservés,
idempotence, moteur opérationnel sur lignes migrées), réglages (ancien `SHOPIFY_CATALOGUE_COMPLET=
Dracaugames` respecté, opt-out vide) et affichage ⚫. `test_lot_monitors` mis à jour (disparition
sans rupture, retour court/long/en rupture).

## Compatibilité

* Schéma : nouvelles colonne `disparu_depuis` et table `meta`, ajoutées par migration
  idempotente ; produits, prix, historiques, drapeaux `manuel` et `derniere_alerte` intacts.
* Réglages existants honorés : `SHOPIFY_CATALOGUE_COMPLET` explicite, `WATCHLIST_LOT`,
  `DEAL_DROP_PERCENT`, `ENABLED_STORES`… Seul changement de défaut : catalogue complet pour toutes
  les boutiques Shopify (protégé par l'adoption). `.env.example` mis à jour.
* Comportement modifié à connaître : un produit disparu garde son dernier stock (plus de
  rupture forcée) ; les titres « occasion/endommagé » ne sont plus jamais suivis.

## Ce qui reste incertain

* Pendant le cycle d'adoption, une vraie nouveauté apparue exactement à ce moment est
  enregistrée sans alerte (compromis assumé : précision > quantité).
* Le seuil de 24 h pour un retour après disparition est un choix de conception, non validé sur
  des cas réels (aucune disparition réelle observée).
* La détection automatique des collections repose sur leurs noms (univers Pokémon / One Piece,
  exclusions de mots entiers) ; une boutique aux noms atypiques peut exiger
  `SHOPIFY_COLLECTIONS`. Les produits hors collections sont relus individuellement.
* Variantes : la liste de mots exclus (`SHOPIFY_VARIANTES_EXCLUES`) est lexicale ; un état
  décrit autrement (ex. « Boîte cabossée ») ne serait pas reconnu.
* WooCommerce : produits « variables » ignorés/`inconnu` (stock par déclinaison indisponible).
* Non couvert ici : Carrefour (règles propres), instore.
