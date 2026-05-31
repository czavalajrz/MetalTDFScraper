"""
Scraper para Reddit combinando dos fuentes sin credenciales:

1. Arctic Shift API  — archivo histórico académico, búsqueda por subreddit y keyword
   https://arctic-shift.photon-reddit.com
2. old.reddit.com    — HTML estático, datos recientes de r/MetalMexico

No requiere registro ni API key de Reddit.
"""

import uuid
import time
import random
from typing import Optional, Tuple
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from tqdm import tqdm

from config import (
    SUBREDDITS, ALL_KEYWORDS, MAX_POSTS_PER_SUBREDDIT, MAX_COMMENTS_PER_POST,
    USER_AGENT, DELAY_MIN, DELAY_MAX, MIN_TEXT_LENGTH, RAW_DATA_PATH
)
from utils.cleaner import clean_text, get_language, text_length
from utils.exporter import save_csv, save_json

HEADERS = {"User-Agent": USER_AGENT}

ARCTIC_BASE = "https://arctic-shift.photon-reddit.com/api"
OLD_REDDIT_BASE = "https://old.reddit.com"

SUBGENRE_KEYWORDS = {
    "death metal": ["death metal", "death/doom", "brutal death", "melodic death"],
    "black metal": ["black metal", "blackened"],
    "thrash metal": ["thrash metal", "thrash"],
    "doom metal": ["doom metal", "doom/death", "funeral doom"],
    "power metal": ["power metal"],
    "folk metal": ["folk metal"],
    "nu metal": ["nu metal", "nu-metal"],
    "metalcore": ["metalcore", "deathcore"],
    "heavy metal": ["heavy metal", "nwobhm"],
}

EVENT_KEYWORDS = [
    "hell and heaven", "mexico metal fest", "imperio azteca metal fest",
    "el chopo", "headbanging fest", "festival"
]

CITY_KEYWORDS = {
    "CDMX": ["cdmx", "ciudad de mexico", "ciudad de méxico", "df", "d.f.", "capital"],
    "Guadalajara": ["guadalajara", "gdl"],
    "Monterrey": ["monterrey", "mty", "regio"],
    "Puebla": ["puebla"],
    "Tijuana": ["tijuana"],
    "Querétaro": ["queretaro", "querétaro"],
}


def _timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_get(url, params=None, retries=3):
    """GET con reintentos ante errores 429/503/timeout."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 15))
                print(f"[MetalTDFScraper] {_timestamp()} — Rate limit 429, esperando {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code in (403, 404):
                print(f"[MetalTDFScraper] {_timestamp()} — {resp.status_code}: {url}")
                return None
            resp.raise_for_status()
            return resp
        except requests.exceptions.Timeout:
            print(f"[MetalTDFScraper] {_timestamp()} — Timeout ({attempt+1}/{retries}): {url}")
            time.sleep(5)
        except requests.exceptions.RequestException as e:
            print(f"[MetalTDFScraper] {_timestamp()} — Error request: {e}")
            time.sleep(5)
    return None


def _detect_subgenre(text: str) -> str:
    text_lower = text.lower()
    for genre, terms in SUBGENRE_KEYWORDS.items():
        for term in terms:
            if term in text_lower:
                return genre
    return ""


def _detect_event(text: str) -> str:
    text_lower = text.lower()
    for ev in EVENT_KEYWORDS:
        if ev in text_lower:
            return ev.title()
    return ""


def _detect_city(text: str) -> str:
    text_lower = text.lower()
    for city, terms in CITY_KEYWORDS.items():
        for term in terms:
            if term in text_lower:
                return city
    return ""


# ─────────────────────────────────────────────
# FUENTE 1: Arctic Shift API (datos históricos)
# ─────────────────────────────────────────────

def _arctic_post_to_record(post: dict) -> dict:
    """Convierte un post de Arctic Shift al esquema estándar."""
    title = post.get("title", "")
    selftext = post.get("selftext", "") or ""
    combined = f"{title} {selftext}"
    texto = clean_text(combined)

    fecha_ts = post.get("created_utc", 0)
    try:
        fecha = datetime.fromtimestamp(float(fecha_ts), tz=timezone.utc).isoformat() if fecha_ts else ""
    except Exception:
        fecha = str(fecha_ts)

    permalink = post.get("permalink", "")
    url = f"https://www.reddit.com{permalink}" if permalink else post.get("url", "")

    return {
        "id": str(uuid.uuid4()),
        "fuente": "reddit_arctic",
        "url": url,
        "fecha": fecha,
        "tipo_texto": "post",
        "autor": post.get("author", ""),
        "titulo": clean_text(title),
        "texto": texto,
        "banda": "",
        "subgenero": _detect_subgenre(combined),
        "ciudad": _detect_city(combined),
        "evento": _detect_event(combined),
        "idioma": get_language(texto),
        "engagement": str(post.get("score", 0)),
        "longitud_texto": text_length(texto),
    }


def _arctic_comment_to_record(comment: dict) -> dict:
    """Convierte un comentario de Arctic Shift al esquema estándar."""
    body = comment.get("body", "") or ""
    texto = clean_text(body)

    fecha_ts = comment.get("created_utc", 0)
    try:
        fecha = datetime.fromtimestamp(float(fecha_ts), tz=timezone.utc).isoformat() if fecha_ts else ""
    except Exception:
        fecha = str(fecha_ts)

    permalink = comment.get("permalink", "")
    url = f"https://www.reddit.com{permalink}" if permalink else ""

    return {
        "id": str(uuid.uuid4()),
        "fuente": "reddit_arctic",
        "url": url,
        "fecha": fecha,
        "tipo_texto": "comentario",
        "autor": comment.get("author", ""),
        "titulo": "",
        "texto": texto,
        "banda": "",
        "subgenero": _detect_subgenre(body),
        "ciudad": _detect_city(body),
        "evento": _detect_event(body),
        "idioma": get_language(texto),
        "engagement": str(comment.get("score", 0)),
        "longitud_texto": text_length(texto),
    }


def _arctic_fetch_posts(subreddit: str, keyword: str = None, limit: int = 100) -> list:
    """Obtiene posts de Arctic Shift para un subreddit (con o sin keyword)."""
    params = {"subreddit": subreddit, "limit": min(limit, 100)}
    if keyword:
        params["query"] = keyword

    resp = _safe_get(f"{ARCTIC_BASE}/posts/search", params=params)
    if not resp:
        return []
    try:
        return resp.json().get("data", [])
    except ValueError:
        return []


def _arctic_fetch_comments(subreddit: str, limit: int = 100) -> list:
    """Obtiene comentarios de Arctic Shift para un subreddit."""
    params = {"subreddit": subreddit, "limit": min(limit, 100)}
    resp = _safe_get(f"{ARCTIC_BASE}/comments/search", params=params)
    if not resp:
        return []
    try:
        return resp.json().get("data", [])
    except ValueError:
        return []


def scrape_arctic_shift() -> list:
    """
    Scrapea todos los subreddits via Arctic Shift:
    - r/MetalMexico: todos los posts + comentarios disponibles
    - Resto: búsqueda por keywords relevantes de metal en México
    """
    records = []
    seen_urls = set()

    def add(rec):
        key = rec["url"] or rec["id"]
        if key not in seen_urls:
            seen_urls.add(key)
            records.append(rec)

    # r/MetalMexico — todos los posts y comentarios
    print(f"\n[MetalTDFScraper] {_timestamp()} — Arctic Shift: r/MetalMexico (posts + comentarios)...")
    posts = _arctic_fetch_posts("MetalMexico", limit=MAX_POSTS_PER_SUBREDDIT)
    for p in posts:
        rec = _arctic_post_to_record(p)
        if rec["longitud_texto"] >= MIN_TEXT_LENGTH:
            add(rec)

    comments = _arctic_fetch_comments("MetalMexico", limit=MAX_COMMENTS_PER_POST * 10)
    for c in comments:
        rec = _arctic_comment_to_record(c)
        if rec["longitud_texto"] >= MIN_TEXT_LENGTH:
            add(rec)

    print(f"[MetalTDFScraper] MetalMexico: {len(records)} registros")
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    # Demás subreddits — búsqueda por keywords de metal mexicano
    # Usamos solo los keywords más específicos para no saturar
    mx_keywords = [kw for kw in ALL_KEYWORDS if any(
        term in kw.lower() for term in ["mexico", "méxico", "mexicano", "mexicana", "cdmx", "chopo"]
    )][:12]

    other_subreddits = [s for s in SUBREDDITS if s != "MetalMexico"]

    for subreddit in tqdm(other_subreddits, desc="Arctic Shift subreddits"):
        print(f"\n[MetalTDFScraper] {_timestamp()} — Arctic Shift: r/{subreddit}...")
        for kw in tqdm(mx_keywords, desc=f"  r/{subreddit}", leave=False):
            posts = _arctic_fetch_posts(subreddit, keyword=kw, limit=50)
            for p in posts:
                rec = _arctic_post_to_record(p)
                if rec["longitud_texto"] >= MIN_TEXT_LENGTH:
                    add(rec)
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    print(f"\n[MetalTDFScraper] {_timestamp()} — Arctic Shift total: {len(records)} registros")
    return records


# ─────────────────────────────────────────────
# FUENTE 2: old.reddit.com (datos recientes)
# ─────────────────────────────────────────────

def _parse_old_reddit_post(thing: BeautifulSoup) -> Optional[dict]:
    """Extrae un post del HTML de old.reddit.com."""
    try:
        title_el = thing.select_one("a.title")
        titulo = clean_text(title_el.get_text()) if title_el else ""

        url = thing.get("data-url", "") or (title_el["href"] if title_el else "")
        if url.startswith("/"):
            url = f"https://www.reddit.com{url}"

        author = thing.get("data-author", "")
        score = thing.get("data-score", "0")
        timestamp = thing.get("data-timestamp", "")
        permalink = thing.get("data-permalink", "")
        post_url = f"https://www.reddit.com{permalink}" if permalink else url

        # Fecha desde timestamp en milisegundos
        fecha = ""
        if timestamp:
            try:
                fecha = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc).isoformat()
            except Exception:
                pass

        texto = clean_text(titulo)
        combined = titulo

        return {
            "id": str(uuid.uuid4()),
            "fuente": "reddit_old",
            "url": post_url,
            "fecha": fecha,
            "tipo_texto": "post",
            "autor": author,
            "titulo": titulo,
            "texto": texto,
            "banda": "",
            "subgenero": _detect_subgenre(combined),
            "ciudad": _detect_city(combined),
            "evento": _detect_event(combined),
            "idioma": get_language(texto),
            "engagement": score,
            "longitud_texto": text_length(texto),
        }
    except Exception as e:
        print(f"[MetalTDFScraper] Error parseando post HTML: {e}")
        return None


def _fetch_old_reddit_page(subreddit: str, after: str = None) -> Tuple[list, Optional[str]]:
    """
    Obtiene una página de old.reddit.com y devuelve (posts, after_token).
    """
    url = f"{OLD_REDDIT_BASE}/r/{subreddit}/"
    params = {"limit": 25}
    if after:
        params["after"] = after

    resp = _safe_get(url, params=params)
    if not resp:
        return [], None

    soup = BeautifulSoup(resp.text, "lxml")
    things = soup.select("div.thing[data-author]")
    records = []
    for thing in things:
        rec = _parse_old_reddit_post(thing)
        if rec and rec["longitud_texto"] >= MIN_TEXT_LENGTH:
            records.append(rec)

    # Token de paginación
    next_btn = soup.select_one("span.next-button a")
    next_after = None
    if next_btn:
        href = next_btn.get("href", "")
        if "after=" in href:
            next_after = href.split("after=")[-1].split("&")[0]

    return records, next_after


def _fetch_old_reddit_comments(permalink: str) -> list:
    """Obtiene comentarios de un post vía old.reddit.com."""
    url = f"{OLD_REDDIT_BASE}{permalink}"
    resp = _safe_get(url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    post_url = f"https://www.reddit.com{permalink}"
    comments = []

    for div in soup.select("div.comment"):
        body_el = div.select_one("div.md")
        if not body_el:
            continue
        body = clean_text(body_el.get_text())
        if text_length(body) < MIN_TEXT_LENGTH:
            continue

        author_el = div.select_one("a.author")
        author = author_el.get_text() if author_el else ""

        time_el = div.select_one("time")
        fecha = time_el.get("datetime", "") if time_el else ""

        score_el = div.select_one("span.score")
        score = score_el.get("title", "0") if score_el else "0"

        rec = {
            "id": str(uuid.uuid4()),
            "fuente": "reddit_old",
            "url": post_url,
            "fecha": fecha,
            "tipo_texto": "comentario",
            "autor": author,
            "titulo": "",
            "texto": body,
            "banda": "",
            "subgenero": _detect_subgenre(body),
            "ciudad": _detect_city(body),
            "evento": _detect_event(body),
            "idioma": get_language(body),
            "engagement": score,
            "longitud_texto": text_length(body),
        }
        comments.append(rec)
        if len(comments) >= MAX_COMMENTS_PER_POST:
            break

    return comments


def scrape_old_reddit() -> list:
    """
    Scrapea r/MetalMexico y subreddits clave vía old.reddit.com (datos recientes).
    """
    records = []
    seen_urls = set()

    def add(rec):
        key = rec["url"] or rec["id"]
        if key not in seen_urls:
            seen_urls.add(key)
            records.append(rec)

    # Scrapear solo MetalMexico con paginación profunda (datos recientes)
    subreddits_old = ["MetalMexico"]

    for subreddit in subreddits_old:
        print(f"\n[MetalTDFScraper] {_timestamp()} — old.reddit: r/{subreddit}...")
        after = None
        page = 0
        post_records = []

        with tqdm(desc=f"Páginas r/{subreddit}", unit="pág") as pbar:
            while page < 10:  # máximo 10 páginas = ~250 posts
                page_posts, after = _fetch_old_reddit_page(subreddit, after)
                for rec in page_posts:
                    if rec["url"] not in seen_urls:
                        seen_urls.add(rec["url"])
                        post_records.append(rec)
                        records.append(rec)
                pbar.update(1)
                pbar.set_postfix({"posts": len(post_records)})
                if not after:
                    break
                page += 1
                time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        print(f"[MetalTDFScraper] {_timestamp()} — Posts r/{subreddit}: {len(post_records)}")

        # Comentarios de los primeros 30 posts
        print(f"[MetalTDFScraper] {_timestamp()} — Extrayendo comentarios de r/{subreddit}...")
        for rec in tqdm(post_records[:30], desc=f"Comentarios r/{subreddit}"):
            permalink = rec["url"].replace("https://www.reddit.com", "")
            if not permalink.startswith("/r/"):
                continue
            comments = _fetch_old_reddit_comments(permalink)
            for c in comments:
                add(c)
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    print(f"\n[MetalTDFScraper] {_timestamp()} — old.reddit total: {len(records)} registros")
    return records


# ─────────────────────────────────────────────
# PUNTO DE ENTRADA PRINCIPAL
# ─────────────────────────────────────────────

def scrape_reddit() -> list:
    """
    Combina Arctic Shift (histórico) + old.reddit.com (reciente).
    Guarda resultados en data/raw/reddit_raw.csv y reddit_raw.json.
    """
    print(f"\n[MetalTDFScraper] {_timestamp()} — Iniciando scraper Reddit (Arctic Shift + old.reddit.com)")

    # Fuente 1: Arctic Shift
    arctic_records = scrape_arctic_shift()

    # Fuente 2: old.reddit.com
    old_records = scrape_old_reddit()

    # Combinar y deduplicar por URL
    all_records = []
    seen_urls = set()
    for rec in arctic_records + old_records:
        key = rec["url"] or rec["id"]
        if key not in seen_urls:
            seen_urls.add(key)
            all_records.append(rec)

    # Guardar
    csv_path = f"{RAW_DATA_PATH}/reddit_raw.csv"
    json_path = f"{RAW_DATA_PATH}/reddit_raw.json"
    save_csv(all_records, csv_path)
    save_json(all_records, json_path)

    print(f"\n[MetalTDFScraper] {_timestamp()} — Reddit total: {len(all_records)} registros")
    print(f"  Arctic Shift: {len(arctic_records)} | old.reddit: {len(old_records)}")
    print(f"  Guardado en: {csv_path}")
    return all_records


if __name__ == "__main__":
    scrape_reddit()
