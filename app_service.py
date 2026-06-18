"""
app_service.py — Couche service de l'application (sans Qt, donc testable seule).

Fait le lien entre l'interface graphique et le reste du bot. Tout ce qui est
asynchrone (base de données, envoi Discord) tourne sur une **petite boucle
asyncio de service** dans son propre thread — distincte de la boucle du bot
(cf. bot_controller). On évite ainsi tout conflit de boucle.

Le pont Qt (gui_bridge.py) ne fait qu'envelopper ce module : aucune logique
métier dans le code Qt.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque

import config
import bot_state
import database
from bot_controller import controleur
from product_format import STORE_COLORS

logger = logging.getLogger("app_service")


# ---------------------------------------------------------------------------
# Boucle asyncio de service (thread dédié) : exécute les coroutines courtes
# (lecture watchlist, envoi manuel…) sans bloquer l'IHM ni la boucle du bot.
# ---------------------------------------------------------------------------
class _ServiceLoop:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run, name="tcg-service", daemon=True
        )
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def executer(self, coro, timeout: float = 30.0):
        """Lance une coroutine sur la boucle de service et attend son résultat."""
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout)

    def arreter(self):
        self._loop.call_soon_threadsafe(self._loop.stop)


_service: _ServiceLoop | None = None


def _boucle() -> _ServiceLoop:
    global _service
    if _service is None:
        _service = _ServiceLoop()
    return _service


# ---------------------------------------------------------------------------
# Tampon de logs : un handler logging mémorise les dernières lignes pour l'IHM
# et notifie un éventuel abonné (le pont Qt) à chaque nouvelle ligne.
# ---------------------------------------------------------------------------
class TamponLogs(logging.Handler):
    def __init__(self, capacite: int = 500):
        super().__init__()
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                             datefmt="%H:%M:%S"))
        self._lignes: deque[str] = deque(maxlen=capacite)
        self._abonne = None  # callable(str) appelé à chaque nouvelle ligne

    def emit(self, record):
        try:
            ligne = self.format(record)
        except Exception:
            return
        self._lignes.append(ligne)
        if self._abonne is not None:
            try:
                self._abonne(ligne)
            except Exception:
                pass

    def lignes(self) -> list[str]:
        return list(self._lignes)

    def sur_nouvelle_ligne(self, callback):
        self._abonne = callback


_tampon: TamponLogs | None = None


def installer_capture_logs(capacite: int = 500) -> TamponLogs:
    """Branche le tampon sur le logger racine (idempotent)."""
    global _tampon
    if _tampon is None:
        _tampon = TamponLogs(capacite)
        logging.getLogger().addHandler(_tampon)
    return _tampon


def tampon_logs() -> TamponLogs:
    return installer_capture_logs()


# ---------------------------------------------------------------------------
# Bot : démarrage / arrêt / statut (délégué au contrôleur existant)
# ---------------------------------------------------------------------------
def demarrer_bot() -> bool:
    return controleur.demarrer()


def arreter_bot(timeout: float = 40.0) -> bool:
    return controleur.arreter(timeout)


def redemarrer_bot() -> bool:
    return controleur.redemarrer()


def bot_actif() -> bool:
    return controleur.est_actif()


def statut() -> dict:
    """Statut live enrichi (uptime lisible) pour l'IHM."""
    s = controleur.get_status()
    demarre = s.get("demarre_a", 0.0)
    s["uptime_s"] = max(0.0, time.time() - demarre) if demarre else 0.0
    return s


# ---------------------------------------------------------------------------
# Watchlist (base de données)
# ---------------------------------------------------------------------------
def lister_watchlist() -> list[dict]:
    """Tous les produits surveillés. Vide si la base n'existe pas encore."""
    try:
        return _boucle().executer(database.recuperer_tous_produits())
    except Exception as e:
        logger.warning("Lecture watchlist impossible : %s", e)
        return []


def supprimer_produit(url: str) -> bool:
    try:
        _boucle().executer(database.supprimer_produit(url))
        return True
    except Exception as e:
        logger.error("Suppression produit échouée : %s", e)
        return False


# ---------------------------------------------------------------------------
# Compositeur : envoi d'un message Discord manuel
# ---------------------------------------------------------------------------
def _to_int_couleur(couleur) -> int:
    """Accepte un int, '#RRGGBB' ou 'RRGGBB' ; défaut rouge bot."""
    if isinstance(couleur, int):
        return couleur
    if isinstance(couleur, str) and couleur.strip():
        try:
            return int(couleur.strip().lstrip("#"), 16)
        except ValueError:
            pass
    return 0xE30613


def envoyer_message_compose(titre: str = "", description: str = "",
                            couleur="#5865F2", image_url: str = "",
                            url: str = "", footer: str = "",
                            content: str = "") -> bool:
    """
    Construit un embed à partir des champs du compositeur et l'envoie.

    Au moins un de titre/description/content doit être non vide.
    """
    if not any([titre.strip(), description.strip(), content.strip()]):
        logger.warning("Message vide — envoi annulé.")
        return False
    embed: dict = {"color": _to_int_couleur(couleur)}
    if titre.strip():
        embed["title"] = titre.strip()[:256]
    if description.strip():
        embed["description"] = description.strip()[:4096]
    if url.strip():
        embed["url"] = url.strip()
    if image_url.strip():
        embed["image"] = {"url": image_url.strip()}
    if footer.strip():
        embed["footer"] = {"text": footer.strip()[:2048]}
    from discord_webhook import poster_embed
    try:
        return _boucle().executer(poster_embed(embed, content=content.strip()), timeout=45.0)
    except Exception as e:
        logger.error("Envoi du message composé échoué : %s", e)
        return False


# ---------------------------------------------------------------------------
# Réglages (lecture des valeurs courantes + écriture via la couche utilisateur)
# ---------------------------------------------------------------------------
# Clés exposées à l'assistant / aux réglages de l'appli, avec leur valeur live.
_CLES_REGLAGES = [
    "DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID", "DISCORD_WEBHOOK_URL",
    "DISCORD_ALERT_ROLE_ID", "ENABLED_STORES", "MIN_SLEEP", "MAX_SLEEP",
    "MASQUER_REVENDEURS", "DEAL_DROP_PERCENT", "HEARTBEAT_INTERVAL",
]


def lire_reglages() -> dict:
    """Valeurs courantes des réglages exposés (depuis la config live)."""
    import os
    valeurs = {}
    for cle in _CLES_REGLAGES:
        # On lit la valeur effective de config si elle existe, sinon l'env brut.
        attr = getattr(config, cle, None)
        if isinstance(attr, list):
            valeurs[cle] = ",".join(attr)
        elif attr is not None and not callable(attr):
            valeurs[cle] = str(attr)
        else:
            valeurs[cle] = os.getenv(cle, "")
    return valeurs


def enregistrer_reglages(reglages: dict) -> str:
    """Sauvegarde les réglages utilisateur (et les applique à l'environnement)."""
    propres = {k: v for k, v in reglages.items() if k in _CLES_REGLAGES}
    return config.sauver_reglages_utilisateur(propres)


def couleurs_enseignes() -> dict:
    """Pour l'IHM : couleur (hex) par enseigne connue."""
    return {nom: f"#{val:06X}" for nom, val in STORE_COLORS.items()}
