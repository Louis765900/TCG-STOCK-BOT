import logging
import aiofiles

logger = logging.getLogger(__name__)

async def debug_dump(page, enseigne: str):
    """
    Extrait le HTML de la page, le sauvegarde via aiofiles,
    et check les mots-clés de blocage anti-bot.
    """
    try:
        html = await page.content()
        filename = f"debug_erreur_{enseigne.lower()}.html"
        
        async with aiofiles.open(filename, mode='w', encoding='utf-8') as f:
            await f.write(html)
            
        logger.info(f"[{enseigne}] 🕵️ HTML de debug sauvegardé dans {filename}")
        
        # Mots-clés indiquant une sécurité / un captcha
        mots_cles = ["datadome", "challenge", "captcha", "interruption", "cloudflare", "verify you are human"]
        html_lower = html.lower()
        
        for mot in mots_cles:
            if mot in html_lower:
                logger.warning(f"[{enseigne}] ⚠️ BLOCAGE ANTI-BOT DÉTECTÉ : Le mot-clé '{mot}' a été trouvé dans la page !")
                break
                
    except Exception as e:
        logger.error(f"[{enseigne}] Erreur lors du debug_dump: {e}")
