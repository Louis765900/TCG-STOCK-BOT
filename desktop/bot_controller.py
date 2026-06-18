"""
bot_controller.py — Pilote la boucle du bot pour une interface graphique.

Le bot (boucle asyncio) tourne dans un **thread dédié** avec sa propre boucle
d'événements, pour que l'IHM (Qt/QML) reste fluide. On peut le démarrer, l'arrêter
proprement et lire son statut en direct.

Réutilise tel quel main.main_loop() et bot_state — aucun duplicata de logique.
"""

from __future__ import annotations

import asyncio
import logging
import threading

import bot_state

logger = logging.getLogger("bot_controller")


class BotController:
    """Démarre/arrête la boucle du bot dans un thread, expose son statut."""

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None

    # ------------------------------------------------------------------ état
    def est_actif(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def get_status(self) -> dict:
        """Statut live (running, cycle, produits, dernières enseignes…)."""
        status = bot_state.get_status()
        status["thread_vivant"] = self.est_actif()
        return status

    # ------------------------------------------------------------- démarrage
    def demarrer(self) -> bool:
        """Lance le bot en arrière-plan. Retourne False s'il tournait déjà."""
        if self.est_actif():
            logger.info("Bot déjà actif — démarrage ignoré.")
            return False
        self._thread = threading.Thread(target=self._run, name="tcg-bot", daemon=True)
        self._thread.start()
        logger.info("Bot démarré (thread arrière-plan).")
        return True

    def _run(self) -> None:
        # Import tardif : évite de charger Playwright/discord tant qu'on ne démarre pas.
        import main
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_event = asyncio.Event()
        try:
            self._loop.run_until_complete(main.main_loop(stop_event=self._stop_event))
        except Exception as e:  # ne jamais faire crasher le thread silencieusement
            logger.error("Boucle du bot terminée sur erreur : %s", e, exc_info=True)
        finally:
            try:
                self._loop.close()
            except Exception:
                pass
            bot_state.set_status(running=False)
            logger.info("Thread du bot terminé.")

    # ---------------------------------------------------------------- arrêt
    def arreter(self, timeout: float = 40.0) -> bool:
        """Demande un arrêt propre et attend la fin du thread (jusqu'à timeout)."""
        if not self.est_actif():
            return True
        if self._loop and self._stop_event:
            # Déclenche l'Event depuis le thread de la boucle (thread-safe).
            self._loop.call_soon_threadsafe(self._stop_event.set)
        self._thread.join(timeout)
        arrete = not self.est_actif()
        logger.info("Arrêt du bot %s.", "réussi" if arrete else "non confirmé (timeout)")
        return arrete

    # --------------------------------------------------------------- redémarrage
    def redemarrer(self) -> bool:
        self.arreter()
        return self.demarrer()


# Instance partagée pratique pour l'appli.
controleur = BotController()
