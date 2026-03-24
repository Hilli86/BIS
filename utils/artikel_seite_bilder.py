"""
Abruf externer Seiten/Bilder für Artikelfoto-URL-Suche (SSRF-Schutz, Größenlimits).
"""

from __future__ import annotations

import html as html_module
import ipaddress
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import HTTPHandler, HTTPSHandler, Request, build_opener

# Kein HTTPRedirectHandler: Weiterleitungen werden manuell mit SSRF-Prüfung pro Ziel-URL verarbeitet.
_OPENER_OHNE_REDIRECT = build_opener(HTTPHandler(), HTTPSHandler())

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BIS-Artikelfoto/1.0"
)


class ArtikelSeiteFehler(Exception):
    """Fehler beim Abruf oder bei der Verarbeitung einer externen URL."""

    pass


def _hostname_ips_sicher(hostname: str) -> bool:
    """True, wenn alle aufgelösten IPs öffentlich erreichbar erscheinen (kein SSRF-Ziel)."""
    if not hostname:
        return False
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def _parse_http_url(url: str) -> tuple[str, str, int | None]:
    """Nur http/https. Gibt (scheme, host, port) zurück."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ArtikelSeiteFehler("Nur http- und https-URLs sind erlaubt.")
    host = parsed.hostname
    if not host:
        raise ArtikelSeiteFehler("Ungültige URL.")
    port = parsed.port
    return parsed.scheme, host, port


def url_fuer_abruf_erlaubt(url: str) -> None:
    """Wirft ArtikelSeiteFehler, wenn die URL nicht abgerufen werden darf."""
    _parse_http_url(url)
    _, host, _ = _parse_http_url(url)
    if not _hostname_ips_sicher(host):
        raise ArtikelSeiteFehler("Die URL zeigt auf eine nicht erlaubte Adresse.")


def _read_limited(resp, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total < max_bytes:
        chunk = resp.read(min(65536, max_bytes - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    if total >= max_bytes:
        extra = resp.read(1)
        if extra:
            raise ArtikelSeiteFehler("Antwort überschreitet die maximal erlaubte Größe.")
    return b"".join(chunks)


def http_get_bytes(
    url: str,
    *,
    max_bytes: int,
    timeout: float = 15.0,
    max_redirects: int = 5,
    accept_header: str = "*/*",
) -> tuple[bytes, str, str]:
    """
    Lädt Ressource per GET. Folgt Redirects manuell mit SSRF-Prüfung pro Ziel-Host.

    Returns:
        (body, finale_url, content_type_niedrig)
    """
    current = url.strip()
    for _ in range(max_redirects + 1):
        url_fuer_abruf_erlaubt(current)
        req = Request(
            current,
            headers={"User-Agent": USER_AGENT, "Accept": accept_header},
            method="GET",
        )
        try:
            resp = _OPENER_OHNE_REDIRECT.open(req, timeout=timeout)
        except HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                current = urljoin(current, e.headers.get("Location"))
                continue
            raise ArtikelSeiteFehler(f"HTTP-Fehler: {e.code}") from e
        except URLError as e:
            raise ArtikelSeiteFehler(f"Verbindungsfehler: {e.reason}") from e
        except OSError as e:
            raise ArtikelSeiteFehler(f"Netzwerkfehler: {e}") from e
        try:
            code = resp.getcode()
            if code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("Location")
                if not loc:
                    raise ArtikelSeiteFehler("Ungültige Weiterleitung.")
                current = urljoin(current, loc)
                continue
            data = _read_limited(resp, max_bytes)
            ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            final = resp.geturl() or current
            return data, final, ct
        finally:
            try:
                resp.close()
            except Exception:
                pass

    raise ArtikelSeiteFehler("Zu viele Weiterleitungen.")


_RE_IMG_SRC = re.compile(
    r'<img[^>]+(?:src|data-src)\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_RE_SRCSET = re.compile(r'srcset\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_RE_META_OG = re.compile(
    r'<meta[^>]+property\s*=\s*["\']og:image["\'][^>]+content\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_RE_META_OG2 = re.compile(
    r'<meta[^>]+content\s*=\s*["\']([^"\']+)["\'][^>]+property\s*=\s*["\']og:image["\']',
    re.IGNORECASE,
)
_RE_META_TW = re.compile(
    r'<meta[^>]+name\s*=\s*["\']twitter:image(?::src)?["\'][^>]+content\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_RE_META_TW2 = re.compile(
    r'<meta[^>]+content\s*=\s*["\']([^"\']+)["\'][^>]+name\s*=\s*["\']twitter:image(?::src)?["\']',
    re.IGNORECASE,
)


def _norm_url(raw: str, base_url: str) -> str | None:
    s = html_module.unescape(raw.strip())
    if not s or s.startswith("data:") or s.startswith("#"):
        return None
    if s.startswith("//"):
        parsed = urlparse(base_url)
        s = f"{parsed.scheme}:{s}"
    absolute = urljoin(base_url, s)
    parsed = urlparse(absolute)
    if parsed.scheme not in ("http", "https"):
        return None
    return urlunparse(parsed)


def _srcset_erste_url(srcset: str) -> str | None:
    """Erstes Kandidaten-URL-Fragment aus srcset (vereinfacht)."""
    part = srcset.split(",")[0].strip().split()[0] if srcset else ""
    return part or None


def extrahiere_bild_urls_aus_html(html: str, base_url: str, *, max_bilder: int = 50) -> list[str]:
    """Sammelt Bild-URLs aus HTML; Reihenfolge: Meta, dann img/srcset."""
    if not html:
        return []
    seen: set[str] = set()
    out: list[str] = []

    def add(u: str | None) -> None:
        if not u or len(out) >= max_bilder:
            return
        if u not in seen:
            seen.add(u)
            out.append(u)

    for rx in (_RE_META_OG, _RE_META_OG2, _RE_META_TW, _RE_META_TW2):
        for m in rx.finditer(html):
            u = _norm_url(m.group(1), base_url)
            add(u)

    for m in _RE_IMG_SRC.finditer(html):
        u = _norm_url(m.group(1), base_url)
        add(u)

    for m in _RE_SRCSET.finditer(html):
        first = _srcset_erste_url(m.group(1))
        if first:
            u = _norm_url(first, base_url)
            add(u)

    return out[:max_bilder]


# HTML-Seiten: genug Puffer für schwere Shop-Seiten; getrennt vom Bild-Download (16 MB in App).
_MAX_HTML_SEITE_BYTES = 8 * 1024 * 1024

_DIREKTE_BILD_ENDUNGEN = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg", ".bmp", ".ico")


def url_ist_vermutlich_direktes_bild(url: str) -> bool:
    """True, wenn der URL-Pfad typischerweise direkt auf eine Bilddatei zeigt."""
    path = (urlparse(url.strip()).path or "").lower()
    return any(path.endswith(ext) for ext in _DIREKTE_BILD_ENDUNGEN)


def bilder_aus_seiten_url(seiten_url: str) -> tuple[list[str], str]:
    """
    Liefert Bild-URLs: bei direkter Bild-URL ohne vollen Download nur SSRF-Prüfung;
    sonst HTML laden und parsen.

    Returns:
        (liste_absoluter_urls, basis_url_fuer_anzeige)
    """
    raw = (seiten_url or "").strip()
    if not raw:
        return [], ""

    if url_ist_vermutlich_direktes_bild(raw):
        url_fuer_abruf_erlaubt(raw)
        parsed = urlparse(raw)
        canonical = urlunparse(parsed)
        return [canonical], canonical

    return html_seite_bilder_laden(raw)


def html_seite_bilder_laden(seiten_url: str) -> tuple[list[str], str]:
    """
    Lädt HTML und extrahiert Bild-URLs.

    Returns:
        (liste_absoluter_urls, finale_seiten_url)
    """
    body, final_url, _ct = http_get_bytes(
        seiten_url,
        max_bytes=_MAX_HTML_SEITE_BYTES,
        timeout=15.0,
        max_redirects=5,
        accept_header="text/html,application/xhtml+xml,*/*;q=0.8",
    )
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        text = body.decode("latin-1", errors="replace")

    bilder = extrahiere_bild_urls_aus_html(text, final_url, max_bilder=50)
    return bilder, final_url


def bild_von_url_laden(image_url: str, *, max_bytes: int) -> tuple[bytes, str]:
    """
    Lädt Bildbytes von einer URL (gleiche SSRF-Regeln, Redirects mit Prüfung).

    Returns:
        (bytes, content_type_niedrig)
    """
    data, _final, ct = http_get_bytes(
        image_url,
        max_bytes=max_bytes,
        timeout=20.0,
        max_redirects=5,
        accept_header="image/*,*/*;q=0.8",
    )
    return data, ct
