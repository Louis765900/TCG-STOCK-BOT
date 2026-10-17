"""Gestion de la base de données SQLite asynchrone."""
import asyncio
import time
import logging
import aiosqlite
from config import DB_PATH

logger = logging.getLogger(__name__)

# Une connexion partagee par (base, boucle asyncio) : ouvrir/fermer SQLite a chaque
# requete coutait cher (I/O + verrous). En mode WAL, lectures et ecritures cohabitent.
# La cle inclut la boucle car l'appli de bureau pilote la base depuis un autre thread.
_connexions: dict = {}
_verrous: dict = {}


def _cle() -> tuple:
    return (DB_PATH, id(asyncio.get_running_loop()))


async def _conn() -> aiosqlite.Connection:
    cle = _cle()
    conn = _connexions.get(cle)
    if conn is not None:
        return conn
    verrou = _verrous.setdefault(cle, asyncio.Lock())
    async with verrou:
        conn = _connexions.get(cle)
        if conn is None:
            candidat = aiosqlite.connect(DB_PATH)
            try:  # thread daemon : un oubli de fermeture ne doit jamais bloquer l'arret
                candidat._thread.daemon = True
            except Exception:
                pass
            conn = await candidat
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA busy_timeout=5000")
            _connexions[cle] = conn
        return conn


async def fermer():
    """Ferme les connexions ouvertes (arret propre / tests)."""
    for cle, conn in list(_connexions.items()):
        _connexions.pop(cle, None)
        try:
            await conn.close()
        except Exception:
            pass


async def initialiser_db():
    db = await _conn()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS produits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            titre TEXT NOT NULL,
            enseigne TEXT NOT NULL,
            en_stock INTEGER NOT NULL,
            prix TEXT DEFAULT 'N/A',
            image_url TEXT DEFAULT '',
            derniere_alerte REAL DEFAULT 0,
            dernier_vu REAL NOT NULL,
            date_decouverte REAL NOT NULL,
            manuel INTEGER DEFAULT 0
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS cycle_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            cycle_num INTEGER NOT NULL,
            enseigne TEXT NOT NULL,
            statut TEXT NOT NULL,
            produits_trouves INTEGER DEFAULT 0,
            nouveautes INTEGER DEFAULT 0,
            restocks INTEGER DEFAULT 0,
            ruptures INTEGER DEFAULT 0,
            duree_s REAL DEFAULT 0.0
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            prix_value REAL NOT NULL,
            en_stock INTEGER NOT NULL,
            timestamp REAL NOT NULL
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_price_history_url ON price_history(url, timestamp)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_produits_enseigne ON produits(enseigne)"
    )
    await _migrer_colonnes(db)
    await db.commit()
    logger.info("Base de données initialisée.")


async def _migrer_colonnes(db):
    """Ajoute les colonnes manquantes si la table existait avant Chantier 4."""
    async with db.execute("PRAGMA table_info(produits)") as cursor:
        colonnes = {row[1] async for row in cursor}
    if "prix" not in colonnes:
        await db.execute("ALTER TABLE produits ADD COLUMN prix TEXT DEFAULT 'N/A'")
        logger.info("Migration: colonne 'prix' ajoutée.")
    if "image_url" not in colonnes:
        await db.execute("ALTER TABLE produits ADD COLUMN image_url TEXT DEFAULT ''")
        logger.info("Migration: colonne 'image_url' ajoutée.")
    if "derniere_alerte" not in colonnes:
        await db.execute("ALTER TABLE produits ADD COLUMN derniere_alerte REAL DEFAULT 0")
        logger.info("Migration: colonne 'derniere_alerte' ajoutée.")
    if "manuel" not in colonnes:
        # 1 = ajoute a la main (/watch, /add) : jamais purge par le filtre automatique.
        await db.execute("ALTER TABLE produits ADD COLUMN manuel INTEGER DEFAULT 0")
        logger.info("Migration: colonne 'manuel' ajoutée.")


async def recuperer_produit(url: str):
    db = await _conn()
    async with db.execute("SELECT * FROM produits WHERE url = ?", (url,)) as cursor:
        return await cursor.fetchone()


async def recuperer_tous_produits() -> list[dict]:
    """Retourne tous les produits connus (watchlist)."""
    db = await _conn()
    async with db.execute("SELECT * FROM produits ORDER BY enseigne, titre") as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def ajouter_produit(url: str, titre: str, enseigne: str, en_stock: bool,
                          prix: str = "N/A", image_url: str = "", manuel: bool = False):
    now = time.time()
    # Garde-fou : SQLite n'accepte que des types simples. Un champ inattendu
    # (ex. image renvoyée comme objet par une API) ne doit jamais tout bloquer.
    if not isinstance(image_url, str):
        image_url = ""
    if not isinstance(prix, str):
        prix = str(prix) if prix is not None else "N/A"
    db = await _conn()
    await db.execute(
        """INSERT INTO produits
           (url, titre, enseigne, en_stock, prix, image_url, dernier_vu, date_decouverte, manuel)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (url, titre, enseigne, int(en_stock), prix, image_url, now, now, int(manuel))
    )
    await db.commit()


async def mettre_a_jour_stock(url: str, en_stock: bool, prix: str | None = None):
    now = time.time()
    db = await _conn()
    if prix is not None:
        await db.execute(
            "UPDATE produits SET en_stock = ?, prix = ?, dernier_vu = ? WHERE url = ?",
            (int(en_stock), prix, now, url)
        )
    else:
        await db.execute(
            "UPDATE produits SET en_stock = ?, dernier_vu = ? WHERE url = ?",
            (int(en_stock), now, url)
        )
    await db.commit()


async def supprimer_produit(url: str):
    """Retire un produit de la watchlist (et son historique de prix)."""
    db = await _conn()
    await db.execute("DELETE FROM produits WHERE url = ?", (url,))
    await db.execute("DELETE FROM price_history WHERE url = ?", (url,))
    await db.commit()


async def retirer_produit(url: str) -> bool:
    """Retire un produit de la watchlist ; True s'il existait."""
    if await recuperer_produit(url) is None:
        return False
    await supprimer_produit(url)
    return True


async def marquer_vu(url: str):
    db = await _conn()
    await db.execute("UPDATE produits SET dernier_vu = ? WHERE url = ?", (time.time(), url))
    await db.commit()


async def enregistrer_cycle(timestamp: float, cycle_num: int, enseigne: str, statut: str,
                             produits_trouves: int, nouveautes: int, restocks: int,
                             ruptures: int, duree_s: float):
    db = await _conn()
    await db.execute(
        """INSERT INTO cycle_logs
           (timestamp, cycle_num, enseigne, statut, produits_trouves, nouveautes, restocks, ruptures, duree_s)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (timestamp, cycle_num, enseigne, statut, produits_trouves, nouveautes, restocks, ruptures, duree_s)
    )
    await db.commit()


async def enregistrer_prix(url: str, prix_value: float, en_stock: bool):
    """Ajoute un point d'historique de prix (seulement si le prix est numérique)."""
    db = await _conn()
    await db.execute(
        "INSERT INTO price_history (url, prix_value, en_stock, timestamp) VALUES (?, ?, ?, ?)",
        (url, prix_value, int(en_stock), time.time())
    )
    await db.commit()


async def purger_historique_prix(jours: int = 90) -> int:
    """Supprime les points d'historique plus vieux que `jours` (garde la base légère)."""
    limite = time.time() - jours * 86400
    db = await _conn()
    cur = await db.execute("DELETE FROM price_history WHERE timestamp < ?", (limite,))
    await db.commit()
    return cur.rowcount or 0


async def recuperer_historique_prix(url: str, limite: int = 60) -> list[dict]:
    """Retourne l'historique de prix d'un produit, du plus ancien au plus récent."""
    db = await _conn()
    async with db.execute(
        "SELECT prix_value, en_stock, timestamp FROM price_history "
        "WHERE url = ? ORDER BY timestamp DESC LIMIT ?",
        (url, limite)
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in reversed(rows)]


async def enregistrer_alerte(url: str, timestamp: float | None = None):
    """Mémorise l'instant de la dernière alerte envoyée pour ce produit (anti-spam)."""
    ts = timestamp if timestamp is not None else time.time()
    db = await _conn()
    await db.execute("UPDATE produits SET derniere_alerte = ? WHERE url = ?", (ts, url))
    await db.commit()


async def reserver_alerte(url: str, maintenant: float, fenetre: float) -> float | None:
    """Reserve ATOMIQUEMENT le droit d'alerter pour `url`.

    Un UPDATE conditionnel unique : si deux taches tentent en meme temps, une seule
    obtient la reservation (anti-doublon sans course lecture/ecriture).
    Retourne l'ancienne valeur de `derniere_alerte` (pour la restituer si l'envoi
    echoue), ou None si une alerte recente existe deja. Produit inconnu : rien a
    proteger, l'alerte est autorisee (retourne 0.0).
    """
    db = await _conn()
    async with db.execute("SELECT derniere_alerte FROM produits WHERE url = ?", (url,)) as cur:
        row = await cur.fetchone()
    if row is None:
        return 0.0
    ancienne = row["derniere_alerte"] or 0.0
    cur = await db.execute(
        "UPDATE produits SET derniere_alerte = ? WHERE url = ? "
        "AND (derniere_alerte IS NULL OR derniere_alerte <= ?)",
        (maintenant, url, maintenant - fenetre),
    )
    await db.commit()
    return ancienne if cur.rowcount == 1 else None


async def mettre_a_jour_image(url: str, image_url: str):
    """Backfill de l'image d'un produit existant si elle manquait."""
    if not isinstance(image_url, str):
        return
    db = await _conn()
    await db.execute(
        "UPDATE produits SET image_url = ? WHERE url = ? AND (image_url IS NULL OR image_url = '')",
        (image_url, url)
    )
    await db.commit()


def _percentile(valeurs: list[float], q: float) -> float:
    """Percentile par rang le plus proche (suffisant pour un tableau de bord)."""
    if not valeurs:
        return 0.0
    v = sorted(valeurs)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))]


async def stats_enseignes(heures: float = 24.0) -> dict[str, dict]:
    """Sante et latence par enseigne sur la fenetre recente (table cycle_logs).

    Retourne {enseigne: {cycles, ok, taux_ok, duree_moy, duree_p95, dernier_statut}}.
    """
    limite = time.time() - heures * 3600
    db = await _conn()
    async with db.execute(
        "SELECT enseigne, statut, duree_s FROM cycle_logs WHERE timestamp >= ? "
        "ORDER BY timestamp", (limite,)
    ) as cur:
        rows = await cur.fetchall()
    par: dict[str, list] = {}
    for r in rows:
        par.setdefault(r["enseigne"], []).append((r["statut"], r["duree_s"] or 0.0))
    out = {}
    for ens, lignes in par.items():
        durees = [d for _, d in lignes]
        ok = sum(1 for st, _ in lignes if st == "healthy")
        out[ens] = {
            "cycles": len(lignes),
            "ok": ok,
            "taux_ok": ok / len(lignes),
            "duree_moy": sum(durees) / len(durees),
            "duree_p95": _percentile(durees, 0.95),
            "dernier_statut": lignes[-1][0],
        }
    return out
