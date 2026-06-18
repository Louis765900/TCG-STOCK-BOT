"""
gui_bridge.py — Pont Qt entre l'interface QML et la couche service (app_service).

Expose au QML : le statut live du bot, le démarrage/arrêt, la watchlist, les
logs en direct, les réglages et l'envoi de messages. Aucune logique métier ici :
on ne fait qu'envelopper app_service et émettre des signaux Qt.

Les opérations potentiellement longues (arrêt du bot, requêtes base, envoi
Discord) tournent dans un thread de travail pour garder l'IHM fluide ; le
résultat revient au thread UI via un signal Qt (connexion en file d'attente).
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal, Slot, QTimer, Property

import app_service


def _en_arriere_plan(fn, *args):
    """Exécute fn(*args) dans un thread daemon (résultat propagé par signal)."""
    threading.Thread(target=fn, args=args, daemon=True).start()


class GuiBridge(QObject):
    # --- signaux vers le QML -------------------------------------------------
    statusChanged = Signal("QVariant")       # statut live (dict) à chaque tick
    watchlistChanged = Signal("QVariant")    # liste de produits
    logLine = Signal(str)                     # nouvelle ligne de log
    messageEnvoye = Signal(bool)              # résultat d'un envoi composé
    botBascule = Signal(bool)                 # True=démarré, False=arrêté
    erreur = Signal(str)                      # message d'erreur à afficher

    def __init__(self, parent=None):
        super().__init__(parent)
        # Capture des logs → signal logLine (le callback peut venir d'un autre thread,
        # l'émission de signal Qt est délivrée en file d'attente : c'est sûr).
        tampon = app_service.installer_capture_logs()
        tampon.sur_nouvelle_ligne(self.logLine.emit)
        self._logs_initiaux = tampon.lignes()

        # Sondage du statut toutes les secondes.
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick_statut)
        self._timer.start()
        self._dernier_running = None

    # ------------------------------------------------------------ statut
    def _tick_statut(self):
        s = app_service.statut()
        self.statusChanged.emit(s)
        running = bool(s.get("running"))
        if running != self._dernier_running:
            self._dernier_running = running
            self.botBascule.emit(running)

    @Slot(result="QVariant")
    def statut(self):
        return app_service.statut()

    @Slot(result=bool)
    def botActif(self):
        return app_service.bot_actif()

    # ------------------------------------------------------------ contrôle bot
    @Slot()
    def demarrer(self):
        def job():
            ok = app_service.demarrer_bot()
            if not ok:
                self.erreur.emit("Le bot tourne déjà.")
        _en_arriere_plan(job)

    @Slot()
    def arreter(self):
        def job():
            ok = app_service.arreter_bot()
            if not ok:
                self.erreur.emit("Arrêt non confirmé (délai dépassé).")
        _en_arriere_plan(job)

    @Slot()
    def redemarrer(self):
        _en_arriere_plan(app_service.redemarrer_bot)

    # ------------------------------------------------------------ watchlist
    @Slot()
    def rafraichirWatchlist(self):
        def job():
            self.watchlistChanged.emit(app_service.lister_watchlist())
        _en_arriere_plan(job)

    @Slot(str, result=bool)
    def supprimerProduit(self, url: str):
        ok = app_service.supprimer_produit(url)
        if ok:
            self.rafraichirWatchlist()
        return ok

    # ------------------------------------------------------------ logs
    @Slot(result="QVariant")
    def logsInitiaux(self):
        return self._logs_initiaux

    # ------------------------------------------------------------ réglages
    @Slot(result="QVariant")
    def lireReglages(self):
        return app_service.lire_reglages()

    @Slot("QVariant", result=str)
    def enregistrerReglages(self, reglages):
        try:
            return app_service.enregistrer_reglages(dict(reglages))
        except Exception as e:
            self.erreur.emit(f"Échec sauvegarde : {e}")
            return ""

    @Slot(result="QVariant")
    def couleursEnseignes(self):
        return app_service.couleurs_enseignes()

    # ------------------------------------------------------------ compositeur
    @Slot("QVariant")
    def envoyerMessage(self, champs):
        """champs : dict {titre, description, couleur, image_url, url, footer, content}."""
        c = dict(champs)
        def job():
            ok = app_service.envoyer_message_compose(
                titre=c.get("titre", ""),
                description=c.get("description", ""),
                couleur=c.get("couleur", "#5865F2"),
                image_url=c.get("image_url", ""),
                url=c.get("url", ""),
                footer=c.get("footer", ""),
                content=c.get("content", ""),
            )
            self.messageEnvoye.emit(ok)
        _en_arriere_plan(job)
