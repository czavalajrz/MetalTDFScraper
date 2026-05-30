"""
Scraper para Reddit usando OAuth (flujo "script") con la API oficial.
No requiere PRAW — usa requests directamente con token Bearer.

Requisito: archivo .env con:
    REDDIT_CLIENT_ID=...
    REDDIT_CLIENT_SECRET=...
    REDDIT_USERNAME=...
    REDDIT_PASSWORD=...

Regístrate en: https://www.reddit.com/prefs/apps  (tipo: script)
"""

import uuid
import time
import random
import os
from typing import Optional
import requests
from datetime import datetime, timezone
from tqdm import tqdm
from dotenv import load_dotenv

from config import (
    SUBREDDITS, ALL_KEYWORDS, MAX_POSTS_PER_SUBREDDIT, MAX_COMMENTS_PER_POST,
    USER_AGENT, DELAY_MIN, DELAY_MAX, MIN_TEXT_LENGTH, RAW_DATA_PATH
)
from utils.cleaner import clean_text, get_language, text_length
from utils.exporter import save_csv, save_json

load_dotenv()

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

# Token OAuth en memoria (se renueva automáticamente)
_oauth_token = {"access_token": None, "expires_at": 0}


def _timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _get_oauth_token() -> Optional[str]:
    """Obtiene o renueva el token OAuth de Reddit."""
    now = time.time()
    if _oauth_token["access_token"] and now < _oauth_token["expires_at"] - 60:
        return _oauth_token["access_token"]

    client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
    username = os.getenv("REDDIT_USERNAME", "").strip()
    password = os.getenv("REDDIT_PASSWORD", "").strip()

    if not all([client_id, client_secret, username, password]):
        print("[MetalTDFScraper] ⚠️  Credenciales de Reddit no encontradas en .env")
        print("               Copia .env.example a .env y rellena tus credenciales.")
        print("               Registra tu app en: https://www.reddit.com/prefs/apps")
        return None

    try:
        resp = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(client_id, client_secret),
            data={"grant_type": "password", "username": username, "password": password},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if not token:
            print(f"[MetalTDFScraper] Error al obtener token: {data}")
            return None
        _oauth_token["access_token"] = token
        _oauth_token["expires_at"] = now + data.get("expires_in", 3600)
        print(f"[MetalTDFScraper] {_timestamp()} — Token OAuth obtenido OK")
        return token
    except requests.exceptions.RequestException as e:
        print(f"[MetalTDFScraper] Error al autenticar con Reddit: {e}")
        return None


def _get_headers() -> dict:
    token = _get_oauth_token()
    if token:
        return {"Authorization": f"bearer {token}", "User-Agent": USER_AGENT}
    return {"User-Agent": USER_AGENT}


def _api_base() -> str:
    """Base URL: oauth si tenemos token, reddit.com si no."""
    if _oauth_token.get("access_token"):
        return "https://oauth.reddit.com"
    return "https://www.reddit.com"


def _safe_get(url, params=None, retries=3):
    """GET con reintentos ante errores 429/503/timeout."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=_get_headers(), params=params, timeout=15)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 10))
                print(f"[MetalTDFScraper] {_timestamp()} — Rate limit 429, esperando {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code in (401, 403):
                # Token expirado o inválido — limpiar y reintentar
                _oauth_token["access_token"] = None
                _oauth_token["expires_at"] = 0
                if attempt < retries - 1:
                    print(f"[MetalTDFScraper] {_timestamp()} — {resp.status_code}, renovando token...")
                    time.sleep(2)
                    continue
                print(f"[MetalTDFScraper] {_timestamp()} — {resp.status_code} en {url}")
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


def _parse_post(post_data: dict) -> dict:
    title = post_data.get("title", "")
    selftext = post_data.get("selftext", "") or ""
    combined = f"{title} {selftext}"
    texto = clean_text(combined)

    fecha_ts = post_data.get("created_utc", 0)
    fecha = datetime.fromtimestamp(fecha_ts, tz=timezone.utc).isoformat() if fecha_ts else ""

    return {
        "id": str(uuid.uuid4()),
        "fuente": "reddit",
        "url": f"https://www.reddit.com{post_data.get('permalink', '')}",
        "fecha": fecha,
        "tipo_texto": "post",
        "autor": post_data.get("author", ""),
        "titulo": clean_text(title),
        "texto": texto,
        "banda": "",
        "subgenero": _detect_subgenre(combined),
        "ciudad": _detect_city(combined),
        "evento": _detect_event(combined),
        "idioma": get_language(texto),
        "engagement": str(post_data.get("score", 0)),
        "longitud_texto": text_length(texto),
    }


def _parse_comment(comment_data: dict, post_url: str) -> dict:
    body = comment_data.get("body", "") or ""
    texto = clean_text(body)

    fecha_ts = comment_data.get("created_utc", 0)
    fecha = datetime.fromtimestamp(fecha_ts, tz=timezone.utc).isoformat() if fecha_ts else ""

    return {
        "id": str(uuid.uuid4()),
        "fuente": "reddit",
        "url": post_url,
        "fecha": fecha,
        "tipo_texto": "comentario",
        "autor": comment_data.get("author", ""),
        "titulo": "",
        "texto": texto,
        "banda": "",
        "subgenero": _detect_subgenre(body),
        "ciudad": _detect_city(body),
        "evento": _detect_event(body),
        "idioma": get_language(texto),
        "engagement": str(comment_data.get("score", 0)),
        "longitud_texto": text_length(texto),
    }


def _fetch_comments(permalink: str) -> list:
    url = f"{_api_base()}{permalink}.json"
    resp = _safe_get(url, params={"limit": MAX_COMMENTS_PER_POST})
    if not resp:
        return []
    try:
        data = resp.json()
        comments_listing = data[1]["data"]["children"]
    except (IndexError, KeyError, ValueError):
        return []

    records = []
    post_url = f"https://www.reddit.com{permalink}"
    for child in comments_listing:
        if child.get("kind") != "t1":
            continue
        c = child.get("data", {})
        if not c.get("body") or c["body"] in ("[deleted]", "[removed]"):
            continue
        rec = _parse_comment(c, post_url)
        if rec["longitud_texto"] >= MIN_TEXT_LENGTH:
            records.append(rec)
        if len(records) >= MAX_COMMENTS_PER_POST:
            break
    return records


def _fetch_listing(subreddit: str, sort: str = "hot") -> list:
    """Extrae posts de un subreddit por tipo de ordenamiento."""
    records = []
    after = None
    fetched = 0
    url = f"{_api_base()}/r/{subreddit}/{sort}.json"

    while fetched < MAX_POSTS_PER_SUBREDDIT:
        params = {"limit": 100, "raw_json": 1}
        if after:
            params["after"] = after
        resp = _safe_get(url, params=params)
        if not resp:
            break
        try:
            data = resp.json()["data"]
        except (KeyError, ValueError):
            break
        children = data.get("children", [])
        if not children:
            break
        for child in children:
            if child.get("kind") != "t3":
                continue
            rec = _parse_post(child["data"])
            if rec["longitud_texto"] >= MIN_TEXT_LENGTH:
                records.append(rec)
            fetched += 1
        after = data.get("after")
        if not after:
            break
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    return records


def _search_subreddit(subreddit: str, keyword: str) -> list:
    """Busca posts en un subreddit por keyword."""
    url = f"{_api_base()}/r/{subreddit}/search.json"
    params = {
        "q": keyword,
        "restrict_sr": 1,
        "limit": 100,
        "sort": "relevance",
        "t": "all",
        "raw_json": 1,
    }
    resp = _safe_get(url, params=params)
    if not resp:
        return []
    try:
        children = resp.json()["data"]["children"]
    except (KeyError, ValueError):
        return []
    records = []
    for child in children:
        if child.get("kind") != "t3":
            continue
        rec = _parse_post(child["data"])
        if rec["longitud_texto"] >= MIN_TEXT_LENGTH:
            records.append(rec)
    return records


def scrape_reddit() -> list:
    """Punto de entrada principal: retorna lista de registros de Reddit."""

    # Verificar credenciales antes de empezar
    token = _get_oauth_token()
    if not token:
        print("[MetalTDFScraper] ❌ No se puede continuar sin credenciales OAuth.")
        print("\n📋 PASOS PARA CONFIGURAR:\n")
        print("  1. Ve a https://www.reddit.com/prefs/apps")
        print("  2. Crea una app tipo 'script'")
        print("  3. Copia .env.example a .env")
        print("  4. Rellena REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD")
        print("  5. Vuelve a correr: python main.py --reddit\n")
        return []

    all_records = []
    seen_ids = set()

    def add_unique(records):
        for r in records:
            key = r["url"] + r.get("texto", "")[:50]
            if key not in seen_ids:
                seen_ids.add(key)
                all_records.append(r)

    # r/MetalMexico: hot + new + top
    print(f"\n[MetalTDFScraper] {_timestamp()} — Scrapeando r/MetalMexico (hot/new/top)...")
    for sort in ["hot", "new", "top"]:
        posts = _fetch_listing("MetalMexico", sort)
        add_unique(posts)
        print(f"[MetalTDFScraper] MetalMexico/{sort}: {len(posts)} posts")
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    # Comentarios de posts de MetalMexico
    metal_posts = [r for r in all_records if r["tipo_texto"] == "post"]
    print(f"[MetalTDFScraper] {_timestamp()} — Extrayendo comentarios de {len(metal_posts)} posts de MetalMexico...")
    for rec in tqdm(metal_posts[:50], desc="Comentarios MetalMexico"):
        permalink = rec["url"].replace("https://www.reddit.com", "")
        comments = _fetch_comments(permalink)
        add_unique(comments)
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    # Demás subreddits: búsqueda por keywords
    other_subreddits = [s for s in SUBREDDITS if s != "MetalMexico"]
    search_keywords = ALL_KEYWORDS[:15]

    for subreddit in tqdm(other_subreddits, desc="Subreddits"):
        print(f"\n[MetalTDFScraper] {_timestamp()} — Buscando en r/{subreddit}...")
        for kw in tqdm(search_keywords, desc=f"  r/{subreddit}", leave=False):
            results = _search_subreddit(subreddit, kw)
            add_unique(results)
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    # Guardar
    csv_path = f"{RAW_DATA_PATH}/reddit_raw.csv"
    json_path = f"{RAW_DATA_PATH}/reddit_raw.json"
    save_csv(all_records, csv_path)
    save_json(all_records, json_path)
    print(f"\n[MetalTDFScraper] {_timestamp()} — Reddit: {len(all_records)} registros guardados en {csv_path}")
    return all_records


if __name__ == "__main__":
    scrape_reddit()
