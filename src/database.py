"""Gestion de la base de données SQLite asynchrone."""
import time
import logging
import aiosqlite
from config import DB_PATH

logger = logging.getLogger(__name__)


async def initialiser_db():
    async with aiosqlite.connect(DB_PATH) as db:
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
                date_decouverte REAL NOT NULL
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
            "CREATE INDEX IF NOT EXISTS idx_price_history_url ON price_history(url)"
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


async def recuperer_produit(url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM produits WHERE url = ?", (url,)) as cursor:
            return await cursor.fetchone()


async def recuperer_tous_produits() -> list[dict]:
    """Retourne tous les produits connus (watchlist)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM produits ORDER BY enseigne, titre"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def ajouter_produit(url: str, titre: str, enseigne: str, en_stock: bool,
                          prix: str = "N/A", image_url: str = ""):
    now = time.time()
    # Garde-fou : SQLite n'accepte que des types simples. Un champ inattendu
    # (ex. image renvoyée comme objet par une API) ne doit jamais tout bloquer.
    if not isinstance(image_url, str):
        image_url = ""
    if not isinstance(prix, str):
        prix = str(prix) if prix is not None else "N/A"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO produits
               (url, titre, enseigne, en_stock, prix, image_url, dernier_vu, date_decouverte)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (url, titre, enseigne, int(en_stock), prix, image_url, now, now)
        )
        await db.commit()


async def mettre_a_jour_stock(url: str, en_stock: bool, prix: str | None = None):
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM produits WHERE url = ?", (url,))
        await db.execute("DELETE FROM price_history WHERE url = ?", (url,))
        await db.commit()


async def marquer_vu(url: str):
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE produits SET dernier_vu = ? WHERE url = ?", (now, url))
        await db.commit()


async def enregistrer_cycle(timestamp: float, cycle_num: int, enseigne: str, statut: str,
                             produits_trouves: int, nouveautes: int, restocks: int,
                             ruptures: int, duree_s: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO cycle_logs
               (timestamp, cycle_num, enseigne, statut, produits_trouves, nouveautes, restocks, ruptures, duree_s)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, cycle_num, enseigne, statut, produits_trouves, nouveautes, restocks, ruptures, duree_s)
        )
        await db.commit()


async def enregistrer_prix(url: str, prix_value: float, en_stock: bool):
    """Ajoute un point d'historique de prix (seulement si le prix est numérique)."""
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO price_history (url, prix_value, en_stock, timestamp) VALUES (?, ?, ?, ?)",
            (url, prix_value, int(en_stock), now)
        )
        await db.commit()


async def purger_historique_prix(jours: int = 90) -> int:
    """Supprime les points d'historique plus vieux que `jours` (garde la base légère)."""
    limite = time.time() - jours * 86400
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM price_history WHERE timestamp < ?", (limite,))
        await db.commit()
        return cur.rowcount or 0


async def recuperer_historique_prix(url: str, limite: int = 60) -> list[dict]:
    """Retourne l'historique de prix d'un produit, du plus ancien au plus récent."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE produits SET derniere_alerte = ? WHERE url = ?", (ts, url)
        )
        await db.commit()


async def mettre_a_jour_image(url: str, image_url: str):
    """Backfill de l'image d'un produit existant si elle manquait."""
    if not isinstance(image_url, str):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE produits SET image_url = ? WHERE url = ? AND (image_url IS NULL OR image_url = '')",
            (image_url, url)
        )
        await db.commit()
