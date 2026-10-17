"""store_domains.py - Domaines des enseignes (source unique : Discord, audit, redirections)."""
from __future__ import annotations

import config

# Reconnaissance de l'enseigne a partir du domaine.
DOMAINES = {
    "auchan.fr": "Auchan",
    "e.leclerc": "Leclerc",
    "cultura.com": "Cultura",
    "king-jouet.com": "KingJouet",
    "smythstoys": "Smyths",
    "lagranderecre.fr": "GrandeRecre",
}


def domaines_connus() -> dict:
    """Enseignes dediees + boutiques Shopify/WooCommerce configurees (domaine -> nom)."""
    domaines = dict(DOMAINES)
    for table in (config.SHOPIFY_SHOPS, config.WOO_SHOPS):
        for nom, dom in table.items():
            domaines[dom.lower().removeprefix("www.")] = nom
    return domaines


def hote_appartient(host: str, domaine: str) -> bool:
    """Vrai si `host` est `domaine` ou l'un de ses sous-domaines (comparaison exacte
    par labels : 'auchan.fr.evil.com' n'appartient PAS a 'auchan.fr').

    Un domaine sans point ('smythstoys') doit etre un label entier de l'hote.
    """
    host = (host or "").lower().rstrip(".")
    domaine = (domaine or "").lower()
    if not host or not domaine:
        return False
    if "." in domaine:
        return host == domaine or host.endswith("." + domaine)
    return domaine in host.split(".")


def enseigne_pour_hote(host: str) -> str | None:
    for domaine, enseigne in domaines_connus().items():
        if hote_appartient(host, domaine):
            return enseigne
    return None


def meme_site(host_a: str, host_b: str) -> bool:
    """Deux hotes du meme site (ex. relictcg.com <-> www.relictcg.com)."""
    a = (host_a or "").lower().removeprefix("www.")
    b = (host_b or "").lower().removeprefix("www.")
    return bool(a and b and (a == b or a.endswith("." + b) or b.endswith("." + a)))
