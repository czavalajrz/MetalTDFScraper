"""
Scraper para las páginas de descubrimiento de Bandcamp por tag.
Extrae lanzamientos de metal mexicano con artista, álbum, descripción y tags.
"""

import uuid
import time
import random
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from tqdm import tqdm

from config import (
    BANDCAMP_TAGS, BANDCAMP_BASE_URL,
    USER_AGENT, DELAY_MIN, DELAY_MAX, MIN_TEXT_LENGTH, RAW_DATA_PATH
)
from utils.cleaner import clean_text, get_language, text_length
from utils.exporter import save_csv, save_json

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}

SUBGENRE_KEYWORDS = {
    "death metal": ["death metal", "brutal death", "melodic death", "death-metal"],
    "black metal": ["black metal", "blackened", "black-metal"],
    "thrash metal": ["thrash metal", "thrash", "thrash-metal"],
    "doom metal": ["doom metal", "funeral doom", "doom-metal"],
    "power metal": ["power metal", "power-metal"],
    "folk metal": ["folk metal", "folk-metal"],
    "nu metal": ["nu metal", "nu-metal"],
    "metalcore": ["metalcore", "deathcore"],
    "heavy metal": ["heavy metal", "heavy-metal"],
}


def _timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_get(url, params=None):
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if resp.status_code in (429, 503):
            print(f"[MetalTDFScraper] {_timestamp()} — Rate limit en Bandcamp, esperando 15s...")
            time.sleep(15)
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        return resp
    except requests.exceptions.RequestException as e:
        print(f"[MetalTDFScraper] {_timestamp()} — Error al obtener {url}: {e}")
        return None


def _detect_subgenre(tags: list) -> str:
    tags_str = " ".join(t.lower() for t in tags)
    for genre, terms in SUBGENRE_KEYWORDS.items():
        for term in terms:
            if term in tags_str:
                return genre
    return ""


def _parse_discover_page(tag: str) -> list:
    """
    Parsea la página de discover de Bandcamp para un tag dado.
    Bandcamp usa JSON embebido en la página para los resultados iniciales.
    """
    url = BANDCAMP_BASE_URL.format(tag=tag)
    resp = _safe_get(url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    records = []

    # Bandcamp incrusta datos en data-blob o en elementos .discover-item
    items = soup.select(".discover-item, .item-details, .result-item")

    if not items:
        # Fallback: buscar elementos genéricos de álbum/artista
        items = soup.select("li[data-band-id], li.item")

    for item in items:
        try:
            # Artista
            artist_el = item.select_one(".artist-name, .itemsubtext, .by-artist")
            artista = clean_text(artist_el.get_text()) if artist_el else ""

            # Álbum / track
            album_el = item.select_one(".item-title, .itemtext, .album-title")
            album = clean_text(album_el.get_text()) if album_el else ""

            # URL del release
            link_el = item.select_one("a[href]")
            item_url = link_el["href"] if link_el else url

            # Tags del item
            tag_els = item.select(".tag")
            item_tags = [t.get_text(strip=True).lower() for t in tag_els]
            if tag not in item_tags:
                item_tags.append(tag)

            # Descripción / texto
            desc_el = item.select_one(".description, .tralbum-about")
            descripcion = clean_text(desc_el.get_text()) if desc_el else ""

            # Si no hay descripción, usar artista + álbum como texto mínimo
            texto = descripcion if descripcion else clean_text(f"{artista} {album} {' '.join(item_tags)}")

            rec = {
                "id": str(uuid.uuid4()),
                "fuente": "bandcamp",
                "url": item_url,
                "fecha": "",
                "tipo_texto": "descripcion",
                "autor": artista,
                "titulo": album,
                "texto": texto,
                "banda": artista,
                "subgenero": _detect_subgenre(item_tags),
                "ciudad": "",
                "evento": "",
                "idioma": get_language(texto),
                "engagement": "",
                "longitud_texto": text_length(texto),
            }
            if rec["longitud_texto"] >= MIN_TEXT_LENGTH:
                records.append(rec)
        except Exception as e:
            print(f"[MetalTDFScraper] {_timestamp()} — Error parseando item de Bandcamp: {e}")
            continue

    # Si no se encontraron items con selectores, intentar scraping de URLs de álbumes
    if not records:
        records = _parse_discover_links(soup, url, tag)

    return records


def _parse_discover_links(soup: BeautifulSoup, base_url: str, tag: str) -> list:
    """Fallback: sigue los links de álbumes encontrados en la página de discover."""
    records = []
    album_links = set()

    for a in soup.select("a[href*='bandcamp.com']"):
        href = a.get("href", "")
        if "/album/" in href or "/track/" in href:
            album_links.add(href.split("?")[0])

    for album_url in list(album_links)[:20]:
        resp = _safe_get(album_url)
        if not resp:
            continue
        album_soup = BeautifulSoup(resp.text, "lxml")

        artista_el = album_soup.select_one("#band-name-location .title, p#band-name")
        artista = clean_text(artista_el.get_text()) if artista_el else ""

        album_el = album_soup.select_one("h2.trackTitle, h2#name-section")
        album = clean_text(album_el.get_text()) if album_el else ""

        desc_el = album_soup.select_one(".tralbum-about")
        descripcion = clean_text(desc_el.get_text()) if desc_el else ""

        tag_els = album_soup.select("a.tag")
        item_tags = [t.get_text(strip=True).lower() for t in tag_els]

        texto = descripcion if descripcion else clean_text(f"{artista} {album} {' '.join(item_tags)}")

        rec = {
            "id": str(uuid.uuid4()),
            "fuente": "bandcamp",
            "url": album_url,
            "fecha": "",
            "tipo_texto": "descripcion",
            "autor": artista,
            "titulo": album,
            "texto": texto,
            "banda": artista,
            "subgenero": _detect_subgenre(item_tags if item_tags else [tag]),
            "ciudad": "",
            "evento": "",
            "idioma": get_language(texto),
            "engagement": "",
            "longitud_texto": text_length(texto),
        }
        if rec["longitud_texto"] >= MIN_TEXT_LENGTH:
            records.append(rec)
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    return records


def scrape_bandcamp() -> list:
    """Punto de entrada principal: retorna lista de registros de Bandcamp."""
    all_records = []
    seen_urls = set()

    for tag in tqdm(BANDCAMP_TAGS, desc="Tags Bandcamp"):
        print(f"\n[MetalTDFScraper] {_timestamp()} — Scrapeando Bandcamp tag: {tag}")
        records = _parse_discover_page(tag)
        for rec in records:
            if rec["url"] not in seen_urls:
                seen_urls.add(rec["url"])
                all_records.append(rec)
        print(f"[MetalTDFScraper] {_timestamp()} — Tag '{tag}': {len(records)} registros")
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    csv_path = f"{RAW_DATA_PATH}/bandcamp_raw.csv"
    json_path = f"{RAW_DATA_PATH}/bandcamp_raw.json"
    save_csv(all_records, csv_path)
    save_json(all_records, json_path)
    print(f"\n[MetalTDFScraper] {_timestamp()} — Bandcamp: {len(all_records)} registros guardados en {csv_path}")
    return all_records


if __name__ == "__main__":
    scrape_bandcamp()
