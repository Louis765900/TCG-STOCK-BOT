# 📒 Journal du projet TCG-STOCK-BOT

Ce fichier raconte, simplement, **tout ce qui est fait sur le bot**, chantier par chantier.
Le but : qu'on comprenne tout sans être informaticien. On avance étape par étape.

---

## 🎯 C'est quoi le bot, en une phrase ?

Un robot qui **surveille les magasins en ligne** et qui **prévient sur Discord**
dès qu'une carte/produit Pokémon est **en stock**, avec un lien pour l'acheter.

---

## 🧱 Chantier 1 — Trouver la porte d'entrée de chaque magasin

**Date :** 12 juin 2026

### Ce qu'on cherchait
Avant de coder, il faut savoir **comment chaque magasin nous laisse entrer**.
Image simple : chaque site est une maison. Certaines portes sont **grandes ouvertes**,
d'autres ont un **videur** à l'entrée (un "anti-bot" qui bloque les robots).

J'ai donc **frappé à la porte des 6 magasins** pour voir lesquelles s'ouvrent facilement.

### Ce que j'ai trouvé

| Magasin | La porte est… | Videur ? | On fait quoi ? |
|---|---|---|---|
| **Auchan** | 🟢 Grande ouverte | Aucun | Le plus facile. On lit directement la page. |
| **Grande Récré** | 🟢 Grande ouverte | Aucun | Facile aussi. On lit directement la page. |
| **Cultura** | 🔴 Fermée | Cloudflare + DataDome | Difficile. Il faudra le "vrai navigateur" (plus tard). |
| **King Jouet** | 🔴 Fermée | Cloudflare + DataDome | Difficile. Pareil, navigateur. |
| **Smyths** | 🔴 Fermée | Imperva | Difficile. Pareil, navigateur. |
| **Leclerc** | 🔴 Fermée | DataDome | Difficile. Pareil, navigateur. |

### La bonne nouvelle 🎉
- **2 magasins sur 6 (Auchan + Grande Récré)** s'ouvrent **sans aucun effort** :
  pas besoin de robot compliqué, on lit la page comme un humain le ferait. C'est
  **rapide** (moins d'1 seconde) et **ça casse rarement**.
- Sur Auchan, la page donne déjà **tout** ce dont on a besoin pour une belle fiche :
  le **nom**, le **prix**, une **image en haute qualité**, si c'est **en stock ou non**,
  et la **référence** du produit.

### Ce que ça veut dire pour la suite
- On commence par **Auchan** et **Grande Récré** : gains faciles et solides.
- Les 4 magasins protégés (Cultura, King Jouet, Smyths, Leclerc) seront gérés
  **plus tard**, avec le "vrai navigateur" déguisé (chantier 6). C'est plus lourd,
  donc on s'en occupe en dernier.

### Décision importante 💡
On **arrête de tout faire avec le gros navigateur**. Pour les magasins ouverts, une
simple lecture de page suffit : c'est **plus rapide, plus fiable, et gratuit**.

---

---

## 🧱 Chantier 2 — Une fiche produit complète et solide

**Date :** 12 juin 2026

### Le problème d'avant
Avant, pour savoir le prix ou si c'était en stock, le bot "devinait" en cherchant
des petits bouts de texte dans la page (des « étiquettes maison »). Souci : dès que
le magasin change la déco de sa page, les étiquettes bougent et le bot se trompe.

### L'idée (beaucoup plus maligne)
Presque tous les magasins rangent les infos de leurs produits dans une **fiche
cachée standardisée** dans la page (on appelle ça *schema.org* : JSON-LD et microdata).
C'est comme une **étiquette officielle** collée sur chaque produit, **pareille partout**.
Au lieu de deviner, le bot **lit directement cette étiquette officielle**.

### Ce que j'ai fait
1. Créé un **lecteur d'étiquettes** (fichier `structured_data.py`) qui sait lire ces
   fiches cachées et en sort : **nom, prix, ancien prix, image, en stock ou non,
   code-barres (EAN), marque, vendeur, note**.
2. Branché ce lecteur dans le bot : il lit d'abord l'étiquette officielle, et **ne
   devine que si elle manque** (sécurité).
3. Fait passer ces nouvelles infos jusqu'à **l'alerte Discord**, qui affiche
   maintenant en plus la **Marque** et le **Vendeur**.

### Vérifié pour de vrai ✅
- Testé sur des exemples + sur une **vraie fiche Auchan** : le bot récupère bien le
  nom, la marque (« POKEMON »), le prix, l'image et le stock, tout seul.
- Si une page n'a pas d'étiquette, **le bot ne plante pas**, il devine comme avant.

### En clair
La fiche produit est maintenant **plus complète** (marque, vendeur, code-barres) et
**plus solide** : elle résiste mieux aux changements de design des magasins.

> 📝 Note : je n'ai **pas touché à l'anti-bot**, comme demandé.

---

---

## 🧱 Chantier 3 — Prévenir seulement quand le stock change

**Date :** 12 juin 2026

### L'idée toute simple
On ne veut **pas** être prévenu « c'est en stock » à chaque tour de surveillance
(ce serait du spam). On veut une alerte **seulement au moment où ça change** :
quand un produit **passe d'indisponible à disponible** (un *restock*). C'est *le*
moment important.

Image : une lampe. On ne sonne pas tant qu'elle est allumée. On sonne **au moment
précis où elle s'allume**. Le bot se souvient de l'état d'avant (dans sa mémoire,
la base de données) et le compare à maintenant.

### Ce que j'ai trouvé en arrivant
Une bonne partie était **déjà là** et bien faite 👍. J'ai surtout **renforcé** et
corrigé deux choses :

1. **Le piège du "site qui bloque".**
   Quand un magasin nous bloque, il répond en gros « rien à montrer », ce que le bot
   pourrait confondre avec « plus de stock ». J'ai vérifié (et prouvé par un test)
   que le bot **ignore** ces blocages : il ne déclenche **pas** de fausse rupture,
   donc **pas** de fausse alerte « de retour ! » juste après.

2. **L'alerte restock qui partait à la poubelle.**
   Avant, après une alerte, le bot se taisait **6 heures** pour le même produit.
   Problème : un produit très demandé peut **re-stocker l'après-midi même** — et on
   l'aurait **raté**. J'ai remplacé ce silence de 6 h par une **petite sécurité de
   10 minutes** (réglable), juste assez pour éviter les doublons, sans rater un vrai
   retour en stock.

### Ce que j'ai fait, concrètement
- Créé une **petite règle claire et testée** (fichier `stock_state.py`) qui décide :
  *restock* (→ on alerte), *rupture* (→ on note seulement), ou *rien*.
- Branché la surveillance dessus.
- Mis en place la **fenêtre anti-doublon de 10 min** (réglage `ALERT_DEDUP_WINDOW`).

### Vérifié pour de vrai ✅
Un test automatique rejoue 3 situations sur une vraie mini-base de données :
- Produit en stock **bloqué** → reste en stock, **aucune fausse alerte**. ✅
- Produit indispo qui **revient en stock** → **1 seule alerte** restock. ✅
- Produit qui **reste** en stock au tour suivant → **pas de doublon**. ✅

### En clair
Le bot prévient **pile au bon moment** (un vrai retour en stock), **ne se trompe
pas** quand un site bloque, et **ne rate plus** un restock qui revient vite.

---

---

## 🧱 Chantier 4 — Préparer Discord pour les boutons

**Date :** 12 juin 2026

### Le problème à anticiper
On veut bientôt des **boutons** dans les alertes (« 🛒 Acheter », etc.). Mais le
système d'envoi actuel (un « webhook », une simple adresse qui poste des messages)
**ne sait pas faire de boutons**. Seul un **vrai bot Discord** le peut.

### L'idée : un aiguillage automatique
J'ai mis en place un **interrupteur intelligent** dans l'envoi des alertes :
- Si **aucun bot** n'est configuré → on continue **exactement comme avant** (webhook,
  le lien d'achat reste écrit dans le message). **Rien ne change pour toi aujourd'hui.**
- Si un **bot** est configuré (plus tard) → les alertes partent **avec les boutons**
  (Acheter, Google, eBay), sans rien réécrire.

Image : une prise électrique qui accepte deux types de fiches. On branche ce qu'on a ;
ça marche dans les deux cas.

### Ce que j'ai fait
- Ajouté deux réglages **optionnels** dans la config : `DISCORD_BOT_TOKEN` et
  `DISCORD_CHANNEL_ID` (vides par défaut = mode webhook actuel).
- Réécrit l'envoi Discord pour **choisir tout seul** le bon canal (bot ou webhook).
- Préparé les **boutons** d'achat (prêts à l'emploi dès qu'un bot sera branché).
- Documenté tout ça dans `.env.example`.

### Vérifié pour de vrai ✅
- Sans bot → message **sans** bouton (comme avant). ✅
- Avec bot → message **avec** les boutons Acheter / Google / eBay. ✅
- Le reste du bot démarre toujours normalement. ✅

### En clair
Aujourd'hui : **aucun changement visible**, tout marche comme avant. Mais le terrain
est **prêt** : le jour où on branche le mini-bot (chantier 5), les boutons
apparaissent tout seuls. **Pas besoin de rien casser.**

---

---

## 🧱 Chantier 5 — Le mini-bot Discord (boutons + fondation autobuy)

**Date :** 12 juin 2026

### Ce qu'on voulait
Des **boutons** dans les alertes : un bouton « 🛒 Acheter » qui ouvre la page du
produit, et préparer le futur **autobuy** (acheter en un clic, plus tard).

### Le truc important à comprendre
- Un **bouton-lien** (qui ouvre une page) : facile, ça marche dès qu'un bot est
  branché. C'est ce que tu voulais pour la V1.
- Un **bouton qui déclenche une action** (l'autobuy) : il faut un programme qui
  **écoute les clics** en direct. C'est la nouveauté de ce chantier.

### Ce que j'ai fait
- Ajouté un petit **programme qui écoute** (fichier `discord_bot.py`) : il se
  connecte à Discord et **réagit aux clics** sur le bouton « Autobuy ».
- Ajouté les **boutons** aux alertes : 🛒 Acheter, Google, eBay, et ⚡ Autobuy.
- Pour l'instant, cliquer « Autobuy » **répond en privé avec le lien d'achat**
  (l'achat 100 % automatique viendra plus tard — il y a une étape banque/3-D Secure
  à valider à la main, on en reparlera).
- Astuce solide : le bouton retrouve le lien **tout seul** dans l'alerte, donc il
  **marche encore même si on redémarre** le bot.
- Branché le bot pour qu'il tourne **en même temps** que la surveillance, et
  **seulement si** tu as configuré un bot (sinon, rien ne change).
- Écrit la **notice d'installation du bot** dans le README (étapes simples).

### Vérifié pour de vrai ✅
- Les 4 boutons apparaissent bien (Acheter / Google / eBay / Autobuy). ✅
- Le clic « Autobuy » répond **en privé** avec le bon lien. ✅
- S'il n'y a pas de lien, **pas de plantage**, message de repli. ✅
- Tout le programme démarre normalement. ✅

### Ce que TOI tu dois faire (une seule fois)
Pour activer les boutons : créer un bot gratuit sur le site de Discord et coller 2
infos dans `.env` (le *token* et l'*identifiant du salon*). **Tout est expliqué pas
à pas dans le README**, section « Activer les boutons ».

### En clair
Le bot peut maintenant **afficher des boutons** et **écouter les clics**. Le bouton
« Acheter » est prêt pour la V1, et la **mécanique de l'autobuy est en place** — il
ne restera qu'à brancher l'achat réel plus tard.

---

---

## 🧱 Chantier 6 — Le navigateur seulement quand c'est nécessaire

**Date :** 12 juin 2026

### Le gâchis qu'on corrige
Jusqu'ici, le bot ouvrait un **navigateur déguisé** (lourd, lent) pour **tous** les
magasins — même Auchan et La Grande Récré qui, eux, ouvrent leur porte **sans
problème**. C'est comme sortir le 4×4 pour aller chercher le pain à 50 mètres.

### L'idée
Pour chaque magasin, on choisit le bon outil :
- **Magasin ouvert** (Auchan, La Grande Récré) → une **simple requête** (rapide,
  légère, ~50× plus rapide que le navigateur).
- **Magasin blindé** (Cultura, King Jouet, Smyths, Leclerc) → on garde le
  **navigateur déguisé** (l'anti-bot), mais **seulement pour eux**.

Et si jamais un magasin « ouvert » se met à bloquer un jour → le bot **bascule tout
seul** sur le navigateur en secours. Ceinture **et** bretelles.

### Ce que j'ai fait
- Créé un **récupérateur léger** (fichier `http_fetch.py`) pour les requêtes simples.
- Centralisé le choix de l'outil dans **un seul endroit** : un interrupteur
  `http_first` par magasin. Auchan et La Grande Récré = ✅ requête simple d'abord.
- Le navigateur + anti-bot reste **inchangé**, juste réservé aux sites blindés.

### Vérifié pour de vrai ✅
- Auchan : page de recherche récupérée en requête simple (534 Ko). ✅
- Auchan : une **fiche produit complète récupérée SANS navigateur** (prix + marque
  obtenus directement). ✅
- Les sites blindés sont bien marqués « navigateur ». ✅
- Si le navigateur manque, le bot **ne plante pas** (échec propre). ✅

### En clair
Le bot est maintenant **beaucoup plus rapide et plus fiable** sur les 2 magasins
faciles, et n'utilise le gros navigateur que là où c'est vraiment nécessaire.
**C'est exactement ce que tu voulais : ne pas surinvestir dans l'anti-bot.**

---

## 🎉 Bilan V1

Les 6 chantiers sont faits :
1. ✅ Repérage des 6 magasins (qui est ouvert, qui est blindé).
2. ✅ Fiche produit complète et solide (données standardisées).
3. ✅ Alerte uniquement quand le stock change vraiment.
4. ✅ Envoi Discord prêt pour les boutons.
5. ✅ Mini-bot Discord avec boutons + fondation autobuy.
6. ✅ Requête rapide pour les sites ouverts, navigateur en secours.

**Prochaines pistes possibles** (quand tu voudras) : faire fonctionner pour de bon
les 4 sites blindés, et avancer sur le vrai autobuy (panier pré-rempli).

---

## 🧱 Chantier 7 — S'attaquer aux 4 sites blindés

**Date :** 13 juin 2026

### La méthode (la même qu'au chantier 1)
Avant de forcer la porte avec le navigateur déguisé, j'ai cherché si chaque magasin
avait une **petite porte de service** : une adresse qui renvoie directement les
données (souvent l'autocomplétion / la recherche interne), bien moins surveillée
que la grande porte.

### Ce que j'ai trouvé

| Magasin | Résultat | Décision |
|---|---|---|
| **Leclerc** | 🟢 **Porte de service trouvée !** Une vraie liste de produits en clair (prix, stock, vendeur, code-barres). | **Réglé** : on lit ça directement, sans navigateur. |
| **Cultura** | 🟠 Une adresse répond… mais **par intermittence** (le videur finit par bloquer) **et elle ne filtre même pas** par mot-clé. Pas fiable. | Reste sur le navigateur de secours. |
| **King Jouet** | 🔴 Videur (DataDome) qui bloque tout. | Reste sur le navigateur de secours. |
| **Smyths** | 🔴 Videur (Imperva) qui bloque tout. | Reste sur le navigateur de secours. |

### Ce que j'ai fait
- **Leclerc est désormais réglé proprement** : un nouveau scraper lit sa liste de
  produits en direct. Testé pour de vrai → **42 produits** récupérés avec prix,
  stock, vendeur et code-barres, **sans ouvrir le navigateur**. ✅
- Ajouté l'outil pour lire ce genre de liste (fichier `http_fetch.py`, partie JSON).

### Le bilan honnête
- **3 magasins sur 6 marchent maintenant en mode rapide** : Auchan, La Grande Récré
  **et Leclerc**.
- **Cultura, King Jouet et Smyths** ont une protection sérieuse qu'on ne contourne
  pas en douceur. Ils restent branchés sur le navigateur déguisé — qui **peut**
  parfois passer, mais **sans garantie**. Je préfère te le dire clairement plutôt
  que te promettre que ça marche à tous les coups.

### Correctif (13 juin 2026, après test grandeur nature)
Sur Leclerc, plusieurs vendeurs proposent le même produit à des prix différents. Le
bot affichait l'offre « par défaut » (pas toujours la moins chère). Corrigé : il
prend désormais **l'offre EN STOCK la moins chère** (le vrai bon prix). Exemple
vérifié : ME03 affiché à **26,62 €** au lieu de 33,95 €.

### En clair
On gagne **Leclerc** (un gros magasin) en mode rapide et fiable. Pour les 3 derniers,
les protections sont trop solides pour une solution propre et gratuite aujourd'hui —
on les garde en « best effort » via le navigateur.

---

## 🧱 Chantier 8 — Chercher d'autres magasins (bilan)

**Date :** 13 juin 2026

J'ai sondé une dizaine de magasins (Micromania, Fnac, Cdiscount, Carrefour,
Maxi Toys, JouéClub, Philibert, UltraJeux…) pour trouver des portes ouvertes.

**Résultat honnête : aucune nouvelle porte ouverte cette fois.** Les grandes
enseignes sont toutes protégées (mêmes videurs : Cloudflare, DataDome, Imperva), et
les boutiques spécialisées affichent leurs produits **en JavaScript** (page vide
côté serveur → il faudrait le navigateur).

**Décision :** je n'ajoute pas un magasin fragile juste pour faire du nombre. Mieux
vaut 3 magasins solides que 6 bancals. On reviendra ajouter des boutiques **Shopify**
(qui ont une porte de service standard) quand tu m'en donneras quelques-unes précises.

---

## 🧱 Chantier 9 — Le bot tourne tout seul, 24h/24

**Date :** 13 juin 2026

### Le but
Que le bot **ne s'arrête jamais sans qu'on le sache**, et qu'il **reparte tout seul**
en cas de pépin.

### Ce que j'ai fait
1. **La boucle ne meurt plus.** Avant, une erreur inattendue pouvait tout arrêter.
   Maintenant, si un cycle plante, le bot **note l'erreur et continue** au cycle
   suivant — comme une voiture qui cale mais redémarre aussitôt.
2. **Redémarrage automatique** (`lancer_bot.bat`) : si le programme s'arrête vraiment
   (crash, coupure), ce script **le relance tout seul** après 15 secondes. Tu double-
   cliques une fois, et ça tourne en boucle.
3. **Résumé quotidien sur Discord** (« 💓 résumé ») : le bot poste chaque jour un
   bilan — combien de produits surveillés, combien d'alertes, quelles enseignes vont
   bien ou pas. Comme ça tu **sais qu'il est vivant** sans rien vérifier.

### Vérifié pour de vrai ✅
- Le résumé s'affiche avec les bons chiffres et le bon état des enseignes. ✅
- Le message part par le bon canal (bot ou webhook). ✅
- Tout démarre normalement. ✅

### En clair
Le bot est maintenant **autonome** : il se relève tout seul, et il te fait un petit
« coucou » quotidien pour dire que tout va bien. Tu peux le laisser tourner et
l'oublier. Règle la fréquence du résumé avec `HEARTBEAT_INTERVAL` (0 = désactivé).

---

## 🧱 Chantier 10 — Être prévenu sur le téléphone (ping)

**Date :** 13 juin 2026

### Le problème
Une alerte qui arrive dans Discord, c'est bien… mais si tu ne regardes pas l'écran
à ce moment-là, tu la rates. Pour un produit qui part en 30 secondes, c'est trop tard.

### La solution
Le bot peut maintenant **te mentionner** (`@drop`) au début de chaque alerte stock.
Une mention déclenche une **notification Discord sur ton téléphone** → tu es prévenu
**instantanément**, même si tu ne regardais pas.

### Ce que j'ai fait
- Ajouté un réglage **optionnel** `DISCORD_ALERT_ROLE_ID` : l'identifiant d'un rôle
  (ex. un rôle `@drop` que tu t'attribues).
- Si renseigné, chaque alerte commence par la mention de ce rôle. Si vide : pas de
  ping (rien ne change).
- Le **résumé quotidien**, lui, **ne ping jamais** (pas de spam inutile).
- Expliqué dans le README comment créer le rôle et récupérer son identifiant.

### Vérifié pour de vrai ✅
- Avec un rôle configuré → l'alerte contient bien la mention. ✅
- Sans rôle → aucune mention. ✅
- Le résumé quotidien ne mentionne jamais personne. ✅

### En clair
Tu peux maintenant être **alerté en temps réel sur ton téléphone** dès qu'un produit
tombe en stock. C'est *la* fonctionnalité clé pour ne plus rater un drop.

---

## 🧱 Chantier 11 — Ne plus s'acharner sur les sites bloqués

**Date :** 13 juin 2026

### Le gâchis
Les 3 sites blindés (Cultura, King Jouet, Smyths) ouvrent un **navigateur lourd**
à chaque cycle… pour se faire jeter à chaque fois. C'est **lent** et ça **gâche des
ressources** pour rien, ce qui ralentit aussi les bons magasins.

### L'idée (comme un humain raisonnable)
Si un magasin te claque la porte au nez **3 fois de suite**, tu arrêtes d'insister
pendant un moment, puis tu retentes plus tard. C'est exactement ce que fait le bot
maintenant : **mise en veille** automatique de l'enseigne (1h par défaut), puis
nouvelle tentative.

### Ce que j'ai fait
- Créé un **carnet de santé** des enseignes (fichier `store_health.py`).
- Après 3 échecs d'affilée → l'enseigne est **mise en veille** et **sautée** pendant
  les cycles suivants (réglable : `STORE_PAUSE_THRESHOLD`, `STORE_PAUSE_DURATION`).
- Dès qu'une enseigne **répond à nouveau**, le compteur repart de zéro.
- Important : une réponse « 0 produit » **n'est PAS** comptée comme un échec (le
  site a répondu, c'est juste qu'il n'y avait rien).

### Vérifié pour de vrai ✅
- 2 échecs → pas de veille ; 3e échec → mise en veille (~60 min). ✅
- La veille expire bien après le délai prévu. ✅
- Une réponse OK (ou « vide ») **remet le compteur à zéro**. ✅

### En clair
Le bot **arrête de perdre du temps** sur les sites qui le bloquent : il les met de
côté un moment et se concentre sur les magasins qui marchent. Plus rapide, plus
efficace — et il retente tout seul plus tard, au cas où.

---

## 🧱 Chantier 12 — Alertes "bon plan" (baisse de prix)

**Date :** 13 juin 2026

### L'idée
Jusqu'ici on alertait quand un produit **revenait en stock**. Maintenant on alerte
aussi quand le **prix baisse fortement** sur un produit déjà en stock — un vrai
**bon plan** à ne pas rater.

### Ce que j'ai fait
- À chaque vérification, le bot compare le prix au prix précédent. Si la baisse
  dépasse un seuil (**15%** par défaut), il envoie une alerte « 💸 Baisse de prix »
  avec l'ancien prix, le nouveau, et le **pourcentage de remise**.
- Réglable avec `DEAL_DROP_PERCENT` (mettre 0 pour désactiver).
- Pas de spam : ça ne se déclenche que sur une vraie baisse, et la sécurité
  anti-doublon de 10 min s'applique aussi.

### Vérifié pour de vrai ✅
- Baisse de 25% (39,99€ → 29,99€) → alerte « Baisse de prix » avec « -25% ». ✅
- Petite baisse (~5%) → **aucune** alerte (en dessous du seuil). ✅
- L'alerte affiche bien l'ancien prix barré + la remise. ✅

### En clair
En plus des retours en stock, tu es prévenu des **bonnes affaires**. Un argument de
vente de plus, et zéro effort de config (ça marche tout seul).

---

## 🧱 Chantier 13 — Piloter le bot depuis Discord (commandes)

**Date :** 13 juin 2026

### L'idée
Au lieu de toucher au code ou aux fichiers, tu pilotes le bot **en tapant des
commandes directement dans Discord**. Tu tapes `/` et la liste s'affiche.

### Les commandes
| Commande | Ce qu'elle fait |
|---|---|
| `/help` | Affiche **toutes** les commandes et leur utilité |
| `/stats` | Combien de produits surveillés, combien en stock, alertes on/off |
| `/watchlist` | La liste des produits suivis (avec 🟢 en stock / 🔴 rupture) |
| `/add <url>` | Ajoute un produit à surveiller, juste en collant son lien |
| `/pause` | Coupe les alertes (le bot continue de tourner en silence) |
| `/resume` | Réactive les alertes |

### Ce que j'ai fait
- Branché ces commandes sur le bot Discord (elles apparaissent toutes seules dans
  ton serveur au démarrage).
- Mis la « cervelle » de chaque commande dans des fonctions à part, **testées une
  par une**, pour que ce soit solide.
- `/add` reconnaît l'enseigne grâce au lien et devine même un titre propre.
- `/pause` coupe vraiment les alertes (partout), `/resume` les rallume.

### Vérifié pour de vrai ✅
- `/help` liste bien les 6 commandes. ✅
- `/add` : ajoute un produit, refuse les doublons, les domaines inconnus et les
  liens invalides. ✅
- `/stats` et `/watchlist` affichent les bons chiffres et la bonne liste. ✅
- `/pause` **bloque réellement** l'envoi d'une alerte ; `/resume` la rétablit. ✅

### En clair
Tu gères tout le bot **depuis Discord**, sans toucher à un fichier. Pratique pour
ajouter un produit à la volée ou faire une pause sans rien arrêter.

---

## 🧱 Chantier 14 — Grand nettoyage + corrections avant lancement

**Date :** 14 juin 2026

Objectif : fiabiliser le projet avant le lancement officiel de la V1.

### 🐛 Bugs corrigés
- **Relance du navigateur cassée** : une vieille fonction tentait de relancer le
  navigateur d'une manière qui **plantait** et, pire, **fermait le navigateur**
  partagé → tout se bloquait. Supprimée (la mise en veille du chantier 11 fait
  déjà le travail, en mieux).
- **Mauvaise adresse de recherche pour La Grande Récré** (page 404). Corrigée.

### 🧹 Ménage
- Supprimé **7 fichiers de brouillon** inutiles (dont 2 qui réécrivaient les
  scrapers tout seuls — dangereux). Aucun n'était utilisé par le vrai bot.

### ✨ Nouveautés utiles
- **Anti-flood au démarrage** : au tout premier lancement (base vide), le bot
  **remplit sa liste en silence** au lieu d'envoyer 50 alertes d'un coup. Ensuite,
  alertes normales. (Évite d'inonder le salon le jour du lancement.)
- **Nettoyage auto de la base** : l'historique de prix de plus de 90 jours est
  purgé au démarrage (la base reste légère). Réglable : `HISTORY_RETENTION_DAYS`.

### 🧪 Tests automatiques (nouveau dossier `tests/`)
Création d'une **suite de 7 tests** qui vérifie d'un coup tout le cœur du bot
(transitions de stock, extraction des données, deals, ping, pause, prix Leclerc,
santé des enseignes). Lancer : `python tests/run_all.py`.
➡️ **7/7 réussis.** Tu peux relancer ça après chaque modif pour être tranquille.

### ⚠️ Point de vérité sur les magasins (important pour le lancement)
Après vérification en direct :
- **Fiables à 100% : Auchan + Leclerc** (rapides, sans navigateur).
- **Best-effort (souvent bloqués) : Cultura, King Jouet, Smyths, La Grande Récré.**
  La Grande Récré a ajouté un captcha depuis le début du projet. Ces 4 passent en
  veille automatiquement quand ils bloquent — pas de plantage, mais peu/pas de
  résultats.

### En clair
Le projet est **plus propre, plus solide et testé**. Le seul vrai piège (la relance
navigateur) est supprimé. Pour le lancement, compte surtout sur **Auchan et Leclerc**
qui marchent parfaitement ; les autres sont du bonus quand ils passent.

---

## 🧱 Chantier 15 — VITESSE : on ne lance que ce qui marche

**Date :** 15 juin 2026

### Le problème (vu dans les vrais logs)
Au lancement, le bot mettait **~45 minutes** pour UN cycle. Pourquoi ? Les 4 sites
blindés (Cultura, King Jouet, Smyths, La Grande Récré) s'acharnaient ~10-14 min
**chacun** contre leur anti-bot… pour **zéro produit**. Pendant ce temps, Leclerc
(247 produits) et Auchan ne passaient quasiment jamais.

### La correction
On ne surveille plus que les enseignes qui **répondent vraiment** : **Auchan +
Leclerc**. Les 4 autres sont **désactivées** (leur code reste là, réactivable via le
réglage `ENABLED_STORES` dans `.env`). On a aussi réduit le nombre d'essais
acharnés (5 → 2) : inutile d'insister contre un mur.

### Résultat mesuré
- **Avant : ~45 minutes** par cycle (et presque rien d'utile).
- **Après : ~10 secondes** par cycle (Auchan 181 produits + Leclerc 247). 🚀

Avec un `MIN_SLEEP` court, la surveillance est quasi **temps réel** sur les 2 gros
magasins qui marchent.

### En clair
Le bot est maintenant **rapide**. On a arrêté de perdre du temps sur l'impossible
et on se concentre sur l'efficace. Si un jour on trouve comment passer un site
blindé, il suffira de l'ajouter dans `ENABLED_STORES`.

---

## 🧹 Chantier 16 — On enlève tout ce qui n'est PAS des cartes Pokémon

**Date :** 15 juin 2026

### Le problème
Le bot envoyait des alertes pour des trucs qui n'ont rien à voir avec les cartes :
des **posters**, des **peluches**, un **jouet Dresseur Mission**, une **arène avec
spinners**, un **coffret Quiz**… Bref, du Pokémon, mais pas du **jeu de cartes**.

Pourquoi ? Deux raisons :
1. Le filtre qui dit "oui/non" ne servait **qu'au moment de la découverte**. Une fois
   un produit rangé dans la liste à surveiller, il n'était **plus jamais re-vérifié**.
   Or beaucoup de déchets avaient été rangés **avant** qu'on muscle le filtre.
2. Le filtre exigeait le mot "pokemon" **dans le titre** avant tout. Mais un vrai
   "Display M1S - Scellé" de Leclerc n'a pas "pokemon" dans le titre (juste dans la
   **marque**) → il était raté.

### La correction (3 verrous)
1. **Filtre plus malin** : il regarde maintenant le titre **ET la marque**. Un signal
   "carte" fort (booster, display, ETB, dresseur d'élite, code de set EV/ME, "card
   box"…) suffit. Sinon il faut "pokemon" **+** un contenant scellé (coffret, box,
   pack…). Nouveaux mots bannis : Mega Construx, nanoblock, Ravensburger, Labyrinth,
   académie de combat, calendrier de l'avent, "dresseur quiz"…
2. **Garde-fou permanent** : avant CHAQUE alerte de la liste de surveillance, on
   re-vérifie le produit. Si ce n'est pas du JCC Pokémon scellé → il est **retiré** et
   **aucune alerte** ne part. Plus aucun déchet ne peut passer.
3. **Grand ménage au démarrage** : à chaque lancement, le bot relit toute sa liste et
   **jette** ce qui n'est pas une vraie carte scellée.

### Résultat mesuré (sur la vraie base)
- **Avant : 199 produits** (bières, Smartbox, vin, livres, Mega Construx, posters…).
- **Après : 46 produits**, **uniquement** des cartes Pokémon scellées (boosters,
  displays, ETB/Dresseur d'Élite, coffrets EX, bundle 6 boosters, card box…).
- Les 4 produits que tu avais pointés (arène, 4D Build, Dresseur Mission, Quiz box)
  sont **tous partis**.

### En clair
Le bot ne t'enverra **plus que des cartes Pokémon scellées**. Tout le reste (jouets,
livres, déco, alcool…) est filtré à trois niveaux : à l'entrée, avant chaque alerte,
et au grand ménage du démarrage.

---

## 🏴‍☠️ Chantier 17 — On ajoute One Piece + de nouvelles boutiques

**Date :** 16 juin 2026

### Ce qu'on voulait
1. Surveiller aussi les cartes **One Piece** (displays, ETB, boosters), en plus de Pokémon.
2. **Tout en français uniquement** (Pokémon ET One Piece) — pas de japonais/anglais.
3. Ajouter le **maximum de boutiques** de la liste fournie (PDF).
4. Continuer à **bannir** les produits qui n'ont rien à voir.

### Ce qu'on a fait
**1) Le filtre comprend maintenant deux univers.** Avant il ne connaissait que
"pokemon". Maintenant il accepte aussi "one piece", et il regarde le **titre ET la
marque**. On a ajouté les codes de sets One Piece (OP01, OP09, PRB01…) et les noms
de sets.

**2) Filtre "fort / faible" (très important).** Sur une boutique qui vend plusieurs
jeux, le mot "booster" tout seul ne suffit plus (sinon on attrapait des boosters
**Magic** !). Désormais :
- un **signal fort** (nom/code de set, ETB, "Dresseur d'Élite") valide tout seul ;
- un **signal faible** (booster, display, coffret…) ne valide **que si** le produit
  dit clairement "Pokémon" ou "One Piece".

**3) Français uniquement.** On rejette tout ce qui est marqué japonais, anglais,
coréen, ou les imports (ex: "x6 EN (12/22)", noms d'équipages anglais).

**4) Blacklist enrichie.** Nouveaux bannis : figurines One Piece (Ichibansho,
Megahouse, Funko…), autres jeux de cartes (Magic, Lorcana, Yu-Gi-Oh, Vanguard…),
coffrets manga (Tomes), DVD/films, bubble tea, jeux de 54 cartes / playing cards,
Panini, accessoires de protection, papeterie…

**5) Nouvelles boutiques (Shopify).** Beaucoup de boutiques TCG tournent sur la même
technologie (**Shopify**) qui offre une "porte d'entrée" gratuite et sans blocage.
On a écrit **un seul** scraper générique qui les gère toutes. Sur les 18 boutiques
spécialisées du PDF testées, **2 sont compatibles et joignables** : **LudiJeux** et
**RelicTCG**. Ajouter une nouvelle boutique Shopify = **une seule ligne** dans la config.

### Ce qui a été écarté (et pourquoi)
- Les **importateurs japonais** du PDF (Cardotaku, AmiAmi, Meccha, Solaris…) et
  **Pokémon Center UK** : ils ne vendent que du japonais/anglais → contraire au
  "100% français".
- Les autres boutiques : soit une autre technologie (à coder une par une plus tard),
  soit injoignables / protégées.

### Résultat
- On surveille maintenant **4 sources** : Auchan, Leclerc, **LudiJeux**, **RelicTCG**
  (au lieu de 2), pour **Pokémon ET One Piece**, **en français**.
- Vérifié en direct : One Piece FR trouvé chez Leclerc (boosters Asmodee), et les 2
  boutiques Shopify renvoient des boosters/displays/coffrets propres avec prix + stock.
- Tests : **8/8** (un test dédié au filtre verrouille tout ça).

---

## 🔎 Chantier 18 — Grand balayage des boutiques (toutes les portes testées)

**Date :** 16 juin 2026

### Ce qu'on a fait
On a testé **TOUTES** les boutiques (PDF + nouvelle liste), pas juste Shopify. Pour
chaque site, on a vérifié 4 choses : est-il **joignable** ? a-t-il un **anti-bot** ?
quelle **technologie** ? et surtout : a-t-il une **porte d'entrée gratuite** (API) ?

On connaît maintenant **3 types de portes gratuites** :
1. **Shopify** → `/products.json` + `/search/suggest.json`
2. **WooCommerce** → `/wp-json/wc/store/v1/products` (NOUVEAU ce chantier !)
3. **Données structurées** (schema.org) sur les pages produit (déjà géré).

### Résultat du balayage (≈35 boutiques testées)
- **Joignables + porte gratuite** → intégrées : **LudiJeux**, **RelicTCG** (Shopify),
  **CoinBarons** (WooCommerce). 
- **Bloquées par Cloudflare/anti-bot** : Magic Bazar, Smartoys, Oupi, Game Mania,
  La Cité des Nuages, Play-In, Destockage… (mur infranchissable gratuitement).
- **Sur PrestaShop sans API publique** (à coder une par une) : UltraJeux, Pikastore,
  Majestik, Le Repaire du Dragon…
- **Injoignables depuis le serveur** (DNS/SSL) : Asie Games, Cartes Online, K-Zone,
  Manga Carta, TCG Normandie, PokéBasement, Card Hunter, Gama-TCG, Maison du Geek…
- **Instables** (SSL qui saute) : CaverneGobelin → écartées par prudence.
- **Géants & marketplaces** (Fnac, Cultura, Amazon, Cdiscount, eBay, Cardmarket…) :
  anti-bot lourd ou API payante → hors cadre "gratuit + robuste".

### Nouveau : scraper WooCommerce générique
Comme pour Shopify, **un seul** scraper gère toutes les boutiques WooCommerce.
Ajouter une boutique Woo = **une ligne** dans `WOO_SHOPS`. CoinBarons : 164 produits
trouvés, 94 valides (Pokémon + One Piece, en français), prix et stock corrects.

### Bilan
- On surveille maintenant **5 sources** (Auchan, Leclerc, LudiJeux, RelicTCG,
  CoinBarons), Pokémon + One Piece, **en français**.
- On maîtrise **3 technologies** → toute nouvelle boutique Shopify ou WooCommerce
  s'ajoute en 1 ligne, sans coder.
- Le mur restant = **Cloudflare** (boutiques bloquées) et **PrestaShop** (à coder
  individuellement). C'est là-dessus qu'il faudra décider d'investir ou non.

---

## 🧭 Chantier 19 — On a étudié PrestaShop (Niveau 2)… et on a dit non (pour l'instant)

**Date :** 16 juin 2026

### La question
Peut-on ajouter les boutiques en PrestaShop (UltraJeux, Pikastore, Majestik, Le
Repaire du Dragon, Parkage) ?

### Ce qu'on a testé
On a sondé leurs pages de recherche. Résultat :
- 4 sites sur 5 ont un **thème sur-mesure ou un rendu JavaScript** → aucun produit
  lisible directement dans la page (impossible de façon générique).
- Le seul propre (**Pikastore**) s'est révélé **instable** : 12 produits au 1er essai,
  puis 0, puis 0. Il a une protection qui se déclenche, ou un rendu JS intermittent.

### La décision (assumée)
**On ne fait pas le Niveau 2 maintenant.** Raisons :
- Pas de solution générique (chaque site = un scraper sur-mesure et fragile).
- Même le meilleur candidat est instable.
- Une source qui marche 1 fois sur 3 est **pire** que pas de source (elle reste en
  veille et fausse les bilans).

À refaire éventuellement **après la livraison**, avec navigateur + patience, site par
site. Pas une priorité.

### Ce qu'on garde
**5 sources solides** : Auchan, Leclerc, LudiJeux, RelicTCG, CoinBarons. Et le petit
**testeur de boutique** (`tools/tester_boutique.py`) pour ajouter soi-même toute
nouvelle boutique Shopify/WooCommerce en 1 ligne.

---

## 🏷️ Chantier 20 — Vendeurs officiels vs revendeurs

**Date :** 18 juin 2026 (demande de Tom)

### Le besoin
Sur les grandes enseignes (Leclerc, Auchan), des **revendeurs tiers** (marketplace)
vendent aussi — parfois plus cher ou douteux. Tom veut pouvoir **les repérer** ou
**les masquer**.

### La solution
- **Pastille automatique** sur chaque alerte :
  - **✅ Vendeur officiel** (l'enseigne elle-même, ou une boutique spécialisée),
  - **🔁 Revendeur (marketplace)** (un vendeur tiers sur Leclerc/Auchan).
- **Paramètre `MASQUER_REVENDEURS`** dans `.env` : à `true`, les revendeurs ne
  déclenchent plus d'alerte du tout (on ne garde que les officiels).

Les boutiques spécialisées (LudiJeux, RelicTCG, CoinBarons) sont toujours
considérées « officielles » (vendeur unique). Pour Leclerc/Auchan, « officiel » =
le vendeur est l'enseigne elle-même (sinon = revendeur).

---

## 🃏 Chantier 21 — Lien Cardmarket

**Date :** 18 juin 2026 (demande de Tom)

### Le besoin
Comme les liens Google/eBay, ajouter un lien **Cardmarket** pour voir la fiche d'un
produit (rareté, tendance des prix, moyennes 7/30 jours).

### La solution
- Nouveau lien/bouton **Cardmarket** sur chaque alerte, qui tombe sur la **recherche
  du bon jeu** (Pokémon ou One Piece, détecté automatiquement depuis le titre).
- Boutons d'une alerte : 🛒 Acheter · Google · eBay · **Cardmarket** · ⚡ Autobuy.

### Limite honnête (à savoir)
Afficher les **prix Cardmarket directement dans l'embed** Discord n'est PAS faisable
gratuitement : Cardmarket est protégé (Cloudflare bloque le scraping) et son API
demande une **clé d'application à valider**. Le lien, lui, ouvre la page où ces
infos sont visibles. Si Tom veut les prix DANS l'alerte, il faudra demander la clé
API Cardmarket — intégrable ensuite.

---

## 📈 Chantier 22 — Un graphique sur TOUS les produits

**Date :** 18 juin 2026 (demande de Tom)

### Le problème
Certaines alertes n'avaient pas de graphique de prix. Cause : le graphe n'était
tracé qu'à partir de **2 relevés**. Or une **nouveauté** n'a qu'**un seul** relevé
au moment de l'alerte → pas de graphe.

### La correction
Le graphique se génère maintenant **dès 1 relevé** : on trace une **ligne plate**
avec le prix affiché (« premier relevé »), et la courbe se remplit naturellement au
fil des cycles. Résultat : un graphe sur **chaque alerte, chaque enseigne**.
On a aussi donné une **couleur propre** aux 3 boutiques (LudiJeux, RelicTCG,
CoinBarons) pour des graphes cohérents.

Un graphe n'est omis que s'il n'y a **aucun prix numérique** (cas quasi inexistant
sur nos 5 sources) ou si matplotlib est absent.

---

## 🧱 Chantier A — Préparer le cœur pour l'appli (vers le .exe)

**Date :** 18 juin 2026

Première brique de l'appli graphique. **Objectif : préparer le moteur sans rien
casser** (le bot en ligne de commande marche toujours pareil).

### 1) Navigateur (Playwright) désormais OPTIONNEL
Nos 5 sources par défaut sont en HTTP/JSON → **elles n'ont pas besoin du navigateur**.
Le bot ne lance Playwright **que si** une enseigne « blindée » est activée. Par défaut :
**mode léger, aucun navigateur** → appli beaucoup plus simple à empaqueter et plus
rapide. (Vérifié en réel : « Mode léger : pas de navigateur lancé ».)

### 2) Configuration en couches
Les réglages se chargent dans l'ordre : `.env` (dev) → **réglages pré-remplis
embarqués** (pour la machine de Tom : zéro config) → **réglages utilisateur**
(`%APPDATA%\TCGStockBot\settings.json`, écrits par l'assistant). Nouvelle fonction
`sauver_reglages_utilisateur()` pour l'assistant de 1ʳᵉ config.

### 3) Bot pilotable (start/stop/statut)
Nouveau `bot_controller.py` : démarre/arrête la boucle dans un **thread** (l'IHM
reste fluide), arrêt **propre** via un signal, et **statut live** (cycle en cours,
produits surveillés, état des enseignes) exposé via `bot_state`. La boucle accepte
maintenant un `stop_event` et un **sommeil interruptible** (arrêt immédiat).

### Vérifs
Tests **10/10** (nouveau `test_app_core.py`), compilation OK, et smoke-test réel du
mode léger (un cycle Leclerc sans navigateur ni Discord). Le `main.py` en CLI est
**inchangé**.
