"""Filtres TCG avec validation locale et option Gemini."""
import os
import logging
import re
import asyncio
import time
import unicodedata

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

def _normaliser(texte: str) -> str:
    """Minuscule + suppression des accents, pour un filtrage robuste.

    Les enseignes écrivent tantôt "Pokémon" tantôt "Pokemon" : on compare tout
    sans accents pour éviter les ratés.
    """
    decompose = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


# --- Mots à BANNIR (produits hors cartes TCG scellées) -----------------------
# ATTENTION : on ne bannit que des termes SANS ambiguïté. Les noms de jeux vidéo
# qui entrent en collision avec des SETS JCC (Écarlate/Violet, Soleil/Lune,
# Noir/Blanc, Pokémon GO, Légendes...) NE SONT PAS bannis bruts, sinon ils
# élimineraient les produits voulus.
_EXCLUS_RAW = [
    # Jeux vidéo / consoles / apps (termes non ambigus uniquement)
    "nintendo", "switch", "3ds", "game boy", "console", "cartouche",
    "jeu video", "amiibo", "scarlet", "tcg pocket", "pokemon sleep",
    "pokemon unite", "pokemon masters", "donjon mystere", "pokken",
    "legendes arceus", "legendes z-a", "jeu video pokemon",
    # Lego / figurines / peluches / jouets
    "lego", "figurine", "peluche", "funko", "statuette", "marionnette", "jouet",
    # Textile / accessoires portés
    "t-shirt", "casquette", "vetement", "pull", "pyjama", "sweat", "chaussettes",
    "sac", "sac a dos", "cartable", "trousse", "porte-monnaie", "portefeuille",
    "montre", "tapis de souris",
    # Livres / guides / mangas
    "manga", "livre", "guide strategique", "pokedex", "roman", "encyclopedie",
    "artbook",
    # Puzzles / jeux de société non-TCG
    "puzzle", "monopoly", "trivial pursuit", "jeu de societe", "memory",
    "jeu educatif", "top chrono", "jeu de plateau",
    # Ménager / déco
    "mug", "tasse", "lampe", "reveil", "cadre", "sticker mural", "decoration",
    "housse", "drap", "coussin",
    # Numérique
    "carte numerique", "code numerique", "carte virtuelle", "pokemon live",
    # Cosplay / déguisement
    "deguisement", "costume", "cosplay", "oreilles pikachu",
    # Alimentaire
    "bonbon", "chocolat", "cereale", "gateau", "pizza", "pate", "filo", "brick",
    "flammekueche",
    # Éditions étrangères
    "japonais", "coreen", "anglais", "jap", "uk",
    # Accessoires de rangement / protection (pas des cartes scellées)
    "portfolio", "classeur", "cahier", "range-cartes", "sleeve", "protege",
    "deck box", "boite de rangement", "boitier",
    # Autres TCG
    "yu-gi-oh", "yugioh", "yu gi oh", "magic the gathering", "one piece",
    "dragon ball", "lorcana", "marvel snap", "digimon",
    # Stickers / autocollants génériques (les collections JCC sont en liste blanche)
    "sticker", "autocollant",
]

# --- Mots indiquant un produit JCC valide ------------------------------------
_TCG_RAW = [
    "booster", "display", "coffret", "etb", "elite trainer box",
    "dresseur d'elite", "dresseur elite", "carte", "cartes", "pack", "bundle",
    "blister", "box", "tin", "pokebox", "pokeball tin", "deck", "tripack",
    "duopack", "jcc", "scelle", "pokemon",
]

# --- Liste blanche : produits voulus contenant un mot normalement exclu -------
# Ex : "Collection autocollant Évolutions Prismatiques" est un produit JCC,
# mais "autocollant" est banni. La liste blanche prime sur les exclusions.
_PRIORITAIRES_RAW = [
    "sticker day",
    "collection autocollant",
    "tripack autocollant",
    "collection poster",
    "coffret collection poster",
    "avant-premiere",
    "avant premiere",
    "classeur booster",
]

MOTS_EXCLUS = [_normaliser(m) for m in _EXCLUS_RAW]
MOTS_TCG = [_normaliser(m) for m in _TCG_RAW]
MOTS_PRIORITAIRES = [_normaliser(m) for m in _PRIORITAIRES_RAW]


def est_tcg_valide_local(titre: str) -> bool:
    """Filtre local deterministe: rapide, stable, sans quota externe."""
    titre_norm = _normaliser(titre).strip()
    if not titre_norm:
        return False

    # La liste blanche prime sur les exclusions.
    if any(mot in titre_norm for mot in MOTS_PRIORITAIRES):
        return True

    if any(mot in titre_norm for mot in MOTS_EXCLUS):
        logger.debug("Rejete par filtre local (mot exclu): %s", titre)
        return False

    if not any(mot in titre_norm for mot in MOTS_TCG):
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
