"""
Scraper para MusicBrainz — reemplaza Bandcamp que migró a React y bloqueó acceso sin JS.

MusicBrainz es una base de datos abierta de música con API gratuita sin registro.
Extrae artistas de metal mexicano, sus álbumes y tags/subgéneros.

API docs: https://musicbrainz.org/doc/MusicBrainz_API
Rate limit: 1 request/segundo (respetado con delays).
"""

import uuid
import time
import random
import requests
from datetime import datetime
from typing import Optional
from tqdm import tqdm

from config import (
    DELAY_MIN, DELAY_MAX, MIN_TEXT_LENGTH, RAW_DATA_PATH
)
from utils.cleaner import clean_text, get_language, text_length
from utils.exporter import save_csv, save_json

# MusicBrainz requiere User-Agent descriptivo con contacto
MB_USER_AGENT = "MetalTDFScraper/1.0 (investigacion academica metal mexico; https://github.com/czavalajrz/MetalTDFScraper)"
MB_API = "https://musicbrainz.org/ws/2"
HEADERS = {"User-Agent": MB_USER_AGENT, "Accept": "application/json"}

SUBGENRE_KEYWORDS = {
    "death metal": ["death metal", "brutal death", "melodic death", "death-metal"],
    "black metal": ["black metal", "blackened", "black-metal"],
    "thrash metal": ["thrash metal", "thrash", "thrash-metal"],
    "doom metal": ["doom metal", "funeral doom", "doom-metal"],
    "power metal": ["power metal", "power-metal"],
    "folk metal": ["folk metal", "folk-metal"],
    "nu metal": ["nu metal", "nu-metal"],
    "metalcore": ["metalcore", "deathcore"],
    "heavy metal": ["heavy metal", "heavy-metal", "nwobhm"],
}

# Consultas para encontrar artistas de metal en México
ARTIST_QUERIES = [
    'tag:metal AND country:MX',
    'tag:death-metal AND country:MX',
    'tag:black-metal AND country:MX',
    'tag:thrash-metal AND country:MX',
    'tag:heavy-metal AND country:MX',
    'tag:doom-metal AND country:MX',
    'tag:power-metal AND country:MX',
]


def _timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_get(url, params=None, retries=3):
    """GET con reintentos. MusicBrainz pide máx 1 req/seg."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                print(f"[MetalTDFScraper] {_timestamp()} — Rate limit MusicBrainz, esperando {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code == 503:
                print(f"[MetalTDFScraper] {_timestamp()} — 503 MusicBrainz, esperando 10s...")
                time.sleep(10)
                continue
            resp.raise_for_status()
            return resp
        except requests.exceptions.Timeout:
            print(f"[MetalTDFScraper] {_timestamp()} — Timeout ({attempt+1}/{retries}): {url}")
            time.sleep(5)
        except requests.exceptions.RequestException as e:
            print(f"[MetalTDFScraper] {_timestamp()} — Error: {e}")
            time.sleep(5)
    return None


def _detect_subgenre(tags: list) -> str:
    tags_str = " ".join(t.lower() for t in tags)
    for genre, terms in SUBGENRE_KEYWORDS.items():
        for term in terms:
            if term in tags_str:
                return genre
    return ""


def _fetch_artists(query: str, limit: int = 100) -> list:
    """Obtiene lista de artistas de metal mexicano desde MusicBrainz."""
    artists = []
    offset = 0
    while offset < limit:
        params = {
            "query": query,
            "fmt": "json",
            "limit": min(100, limit - offset),
            "offset": offset,
        }
        resp = _safe_get(f"{MB_API}/artist", params=params)
        if not resp:
            break
        try:
            data = resp.json()
        except ValueError:
            break

        page_artists = data.get("artists", [])
        if not page_artists:
            break
        artists.extend(page_artists)
        offset += len(page_artists)

        total = data.get("count", 0)
        if offset >= total:
            break
        # MusicBrainz: máximo 1 request por segundo
        time.sleep(1.2)

    return artists


def _fetch_artist_releases(artist_id: str, limit: int = 10) -> list:
    """Obtiene los releases (álbumes) de un artista."""
    params = {
        "artist": artist_id,
        "type": "album",
        "fmt": "json",
        "limit": limit,
        "inc": "tags+genres",
    }
    resp = _safe_get(f"{MB_API}/release-group", params=params)
    if not resp:
        return []
    try:
        return resp.json().get("release-groups", [])
    except ValueError:
        return []


def _artist_to_record(artist: dict) -> Optional[dict]:
    """Convierte un artista de MusicBrainz al esquema estándar."""
    name = artist.get("name", "")
    disambiguation = artist.get("disambiguation", "")
    country = artist.get("country", "")

    # Obtener tags del artista
    tags = [t.get("name", "") for t in artist.get("tags", [])]
    tags_str = " ".join(tags)

    # Área (ciudad/estado)
    area = artist.get("area", {}) or {}
    city = area.get("name", "")

    # Texto descriptivo combinado
    texto = clean_text(f"{name} {disambiguation} {tags_str}")
    if text_length(texto) < MIN_TEXT_LENGTH:
        # Enriquecer con info del life-span
        life = artist.get("life-span", {}) or {}
        inicio = life.get("begin", "")
        texto = clean_text(f"{name} banda de metal de {country or 'México'}. Tags: {tags_str}. Activa desde {inicio}.")

    # Fecha de inicio
    life_span = artist.get("life-span", {}) or {}
    fecha = life_span.get("begin", "")

    mb_url = f"https://musicbrainz.org/artist/{artist.get('id', '')}"

    return {
        "id": str(uuid.uuid4()),
        "fuente": "musicbrainz",
        "url": mb_url,
        "fecha": fecha,
        "tipo_texto": "bio",
        "autor": "",
        "titulo": name,
        "texto": texto,
        "banda": name,
        "subgenero": _detect_subgenre(tags),
        "ciudad": city,
        "evento": "",
        "idioma": get_language(texto),
        "engagement": str(artist.get("score", 0)),
        "longitud_texto": text_length(texto),
    }


def _release_to_record(release: dict, artist_name: str) -> Optional[dict]:
    """Convierte un release de MusicBrainz al esquema estándar."""
    title = release.get("title", "")
    tags = [t.get("name", "") for t in release.get("tags", [])]
    genres = [g.get("name", "") for g in release.get("genres", [])]
    all_tags = tags + genres
    tags_str = " ".join(all_tags)

    texto = clean_text(f"{artist_name} - {title}. {tags_str}")
    if text_length(texto) < MIN_TEXT_LENGTH:
        texto = clean_text(f"Álbum: {title} de {artist_name}. Tags: {tags_str}")

    # Fecha del primer release
    fecha = release.get("first-release-date", "")

    mb_url = f"https://musicbrainz.org/release-group/{release.get('id', '')}"

    return {
        "id": str(uuid.uuid4()),
        "fuente": "musicbrainz",
        "url": mb_url,
        "fecha": fecha,
        "tipo_texto": "descripcion",
        "autor": artist_name,
        "titulo": title,
        "texto": texto,
        "banda": artist_name,
        "subgenero": _detect_subgenre(all_tags),
        "ciudad": "",
        "evento": "",
        "idioma": get_language(texto),
        "engagement": "",
        "longitud_texto": text_length(texto),
    }


def scrape_bandcamp() -> list:
    """
    Punto de entrada principal.
    Scrapea artistas y álbumes de metal mexicano desde MusicBrainz.
    (Bandcamp migró a React en 2024-2025 y bloqueó acceso sin JS)
    """
    print(f"\n[MetalTDFScraper] {_timestamp()} — MusicBrainz: buscando artistas de metal en México...")

    all_records = []
    seen_ids = set()
    seen_artist_ids = set()

    def add(rec):
        key = rec["url"]
        if key not in seen_ids:
            seen_ids.add(key)
            all_records.append(rec)

    # Recolectar artistas de todas las queries
    all_artists = []
    for query in tqdm(ARTIST_QUERIES, desc="Queries MusicBrainz"):
        artists = _fetch_artists(query, limit=100)
        for a in artists:
            if a.get("id") not in seen_artist_ids:
                seen_artist_ids.add(a.get("id"))
                all_artists.append(a)
        print(f"[MetalTDFScraper] '{query}': {len(artists)} artistas")
        time.sleep(1.2)

    print(f"\n[MetalTDFScraper] {_timestamp()} — Total artistas únicos: {len(all_artists)}")

    # Convertir artistas a registros + obtener sus álbumes
    for artist in tqdm(all_artists, desc="Artistas → registros"):
        # Registro del artista
        rec = _artist_to_record(artist)
        if rec and rec["longitud_texto"] >= MIN_TEXT_LENGTH:
            add(rec)

        # Álbumes del artista (máx 5 por artista para no saturar)
        releases = _fetch_artist_releases(artist["id"], limit=5)
        for rel in releases:
            rel_rec = _release_to_record(rel, artist.get("name", ""))
            if rel_rec and rel_rec["longitud_texto"] >= MIN_TEXT_LENGTH:
                add(rel_rec)

        # Respetar rate limit de MusicBrainz (1 req/seg)
        time.sleep(1.2)

    # Guardar
    csv_path = f"{RAW_DATA_PATH}/bandcamp_raw.csv"
    json_path = f"{RAW_DATA_PATH}/bandcamp_raw.json"
    save_csv(all_records, csv_path)
    save_json(all_records, json_path)

    print(f"\n[MetalTDFScraper] {_timestamp()} — MusicBrainz: {len(all_records)} registros guardados en {csv_path}")
    return all_records


if __name__ == "__main__":
    scrape_bandcamp()
