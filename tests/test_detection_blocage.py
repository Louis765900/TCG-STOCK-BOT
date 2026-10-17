"""Detection de blocage : pas de faux positifs sur de vraies pages, vrais blocages reperes ;
redirections : seules celles qui restent sur le site en https sont acceptees."""
import os
import sys
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))

from anti_bot_bypass import detecter_type_blocage
from http_fetch import redirection_sure
from store_domains import hote_appartient, meme_site

_CORPS = ('<div class="product-miniature">Coffret Pokemon</div>' * 800)


def test_detection():
    # Vraie page produit qui embarque reCAPTCHA / datadome : PAS un blocage.
    vraie = ('<html><script type="application/ld+json">{"@type":"Product"}</script>'
             '<script src="https://js.datadome.co/tag.js"></script>'
             '<div class="g-recaptcha"></div>' + _CORPS + '</html>')
    assert len(vraie) > 30000 and detecter_type_blocage(vraie) is None
    # Page normale sans aucune mention.
    assert detecter_type_blocage("<html>" + _CORPS + "</html>") is None

    # Vrais challenges (courts).
    dd = '<html><iframe src="https://geo.captcha-delivery.com/captcha/?x=1"></iframe></html>'
    assert detecter_type_blocage(dd) == "datadome"
    cf = "<html><title>Just a moment...</title><script src='/cdn-cgi/challenge-platform/x'></script></html>"
    assert detecter_type_blocage(cf) == "cloudflare"
    assert detecter_type_blocage("<html><body>Access Denied</body></html>") == "generic_bot"
    assert detecter_type_blocage("<html><div class='g-recaptcha'></div></html>") == "captcha"
    assert detecter_type_blocage("") == "empty"
    # Meme une grande page : une signature FORTE reste un blocage.
    assert detecter_type_blocage(_CORPS + "geo.captcha-delivery.com") == "datadome"


def test_redirections():
    o = "https://www.auchan.fr/p/x"
    assert redirection_sure(o, "https://auchan.fr/p/x")                 # www <-> nu
    assert redirection_sure(o, "https://m.auchan.fr/p/x")               # sous-domaine
    assert not redirection_sure(o, "http://www.auchan.fr/p/x")          # retrogradation http
    assert not redirection_sure(o, "https://evil.com/?r=auchan.fr")     # autre site
    assert not redirection_sure(o, "https://auchan.fr.evil.com/")       # faux sous-domaine
    assert not redirection_sure(o, "https://127.0.0.1/admin")           # IP interne
    assert not redirection_sure(o, "https://169.254.169.254/latest/")   # metadonnees cloud
    assert not redirection_sure(o, "https://[::1]/")
    assert not redirection_sure(o, "https://localhost/")
    assert not redirection_sure(o, "https://user:pw@www.auchan.fr/")
    assert not redirection_sure(o, "https://www.auchan.fr:8443/")
    assert not redirection_sure(o, "file:///etc/passwd")
    assert hote_appartient("www.smythstoys.com", "smythstoys")
    assert not hote_appartient("smythstoys.evil.com.x", "auchan.fr")
    assert meme_site("www.relictcg.com", "relictcg.com")
    assert not meme_site("relictcg.com", "evil.com")


def test_statuts_http():
    import asyncio
    import http_fetch
    page = "<html>" + _CORPS + "</html>"
    scenarios = {
        "https://www.auchan.fr/redir-ok": [(301, "", {"Location": "/final"}), (200, page, {})],
        "https://www.auchan.fr/redir-evil": [(302, "", {"Location": "https://evil.com/x"})],
        "https://www.auchan.fr/redir-ip": [(302, "", {"Location": "https://10.0.0.1/x"})],
        "https://www.auchan.fr/boucle": [(302, "", {"Location": "/boucle"})] * 10,
        "https://www.auchan.fr/gone": [(404, "nope", {})],
        "https://www.auchan.fr/403": [(403, "", {})],
        "https://www.auchan.fr/500": [(500, "", {})],
    }
    appels = []

    async def faux_get(url, accept, extra, timeout_s):
        appels.append(url)
        file = scenarios.get(url) or scenarios[url.rsplit("/", 1)[0] + "/redir-ok"]
        rep = file[min(sum(1 for u in appels if u == url) - 1, len(file) - 1)]
        if url.endswith("/final"):
            return 200, page, {}
        return rep

    reel, reel_secours = http_fetch._get_sans_redirection, http_fetch._secours_html
    http_fetch._get_sans_redirection = faux_get

    async def pas_de_secours(url, blocage):          # jamais de service tiers en test
        return None, "blocked", blocage
    http_fetch._secours_html = pas_de_secours
    try:
        async def go(u):
            return await http_fetch.http_get(u)
        r = asyncio.run(go("https://www.auchan.fr/redir-ok"))
        assert r[1] == "ok" and r[0] == page
        assert asyncio.run(go("https://www.auchan.fr/redir-evil"))[1:] == ("blocked", "redirect_non_fiable")
        assert asyncio.run(go("https://www.auchan.fr/redir-ip"))[1:] == ("blocked", "redirect_non_fiable")
        assert asyncio.run(go("https://www.auchan.fr/boucle"))[1:] == ("blocked", "redirect_non_fiable")
        assert asyncio.run(go("https://www.auchan.fr/gone"))[1:] == ("not_found", "http_404")
        assert asyncio.run(go("https://www.auchan.fr/403"))[1] == "blocked"
        assert asyncio.run(go("https://www.auchan.fr/500"))[1] == "timeout"
        # JSON : 404 -> not_found ; redirection hors site -> blocked
        assert asyncio.run(http_fetch.http_get_json("https://www.auchan.fr/gone"))[1] == "not_found"
        assert asyncio.run(http_fetch.http_get_json("https://www.auchan.fr/redir-evil"))[1] == "blocked"
    finally:
        http_fetch._get_sans_redirection, http_fetch._secours_html = reel, reel_secours


def test():
    test_statuts_http()
    test_detection()
    test_redirections()


if __name__ == "__main__":
    test()
    print("OK")
