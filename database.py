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
                dernier_vu REAL NOT NULL,
                date_decouverte REAL NOT NULL
            )
        """)
        await db.commit()
    logger.info("Base de données initialisée.")

async def recuperer_produit(url: str):
    """Retourne l'état d'un produit s'il existe."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM produits WHERE url = ?", (url,)) as cursor:
            return await cursor.fetchone()

async def ajouter_produit(url: str, titre: str, enseigne: str, en_stock: bool):
    """Ajoute un nouveau produit."""
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO produits (url, titre, enseigne, en_stock, dernier_vu, date_decouverte) VALUES (?, ?, ?, ?, ?, ?)",
            (url, titre, enseigne, int(en_stock), now, now)
        )
        await db.commit()

async def mettre_a_jour_stock(url: str, en_stock: bool):
    """Met à jour le statut de stock d'un produit."""
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE produits SET en_stock = ?, dernier_vu = ? WHERE url = ?",
            (int(en_stock), now, url)
        )
        await db.commit()

async def marquer_vu(url: str):
    """Met à jour uniquement le timestamp dernier_vu."""
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE produits SET dernier_vu = ? WHERE url = ?", (now, url))
        await db.commit()
