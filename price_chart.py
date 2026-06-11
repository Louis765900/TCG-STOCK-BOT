"""Génération d'un graphique d'historique de prix (PNG en mémoire)."""
import io
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# matplotlib est optionnel : si absent, on dégrade proprement (pas de graphique).
try:
    import matplotlib
    matplotlib.use("Agg")  # backend sans affichage, indispensable hors GUI
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    _MATPLOTLIB_OK = True
except Exception:  # pragma: no cover
    _MATPLOTLIB_OK = False


def generer_graphique_prix(historique: list[dict], titre: str, couleur: int = 0xE30613) -> bytes | None:
    """
    Construit un PNG de l'évolution du prix.
    `historique`: liste de dicts {prix_value, en_stock, timestamp} triée du plus ancien au plus récent.
    Retourne les octets PNG, ou None si impossible (matplotlib absent, < 2 points).
    """
    if not _MATPLOTLIB_OK:
        logger.debug("matplotlib indisponible — graphique ignoré.")
        return None

    points = [h for h in historique if h.get("prix_value")]
    if len(points) < 2:
        return None

    dates = [datetime.fromtimestamp(h["timestamp"]) for h in points]
    prix = [float(h["prix_value"]) for h in points]
    hex_couleur = f"#{couleur:06x}"

    fig, ax = plt.subplots(figsize=(6.0, 3.0), dpi=110)
    fig.patch.set_facecolor("#2b2d31")  # fond façon Discord dark
    ax.set_facecolor("#2b2d31")

    ax.plot(dates, prix, color=hex_couleur, linewidth=2.0, marker="o",
            markersize=4, markerfacecolor=hex_couleur)
    ax.fill_between(dates, prix, min(prix), color=hex_couleur, alpha=0.12)

    # Met en évidence min / max
    pmin, pmax = min(prix), max(prix)
    if pmax != pmin:
        i_min, i_max = prix.index(pmin), prix.index(pmax)
        ax.annotate(f"{pmin:.2f}€", (dates[i_min], pmin), color="#43b581",
                    fontsize=8, xytext=(0, -12), textcoords="offset points", ha="center")
        ax.annotate(f"{pmax:.2f}€", (dates[i_max], pmax), color="#f04747",
                    fontsize=8, xytext=(0, 6), textcoords="offset points", ha="center")

    titre_court = (titre[:42] + "…") if len(titre) > 43 else titre
    ax.set_title(f"Évolution du prix — {titre_court}", color="#ffffff", fontsize=10, pad=10)

    ax.tick_params(colors="#b9bbbe", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#4f545c")
    ax.grid(True, color="#40444b", linewidth=0.5, alpha=0.6)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M"))
    fig.autofmt_xdate(rotation=30, ha="right")
    ax.margins(y=0.2)

    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    except Exception as e:
        logger.warning("Échec génération graphique: %s", e)
        return None
    finally:
        plt.close(fig)

    return buf.getvalue()
