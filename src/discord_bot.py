"""
discord_bot.py - Passerelle temps reel du bot Discord (gateway).

Deux roles :
  1. ECOUTER les clics de boutons (fondation autobuy).
  2. Fournir des COMMANDES SLASH pour piloter le bot depuis Discord :
     /help /stats /watchlist /add /pause /resume.

La logique de chaque commande est dans des fonctions simples et testables
(texte_aide, texte_stats, texte_watchlist, ajouter_produit_url). La couche
Discord ne fait que les appeler et repondre.

Demarre uniquement si DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID sont configures.
"""

import logging
import math
import re
from urllib.parse import urlparse, urlsplit, urlunsplit, parse_qsl, urlencode

import discord
from discord import app_commands

import bot_state
import database
import config
from config import DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID, DISCORD_OWNER_ID
from product_format import escape_markdown
from store_domains import DOMAINES, domaines_connus, enseigne_pour_hote  # noqa: F401

logger = logging.getLogger("discord_bot")

_client: discord.Client | None = None

# Domaines des enseignes : source unique dans store_domains (partagee avec l'audit).
_domaines_connus = domaines_connus


def _enseigne_pour_url(url: str) -> str | None:
    """Enseigne correspondant a l'URL, par correspondance EXACTE de nom d'hote.

    On compare le hostname reel (pas une sous-chaine de l'URL) : ainsi
    'https://evil.com/?x=auchan.fr' n'est PAS reconnu comme Auchan. Empeche
    qu'une URL arbitraire (SSRF) soit ajoutee a la watchlist puis requetee.
    """
    return enseigne_pour_hote(urlparse(url).hostname or "")
    labels = host.split(".")
    for domaine, enseigne in _domaines_connus().items():
        d = domaine.lower()
        if "." in d:
            # Domaine complet : host doit etre ce domaine ou un sous-domaine.
            if host == d or host.endswith("." + d):
                return enseigne
        else:
            # Mot-cle nu (ex. 'smythstoys') : doit etre un label entier du host.
            if d in labels:
                return enseigne
    return None


# =============================================================================
# Logique des commandes (testable sans Discord)
# =============================================================================

def texte_aide() -> str:
    return (
        "**🛠️ Commandes TCG-STOCK-BOT**\n"
        "• `/help` — affiche cette aide\n"
        "• `/stats` — produits surveillés, en stock, état des alertes\n"
        "• `/status` — santé et vitesse de chaque enseigne (24 h)\n"
        "• `/watchlist` — liste des produits suivis\n"
        "• `/list [page] [enseigne]` — produits suivis (paginé)\n"
        "• `/watch <url>` — ajouter un produit à surveiller (admin)\n"
        "• `/unwatch <url>` — retirer un produit (admin)\n"
        "• `/add <url>` — identique à `/watch`\n"
        "• `/pause` — couper les alertes (le bot continue de tourner)\n"
        "• `/resume` — réactiver les alertes\n"
    )


async def texte_stats() -> str:
    produits = await database.recuperer_tous_produits()
    total = len(produits)
    en_stock = sum(1 for p in produits if p.get("en_stock"))
    par_enseigne: dict[str, int] = {}
    for p in produits:
        par_enseigne[p["enseigne"]] = par_enseigne.get(p["enseigne"], 0) + 1
    etat = "⏸️ en pause" if bot_state.alertes_en_pause() else "▶️ actives"
    repartition = ", ".join(f"{k} ({v})" for k, v in sorted(par_enseigne.items())) or "—"
    return (
        "**📊 Statistiques**\n"
        f"Produits surveillés : **{total}**\n"
        f"En stock actuellement : **{en_stock}**\n"
        f"Alertes : {etat}\n"
        f"Par enseigne : {repartition}"
    )


async def texte_status(heures: float = 24.0) -> str:
    stats = await database.stats_enseignes(heures)
    if not stats:
        return "🩺 Pas encore de données de cycle."
    icone = {"healthy": "🟢", "blocked": "🔴", "timeout": "🟠", "parser_error": "🟠",
             "empty": "🟡"}
    lignes = [f"**🩺 Santé des enseignes** ({heures:g} h)"]
    for ens, st in sorted(stats.items()):
        lignes.append(
            f"{icone.get(st['dernier_statut'], '⚪')} **{ens}** — "
            f"{st['taux_ok'] * 100:.0f}% OK ({st['ok']}/{st['cycles']}) · "
            f"moy {st['duree_moy']:.1f}s · p95 {st['duree_p95']:.1f}s"
        )
    return "\n".join(lignes)


async def texte_watchlist(limite: int = 15) -> str:
    produits = await database.recuperer_tous_produits()
    if not produits:
        return "📋 Watchlist vide. Ajoute un produit avec `/add <url>`."
    lignes = [f"**📋 Watchlist** ({len(produits)} produits)"]
    for p in produits[:limite]:
        etat = "🟢" if p.get("en_stock") else "🔴"
        lignes.append(f"{etat} [{p['enseigne']}] {p['titre'][:48]} — {p.get('prix', 'N/A')}")
    if len(produits) > limite:
        lignes.append(f"… et {len(produits) - limite} de plus")
    return "\n".join(lignes)


def _titre_depuis_url(url: str) -> str:
    path = urlparse(url).path
    segments = [s for s in path.split("/") if s and not s.lower().startswith("pr-")]
    base = segments[-1] if segments else "Produit"
    base = re.sub(r"\.html?$", "", base)
    base = re.sub(r"-\d{6,}$", "", base)            # retire un id/EAN en fin
    base = base.replace("-", " ").replace("_", " ").strip()
    return (base[:80].title() or "Produit")


_URL_MAX = 500
_PARAMS_SUIVI = ("utm_", "fbclid", "gclid", "mc_", "xtor", "xtcr")


def normaliser_url(url: str) -> str | None:
    """URL canonique pour la watchlist, ou None si elle n'est pas acceptable.

    Regles (anti-SSRF + anti-doublons) : https uniquement, pas d'identifiants dans
    l'URL (user:pass@), pas de port exotique, pas de caracteres de controle ; nom
    d'hote en minuscules ; fragment et parametres de suivi (utm_*, fbclid...)
    retires pour qu'un meme produit ne soit pas ajoute deux fois.
    """
    url = (url or "").strip()
    if not url or len(url) > _URL_MAX or any(ord(c) < 33 or ord(c) == 127 for c in url):
        return None
    try:
        p = urlsplit(url)
        port = p.port
    except ValueError:
        return None
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        return None
    if port not in (None, 443):
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                       if not k.lower().startswith(_PARAMS_SUIVI)])
    if p.hostname.lower().endswith("carrefour.fr"):
        query = ""   # ?s=<id vendeur> designe une offre marketplace : meme produit, meme fiche
    return urlunsplit(("https", p.hostname.lower(), p.path, query, ""))


async def ajouter_produit_url(url: str) -> str:
    """Ajoute un produit a la watchlist (commandes /watch et /add)."""
    propre = normaliser_url(url)
    if propre is None:
        return "❌ URL invalide (https:// requis, sans identifiants ni port particulier)."
    enseigne = _enseigne_pour_url(propre)
    if not enseigne:
        return ("❌ Enseigne non reconnue pour cette URL.\n"
                "Enseignes gérées : " + ", ".join(sorted(set(_domaines_connus().values()))))
    if enseigne not in config.ENABLED_STORES:
        return f"❌ L'enseigne **{enseigne}** est désactivée (ENABLED_STORES) : produit non surveillé."
    if await database.recuperer_produit(propre):
        return "ℹ️ Ce produit est déjà dans la watchlist."
    titre = _titre_depuis_url(propre)
    # manuel=True : le filtre automatique ne doit jamais purger un ajout volontaire.
    await database.ajouter_produit(propre, titre, enseigne, False, manuel=True)
    return f"✅ Ajouté à la surveillance **[{enseigne}]** : {escape_markdown(titre)}"


async def retirer_produit_url(url: str) -> str:
    """Retire un produit de la watchlist (commande /unwatch)."""
    propre = normaliser_url(url)
    if propre is None:
        return "❌ URL invalide (https:// requis)."
    if await database.retirer_produit(propre):
        return "🗑️ Produit retiré de la surveillance."
    return "ℹ️ Ce produit n'est pas dans la watchlist."


_PAR_PAGE = 10


async def texte_liste(page: int = 1, enseigne: str | None = None) -> str:
    """Liste paginee des produits suivis (10 par page), filtrable par enseigne."""
    produits = await database.recuperer_tous_produits()
    if enseigne:
        produits = [p for p in produits if p["enseigne"].lower() == enseigne.strip().lower()]
    if not produits:
        if enseigne:
            return f"📋 Aucun produit suivi pour **{escape_markdown(enseigne)}**."
        return "📋 Aucun produit suivi. Ajoute-en un avec `/watch <url>`."
    pages = max(1, math.ceil(len(produits) / _PAR_PAGE))
    page = min(max(1, int(page)), pages)
    debut = (page - 1) * _PAR_PAGE
    lignes = [f"**📋 Produits suivis** ({len(produits)}) — page {page}/{pages}"]
    for p in produits[debut:debut + _PAR_PAGE]:
        etat = "🟢" if p.get("en_stock") else "🔴"
        lignes.append(f"{etat} [{p['enseigne']}] {escape_markdown(p['titre'][:48])} — "
                      f"{p.get('prix', 'N/A')}")
    if page < pages:
        lignes.append(f"➡️ `/list page:{page + 1}` pour la suite")
    return "\n".join(lignes)


# =============================================================================
# Controle d'acces (commandes qui modifient l'etat du bot)
# =============================================================================

_REFUS = "⛔ Commande réservée à l'administrateur du bot."


def est_autorise(interaction: discord.Interaction) -> bool:
    """Vrai si l'auteur peut piloter le bot (/add, /pause, /resume).

    - Si DISCORD_OWNER_ID est defini : seul cet utilisateur est autorise.
    - Sinon : toute personne disposant de la permission 'administrateur' sur le
      serveur. (Par defaut Discord, sans config, on ne se repose donc PAS sur
      'tout le monde' : un membre lambda ne peut pas couper les alertes.)
    """
    user = getattr(interaction, "user", None)
    if user is None:
        return False
    if DISCORD_OWNER_ID:
        return str(getattr(user, "id", "")) == str(DISCORD_OWNER_ID)
    perms = getattr(user, "guild_permissions", None)
    return bool(perms and perms.administrator)


# =============================================================================
# Boutons (fondation autobuy)
# =============================================================================

async def gerer_autobuy(interaction: discord.Interaction) -> None:
    lien = ""
    if interaction.message and interaction.message.embeds:
        lien = interaction.message.embeds[0].url or ""
    if lien:
        message = ("⚡ **Autobuy bientôt disponible.**\n"
                   f"En attendant, finalise ton achat ici : {lien}")
    else:
        message = "⚡ Autobuy bientôt disponible (lien d'achat introuvable sur cette alerte)."
    await interaction.response.send_message(message, ephemeral=True)


# =============================================================================
# Construction du client + commandes
# =============================================================================

def creer_client() -> discord.Client:
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    @client.event
    async def on_ready():
        try:
            guild = None
            if DISCORD_CHANNEL_ID:
                chan = client.get_channel(int(DISCORD_CHANNEL_ID))
                if chan is not None:
                    guild = chan.guild
            if guild is not None:
                # Sync sur le serveur = commandes disponibles immédiatement.
                tree.copy_global_to(guild=discord.Object(id=guild.id))
                await tree.sync(guild=discord.Object(id=guild.id))
            else:
                await tree.sync()
            logger.info("Bot Discord connecté (%s), commandes slash prêtes.", client.user)
        except Exception as e:
            logger.error("Synchronisation des commandes échouée : %s", e)

    @client.event
    async def on_interaction(interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            custom_id = (interaction.data or {}).get("custom_id", "")
            try:
                if custom_id == "autobuy":
                    await gerer_autobuy(interaction)
            except Exception as e:
                logger.error("Erreur interaction '%s' : %s", custom_id, e)

    # ----- Commandes slash -----
    @tree.command(name="help", description="Affiche toutes les commandes du bot")
    async def cmd_help(interaction: discord.Interaction):
        await interaction.response.send_message(texte_aide(), ephemeral=True)

    @tree.command(name="stats", description="Produits surveillés et état du bot")
    async def cmd_stats(interaction: discord.Interaction):
        await interaction.response.send_message(await texte_stats(), ephemeral=True)

    @tree.command(name="status", description="Santé et vitesse de chaque enseigne")
    async def cmd_status(interaction: discord.Interaction):
        await interaction.response.send_message(await texte_status(), ephemeral=True)

    @tree.command(name="watchlist", description="Liste des produits surveillés")
    async def cmd_watchlist(interaction: discord.Interaction):
        await interaction.response.send_message(await texte_watchlist(), ephemeral=True)

    @tree.command(name="list", description="Produits suivis (paginé)")
    @app_commands.describe(page="Numéro de page", enseigne="Filtrer par enseigne")
    async def cmd_list(interaction: discord.Interaction, page: int = 1,
                       enseigne: str | None = None):
        await interaction.response.send_message(await texte_liste(page, enseigne),
                                                ephemeral=True)

    async def _admin_url(interaction: discord.Interaction, url: str, action):
        if not est_autorise(interaction):
            await interaction.response.send_message(_REFUS, ephemeral=True)
            return
        try:
            message = await action(url)
        except Exception as e:
            logger.error("Erreur commande watchlist : %s", e)
            message = "❌ Erreur interne, réessaie."
        await interaction.response.send_message(message, ephemeral=True)

    @tree.command(name="watch", description="Ajouter un produit à surveiller")
    @app_commands.describe(url="Lien du produit à surveiller")
    async def cmd_watch(interaction: discord.Interaction, url: str):
        await _admin_url(interaction, url, ajouter_produit_url)

    @tree.command(name="add", description="Ajouter un produit à surveiller (= /watch)")
    @app_commands.describe(url="Lien du produit à surveiller")
    async def cmd_add(interaction: discord.Interaction, url: str):
        await _admin_url(interaction, url, ajouter_produit_url)

    @tree.command(name="unwatch", description="Retirer un produit de la surveillance")
    @app_commands.describe(url="Lien du produit à retirer")
    async def cmd_unwatch(interaction: discord.Interaction, url: str):
        await _admin_url(interaction, url, retirer_produit_url)

    @tree.command(name="pause", description="Couper les alertes (le bot continue de tourner)")
    async def cmd_pause(interaction: discord.Interaction):
        if not est_autorise(interaction):
            await interaction.response.send_message(_REFUS, ephemeral=True)
            return
        bot_state.set_pause(True)
        await interaction.response.send_message("⏸️ Alertes mises en pause.", ephemeral=True)

    @tree.command(name="resume", description="Réactiver les alertes")
    async def cmd_resume(interaction: discord.Interaction):
        if not est_autorise(interaction):
            await interaction.response.send_message(_REFUS, ephemeral=True)
            return
        bot_state.set_pause(False)
        await interaction.response.send_message("▶️ Alertes réactivées.", ephemeral=True)

    return client


async def demarrer() -> None:
    global _client
    if not DISCORD_BOT_TOKEN:
        logger.warning("DISCORD_BOT_TOKEN manquant : bot non démarré.")
        return
    _client = creer_client()
    try:
        await _client.start(DISCORD_BOT_TOKEN)
    except Exception as e:
        logger.error("Bot Discord interrompu : %s", e)


async def arreter() -> None:
    if _client is not None and not _client.is_closed():
        await _client.close()
