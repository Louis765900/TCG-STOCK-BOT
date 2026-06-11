# Strategie de monitoring stable

Objectif: suivre les stocks TCG/Pokemon avec un bot qui continue de fonctionner meme quand une enseigne change son HTML ou refuse le scraping navigateur.

## Position claire

Le bot ne doit pas dependre d'un "bypass" anti-bot. C'est fragile, instable, et certains sites bloquent explicitement l'automatisation. La base stable est une architecture multi-source:

1. Source officielle ou publique quand elle existe: API, flux produit, sitemap, JSON-LD, schema.org, pages produit.
2. Scraper HTML uniquement en fallback, avec detection explicite des pages CAPTCHA/protection.
3. Watchlist de pages produit connues pour le temps reel utile: les fiches produit changent moins souvent que les pages recherche.
4. Alertes uniquement apres normalisation produit + detection de changement stock.

## Priorites techniques

1. Supprimer Gemini de la boucle critique.
   - Le filtre local doit suffire par defaut.
   - Gemini reste optionnel pour des cas ambigus, jamais bloquant.

2. Normaliser les resultats.
   - Champs minimum: enseigne, titre, url, prix, image_url, en_stock, source, detected_at.
   - Chaque scraper doit indiquer s'il a trouve zero produit, s'il est bloque, ou s'il a timeout.

3. Passer a un modele par connecteur.
   - `search`: decouverte de nouveaux produits.
   - `product`: verification stock/prix sur URL connue.
   - `source_status`: healthy, blocked, timeout, parser_error.

4. Ajouter une watchlist.
   - Le bot stocke les URLs valides deja trouvees.
   - A chaque cycle, il verifie surtout ces URLs.
   - La recherche globale tourne moins souvent pour decouvrir les nouveaux produits.

5. Couverture par enseigne.
   - Auchan: HTML exploitable avec schema.org et `data-stock`.
   - Leclerc: Angular/SSR partiel, necessite extraction plus specifique ou endpoint interne stable si disponible.
   - Cultura, King Jouet, Smyths: protections anti-bot detectees. A traiter via source officielle, flux partenaire, alerte navigateur manuelle, ou watchlist importee.
   - La Grande Recre: HTML partiel mais protection/captcha possible. A fiabiliser avec endpoints ou fiches produit.

## Ce qui est realiste

- "Tous les sites possibles" en temps reel strict n'est pas realiste avec du scraping navigateur pur.
- Une couverture fiable se construit site par site, avec une source primaire par enseigne.
- Le bot peut etre stable si chaque connecteur sait echouer proprement et si la watchlist continue de surveiller les produits deja connus.

## Prochaine etape recommandee

Mettre en place le moteur `watchlist + connecteurs`:

1. Ajouter une table `sources`/`watchlist`.
2. Decoupler decouverte et verification stock.
3. Creer un rapport de cycle: produits trouves, restocks, ruptures, sites bloques, erreurs parser.
4. Migrer chaque enseigne une par une vers son meilleur connecteur.
