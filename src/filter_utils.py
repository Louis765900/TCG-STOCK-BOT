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
    "Mission : Tu es un expert en cartes à collectionner Pokémon ET One Piece. Tu dois déterminer "
    "si un produit correspond exactement à la recherche d'un collectionneur de cartes scellées.\n\n"
    "OUI (Validé) : Le produit est un article scellé contenant des cartes Pokémon ou One Piece, "
    "exclusivement en édition FRANÇAISE (ex: Boosters, ETB, Elite Trainer Box, Displays, Coffrets, "
    "Box, Bundles).\n\n"
    "NON (Rejeté) : Le produit est un produit dérivé (peluches, figurines/figures, vêtements, mugs, "
    "jouets sans cartes), un accessoire (portfolios, classeurs, cahiers range-cartes, sleeves, "
    "protège-cartes), un autre TCG (Yu-Gi-Oh, Magic, Lorcana, Dragon Ball...), ou une édition "
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
    sans_accents = "".join(c for c in decompose if unicodedata.category(c) != "Mn")
    # Tirets longs/courts (– — ‐ ‑) et espaces insécables -> espace, puis on
    # compacte les espaces. Évite que "mega – pokemon" échappe au mot "mega pokemon".
    unifie = re.sub(r"[‐-― ]", " ", sans_accents)
    return re.sub(r"\s+", " ", unifie)


# =============================================================================
# PHILOSOPHIE DU FILTRE (important pour la fiabilité)
# -----------------------------------------------------------------------------
# Les moteurs de recherche des enseignes sont FLOUS : chercher "pokemon coffret"
# ramène aussi des coffrets cadeaux Smartbox, du vin "Bag-in-Box", des Lego
# "coffret de construction", des livres, etc. Un filtre basé sur des mots vagues
# (coffret/pack/box) laisse donc passer un flot de déchets.
#
# On INVERSE la logique : un produit n'est validé que s'il contient un SIGNAL
# JCC FORT (booster, display, ETB, dresseur d'élite, code de set EV/ME, coffret
# ... EX, nom de set...). Les mots génériques ne suffisent JAMAIS seuls.
# Ordre de décision : liste blanche -> exclusions -> (mention Pokémon + signal).
# =============================================================================

# --- Exclusions : catégories hors cartes scellées (filet de sécurité) --------
_EXCLUS_RAW = [
    # Jeux vidéo / consoles / apps
    "nintendo", "switch", "3ds", "game boy", "console", "cartouche", "jeu video",
    "amiibo", "scarlet", "tcg pocket", "pokemon sleep", "pokemon unite",
    "pokemon masters", "donjon mystere", "pokken", "legendes arceus",
    "legendes z-a", "(nds)", "version noire", "version blanche",
    # Lego / briques / construction / blocs
    "lego", "construction", "a construire", "construx", "mega bloks", "megabloks",
    "mega construx", "mega pokemon", "mega-pokemon", "mega-coffret", "mega coffret",
    "bloks", "nanoblock", "briques", "4d build", "build", "builder", "blocks",
    "adventure builder",
    # Figurines / peluches / jouets
    "figurine", "peluche", "funko", "statuette", "marionnette", "jouet",
    "spinner", "arene", "dresseur mission", "jeu electronique", "dresseur quiz",
    "reconnaissance vocale", "centre pokemon", "clip n go", "clip 'n' go",
    "academie de combat", "jeu d'ambiance", "ravensburger", "labyrinth",
    "calendrier de l'avent",
    # Textile / accessoires portés / merch
    "t-shirt", "tee-shirt", "tee shirt", "casquette", "vetement", "pull",
    "pyjama", "sweat", "chaussettes", "sandales", "sac", "cartable", "trousse",
    "porte-monnaie", "portefeuille", "montre", "tapis de souris", "plaid",
    "sherpa", "couverture", "gourde", "casque", "ceinture", "vaisselle",
    "baguettes", "ramen", "cutlery", "polybag", "porte-cles",
    # Livres / guides / mangas / coloriages
    "manga", "livre", "guide", "pokedex", "(roman)", "encyclopedie", "artbook",
    "coloriage", "cherche-et-trouve", "cherche et trouve", "labyrinthe", "quiz",
    "carnet", "(poche)", "(broche)", "(relie)", "(cartonne)", "(jeunesse)",
    "(spirale)", "tome ", "secrets de",
    # Puzzles / jeux de société non-TCG
    "puzzle", "monopoly", "trivial pursuit", "jeu de societe", "memory",
    "jeu educatif", "top chrono", "jeu de plateau",
    # Ménager / déco / poster
    "mug", "tasse", "lampe", "reveil", "cadre", "poster", "sticker mural",
    "decoration", "housse", "drap", "coussin", "calendrier",
    # DVD / films / mangas en coffret (souvent "Coffret ... Tomes X à Y" / "Films")
    "le film", "films", "blu-ray", "blu ray", "dvd", ", vol", "tomes", "(tome",
    # Faux "cartes" : jeux de 54 cartes, cartes à jouer, stickers Panini, novelty
    "jeu de 54 cartes", "54 cartes", "playing card", "playing cards", "panini",
    "top trumps", "bubble tea", "straw hat", "devil fruit collection",
    # Cosmétique
    "serum", "uriage", "eau thermale", "creme",
    # Numérique
    "carte numerique", "code numerique", "carte virtuelle", "pokemon live",
    # Cosplay / déguisement
    "deguisement", "costume", "cosplay", "oreilles pikachu",
    # Alimentaire / boissons
    "bonbon", "chocolat", "cereale", "gateau", "pizza", "filo", "brick",
    "flammekueche", "biere", "bouteille", "bag-in-box", "apero", "dattes",
    "snack", "saumon", "thon", "poulet", "jambon", "capsules espresso", "sauce",
    "vin ", "smartbox", "coffret cadeau", "sejour",
    # Éditions étrangères (on veut du 100% FRANÇAIS, Pokémon comme One Piece)
    "japonais", "japonaise", "japanese", "coreen", "coreenne", "korean",
    "anglais", "anglaise", "english", "(jp)", "(en)", "jpn", "eng ", "ver eng",
    "version japonaise", "version anglaise", "version coreenne", "import japon",
    " jap ", "made in japan",
    # Marqueurs d'import EN/JP (ex: "... x6 EN (12/22)", noms d'équipages anglais)
    " en (", " jp (", "hat crew", "straw hat", "staw hat", " crew ",
    # Accessoires de rangement / protection (pas des cartes scellées)
    "portfolio", "classeur", "cahier", "range-cartes", "sleeve", "protege",
    "protection", "deck box", "deck holder", "holder", "boite de rangement",
    "boitier", "playmat", "tapis de jeu", "porte-cartes",
    # Autres TCG (on ne veut QUE Pokémon et One Piece)
    "yu-gi-oh", "yugioh", "yu gi oh", "magic the gathering", "mtg",
    "dragon ball", "lorcana", "marvel snap", "digimon", "weiss schwarz",
    "cardfight", "vanguard", "flesh and blood", "star wars unlimited",
    "union arena", "gundam card", "naruto kayou", "altered",
    # Figurines / figures (très présentes pour One Piece) + papeterie
    "ichiban", "ichibansho", "grandista", "portrait of pirates", "megahouse",
    "banpresto", "nendoroid", "world collectable", "model kit", "maquette",
    "porte-cle", "porte cle", "porte-clef", "stylo", "gomme", "badge",
    "pin's", "magnet", "veilleuse", "doudou", "maillot", "swimsuit",
    # Stickers / autocollants génériques (collections JCC -> liste blanche)
    "sticker", "autocollant",
]

# --- Signaux JCC FORTS : propres à Pokémon/One Piece -> valident SEULS ---------
# (un nom/code de set, un ETB, un "Dresseur d'Élite"... n'existent QUE sur ces
#  jeux ; aucun autre TCG ni merch ne les porte.)
_SIGNAUX_FORTS_RAW = [
    "etb", "elite trainer box",
    "dresseur d'elite", "dresseur d elite", "dresseur delite", "dresseur d'élite",
    "ultra premium", "ultra-premium", "premium collection", "super premium",
    # Noms de sets Pokémon (uniques au JCC, jamais sur du merch)
    "mega-evolution", "mega evolution", "flammes fantasmagoriques",
    "heros transcendants", "equilibre parfait", "chaos ascendant", "nuit noire",
    "ecarlate et violet", "evolutions a paldea", "flammes obsidiennes",
    "destinees de paldea", "faille paradoxe", "forces temporelles",
    "mascarade crepusculaire", "fable nebuleuse", "couronne stellaire",
    "etincelles deferlantes", "evolutions prismatiques", "aventures ensemble",
    "rivalites destinees", "foudre noire", "flamme blanche", "destinees radieuses",
    "celebrations", "origine perdue", "tempete argentee", "zenith supreme",
    # Noms de sets One Piece
    "romance dawn", "paramount war", "pillars of strength", "kingdoms of intrigue",
    "awakening of the new era", "wings of the captain", "two legends",
    "emperors in the new world", "royal blood", "500 years in the future",
    "memorial collection", "anime 25th",
]

# --- Signaux JCC FAIBLES : types de produits scellés COMMUNS à plusieurs TCG ---
# (un "booster"/"display"/"coffret" existe aussi chez Magic, Yu-Gi-Oh, Lorcana...
#  Sur une boutique multi-TCG, ils ne valident donc QU'AVEC l'univers Pokémon ou
#  One Piece présent dans le titre ou la marque.)
_SIGNAUX_FAIBLES_RAW = [
    "booster", "display", "jcc", "cartes a collectionner", "carte a collectionner",
    "blister", "tripack", "duopack", "pokebox", "pokeball tin", "mini tin",
    "deck de combat", "starter deck", "coffret ex", "coffret vmax",
    "coffret combat", "36 boosters", "boite de 36",
    "card box", "build & battle", "build and battle", "battle box",
    "premium booster", "double pack", "the best",
]

# Code de set Pokémon, ex : EV05, ME02, EB12, EB12.5, SL12
_SET_CODE_RE = re.compile(r"\b(ev|me|eb|sl|xy)\s?\d{1,2}(\.\d)?\b")
# Code de set One Piece, ex : OP01, OP-09, PRB01 (très spécifiques au jeu de cartes).
_SET_CODE_OP_RE = re.compile(r"\b(op|prb)\s?-?\d{1,2}\b")
# Marqueurs de carte (EX/VMAX/VSTAR/GX) pour les "Coffret <Pokémon> EX"
_CARD_MARKER_RE = re.compile(r"\b(ex|vmax|vstar|gx)\b")

# Univers cibles : un produit "générique" (coffret/box/pack sans signal fort) n'est
# validé que s'il appartient à l'un de ces univers de cartes.
MOTS_UNIVERS = ["pokemon", "one piece"]

# Contenants scellés génériques : ne valident QUE combinés à la mention "pokemon"
# (un "coffret"/"box"/"pack" Pokémon est un vrai produit ; sans Pokémon c'est du
# coffret cadeau, de la box repas, etc. — déjà filtrés par les exclusions).
_CONTENEUR_RAW = ["coffret", "box", "pack ", "collection", "tin", "bundle"]
MOTS_CONTENEUR = [_normaliser(m) for m in _CONTENEUR_RAW]

# --- Liste blanche : produits voulus contenant un mot normalement exclu -------
_PRIORITAIRES_RAW = [
    "sticker day",
    "collection autocollant",
    "tripack autocollant",
    "collection poster",
    "coffret collection poster",
    "avant-premiere",
    "avant premiere",
]

MOTS_EXCLUS = [_normaliser(m) for m in _EXCLUS_RAW]
MOTS_SIGNAUX_FORTS = [_normaliser(m) for m in _SIGNAUX_FORTS_RAW]
MOTS_SIGNAUX_FAIBLES = [_normaliser(m) for m in _SIGNAUX_FAIBLES_RAW]
MOTS_PRIORITAIRES = [_normaliser(m) for m in _PRIORITAIRES_RAW]
# Compat : anciens noms utilisés ailleurs (tous les signaux confondus).
MOTS_SIGNAUX = MOTS_SIGNAUX_FORTS + MOTS_SIGNAUX_FAIBLES
MOTS_TCG = MOTS_SIGNAUX


def est_tcg_valide_local(titre: str, marque: str = "") -> bool:
    """Filtre local strict : ne valide qu'un vrai produit JCC Pokémon scellé.

    `marque` (optionnel) : la marque renvoyée par le scraper. Beaucoup de fiches
    Leclerc ont un titre sans le mot "Pokémon" (ex: "Display M1S - Scellé") mais une
    marque "Pokémon" : on l'inclut dans le texte analysé pour ne pas les rater.
    """
    t = _normaliser(f"{titre} {marque}").strip()
    if not t:
        return False

    # 1. Liste blanche (produits voulus malgré un mot exclu) -> prime sur tout.
    if any(mot in t for mot in MOTS_PRIORITAIRES):
        return True

    # 2. Exclusions (Lego, livres, food, Smartbox, merch...).
    if any(mot in t for mot in MOTS_EXCLUS):
        logger.debug("Rejete (mot exclu): %s", titre)
        return False

    # 3. Signal JCC FORT (nom/code de set, ETB, Dresseur d'Élite...) -> valide SEUL,
    #    même sans nommer l'univers : ces signaux n'existent que sur Pokémon/One Piece.
    if (any(sig in t for sig in MOTS_SIGNAUX_FORTS)
            or _SET_CODE_RE.search(t) or _SET_CODE_OP_RE.search(t)):
        return True

    # 4. Sinon il FAUT nommer un univers cible (Pokémon ou One Piece) — sinon on
    #    risque de valider un booster Magic/Yu-Gi-Oh sur une boutique multi-TCG.
    if not any(u in t for u in MOTS_UNIVERS):
        logger.debug("Rejete (univers absent et aucun signal fort): %s", titre)
        return False

    # 5. Univers + (signal faible booster/display/blister... OU contenant scellé
    #    coffret/box/pack OU marqueur de carte EX/VMAX) -> produit JCC valide.
    if (any(sig in t for sig in MOTS_SIGNAUX_FAIBLES)
            or any(c in t for c in MOTS_CONTENEUR)
            or _CARD_MARKER_RE.search(t)):
        return True

    logger.debug("Rejete (univers sans signal/contenant JCC): %s", titre)
    return False

async def est_tcg_valide(titre: str, marque: str = "") -> bool:
    """
    Verifie localement le produit, puis utilise Gemini uniquement si l'option est active.
    Le bot ne doit jamais devenir muet parce qu'une API IA manque ou rate-limit.
    """
    global _DERNIER_APPEL_API
    titre_lower = f"{titre}|{marque}".lower().strip()

    # 0. Vérification du cache
    if titre_lower in _CACHE_TITRES:
        return _CACHE_TITRES[titre_lower]

    if not est_tcg_valide_local(titre, marque):
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
            contents=f"{titre} (marque: {marque})" if marque else titre,
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
