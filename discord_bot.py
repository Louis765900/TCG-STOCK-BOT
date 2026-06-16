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
import re
from urllib.parse import urlparse

import discord
from discord import app_commands

import bot_state
import database
from config import DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID

logger = logging.getLogger("discord_bot")

_client: discord.Client | None = None

# Reconnaissance de l'enseigne a partir du domaine (pour /add).
DOMAINES = {
    "auchan.fr": "Auchan",
    "e.leclerc": "Leclerc",
    "cultura.com": "Cultura",
    "king-jouet.com": "KingJouet",
    "smythstoys": "Smyths",
    "lagranderecre.fr": "GrandeRecre",
}


# =============================================================================
# Logique des commandes (testable sans Discord)
# =============================================================================

def texte_aide() -> str:
    return (
        "**🛠️ Commandes TCG-STOCK-BOT**\n"
        "• `/help` — affiche cette aide\n"
        "• `/stats` — produits surveillés, en stock, état des alertes\n"
        "• `/watchlist` — liste des produits suivis\n"
        "• `/add <url>` — ajouter un produit à surveiller\n"
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


async def ajouter_produit_url(url: str) -> str:
    url = (url or "").strip()
    if not url.startswith("http"):
        return "❌ URL invalide (elle doit commencer par http)."
    enseigne = next((e for d, e in DOMAINES.items() if d in url), None)
    if not enseigne:
        return ("❌ Enseigne non reconnue pour cette URL.\n"
                "Enseignes gérées : " + ", ".join(sorted(set(DOMAINES.values()))))
    if await database.recuperer_produit(url):
        return "ℹ️ Ce produit est déjà dans la watchlist."
    titre = _titre_depuis_url(url)
    await database.ajouter_produit(url, titre, enseigne, False)
    return f"✅ Ajouté à la surveillance **[{enseigne}]** : {titre}"


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

    @tree.command(name="watchlist", description="Liste des produits surveillés")
    async def cmd_watchlist(interaction: discord.Interaction):
        await interaction.response.send_message(await texte_watchlist(), ephemeral=True)

    @tree.command(name="add", description="Ajouter un produit à surveiller")
    @app_commands.describe(url="Lien du produit à surveiller")
    async def cmd_add(interaction: discord.Interaction, url: str):
        await interaction.response.send_message(await ajouter_produit_url(url), ephemeral=True)

    @tree.command(name="pause", description="Couper les alertes (le bot continue de tourner)")
    async def cmd_pause(interaction: discord.Interaction):
        bot_state.set_pause(True)
        await interaction.response.send_message("⏸️ Alertes mises en pause.", ephemeral=True)

    @tree.command(name="resume", description="Réactiver les alertes")
    async def cmd_resume(interaction: discord.Interaction):
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
