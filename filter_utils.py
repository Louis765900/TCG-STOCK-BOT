"""Filtres TCG avec validation locale et option Gemini."""
import os
import logging
import re
import asyncio
import time

import config

try:
    from google import genai
except ImportError:
    genai = None

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY and genai:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None
    if config.USE_GEMINI_FILTER:
        logger.warning("GEMINI_API_KEY non configuree. Le filtrage Gemini est ignore.")

system_instruction = (
    "Mission : Tu es un expert en cartes Pokémon. Tu dois déterminer si un produit correspond "
    "exactement à la recherche d'un collectionneur de cartes scellées.\n\n"
    "OUI (Validé) : Le produit est un article scellé contenant des cartes Pokémon, exclusivement "
    "en édition Française (ex: Boosters, ETB, Elite Trainer Box, Displays, Coffrets, Box).\n\n"
    "NON (Rejeté) : Le produit est un produit dérivé (peluches, figurines, vêtements, mugs, jouets sans cartes), "
    "un accessoire (portfolios, classeurs, cahiers range-cartes, sleeves, protège-cartes), ou une édition "
    "étrangère (Coréen, Japonais, Anglais) ou de la nourriture.\n\n"
    "Format de sortie strict : Tu dois répondre UNIQUEMENT par le mot \"OUI\" ou le mot \"NON\". "
    "Aucun autre texte, aucune ponctuation supplémentaire."
)

# Cache en mémoire pour éviter d'interroger Gemini plusieurs fois pour le même titre
_CACHE_TITRES = {}

# Dernier appel à l'API pour limiter le débit
_DERNIER_APPEL_API = 0

MOTS_EXCLUS = [
    "figurine", "peluche", "mug", "t-shirt", "casquette", "vetement", "vêtement",
    "pull", "pyjama", "jouet", "puzzle", "cartable", "sac", "montre", "reveil",
    "réveil", "housse", "drap", "coussin", "bonbon", "chocolat", "cereale",
    "céréale", "gateau", "gâteau", "pizza", "pate", "pâte", "filo", "brick",
    "flammekueche", "japonais", "coreen", "coréen", "anglais", "jap", "uk",
    "portfolio", "classeur", "cahier", "range-cartes", "sleeve", "protege",
    "protège", "deck box", "boite de rangement", "boîte de rangement", "boitier",
    "boîtier", "sticker", "autocollant",
]

MOTS_TCG = [
    "booster", "display", "coffret", "etb", "elite trainer box", "carte",
    "cartes", "pack", "bundle", "blister", "box", "tin", "pokebox", "pokébox",
    "deck", "pokemon", "pokémon",
]


def est_tcg_valide_local(titre: str) -> bool:
    """Filtre local deterministe: rapide, stable, sans quota externe."""
    titre_lower = titre.lower().strip()
    if not titre_lower:
        return False

    if any(mot in titre_lower for mot in MOTS_EXCLUS):
        logger.debug("Rejete par filtre local (mot exclu): %s", titre)
        return False

    if not any(mot in titre_lower for mot in MOTS_TCG):
        logger.debug("Rejete par filtre local (aucun mot-cle TCG): %s", titre)
        return False

    return True

async def est_tcg_valide(titre: str) -> bool:
    """
    Verifie localement le produit, puis utilise Gemini uniquement si l'option est active.
    Le bot ne doit jamais devenir muet parce qu'une API IA manque ou rate-limit.
    """
    global _DERNIER_APPEL_API
    titre_lower = titre.lower().strip()
    
    # 0. Vérification du cache
    if titre_lower in _CACHE_TITRES:
        return _CACHE_TITRES[titre_lower]
    
    if not est_tcg_valide_local(titre):
        _CACHE_TITRES[titre_lower] = False
        return False

    if not config.USE_GEMINI_FILTER or not client:
        _CACHE_TITRES[titre_lower] = True
        return True

    try:
        # Rate Limiting stricte : Max 15 requêtes par minute => 1 requête toutes les 4.1 secondes
        maintenant = time.time()
        temps_ecoule = maintenant - _DERNIER_APPEL_API
        if temps_ecoule < 4.1:
            await asyncio.sleep(4.1 - temps_ecoule)
            
        _DERNIER_APPEL_API = time.time()
        
        response = await client.aio.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=titre,
            config=genai.types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.0
            )
        )
        reponse_texte = response.text.strip().upper()
        # Nettoyage de la ponctuation éventuelle (ex: "OUI.")
        reponse_nette = re.sub(r'[^A-Z]', '', reponse_texte)
        
        resultat = (reponse_nette == "OUI")
        _CACHE_TITRES[titre_lower] = resultat
        return resultat
    except Exception as e:
        logger.error(f"Erreur lors de l'appel à l'API Gemini pour '{titre}': {e} — fallback filtre local.")
        _CACHE_TITRES[titre_lower] = True
        return True
