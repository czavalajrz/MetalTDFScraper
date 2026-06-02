"""
Scraper para headbanging.com.mx usando BeautifulSoup + lxml.
Extrae noticias, reseñas y crónicas del sitio de metal mexicano.
"""

import uuid
import time
import random
from typing import Optional
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from tqdm import tqdm

from config import (
    HEADBANGING_BASE_URL, HEADBANGING_SECTIONS, MAX_PAGES_HEADBANGING,
    USER_AGENT, DELAY_MIN, DELAY_MAX, MIN_TEXT_LENGTH, RAW_DATA_PATH
)
from utils.cleaner import clean_text, get_language, text_length
from utils.exporter import save_csv, save_json

HEADERS = {"User-Agent": USER_AGENT}

SUBGENRE_KEYWORDS = {
    "death metal": ["death metal", "brutal death", "melodic death"],
    "black metal": ["black metal", "blackened"],
    "thrash metal": ["thrash metal", "thrash"],
    "doom metal": ["doom metal", "funeral doom"],
    "power metal": ["power metal"],
    "folk metal": ["folk metal"],
    "nu metal": ["nu metal", "nu-metal"],
    "metalcore": ["metalcore", "deathcore"],
    "heavy metal": ["heavy metal"],
}

EVENT_KEYWORDS = [
    "hell and heaven", "mexico metal fest", "imperio azteca metal fest",
    "el chopo", "headbanging fest", "festival", "tour", "gira"
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


def _safe_get(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp
    except requests.exceptions.RequestException as e:
        print(f"[MetalTDFScraper] {_timestamp()} — Error al obtener {url}: {e}")
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


def _get_article_urls(section_url: str) -> list:
    """Obtiene las URLs de artículos de una sección paginada."""
    urls = []
    for page in range(1, MAX_PAGES_HEADBANGING + 1):
        page_url = section_url if page == 1 else f"{section_url}page/{page}/"
        resp = _safe_get(page_url)
        if not resp:
            break
        soup = BeautifulSoup(resp.text, "lxml")
        # Buscar enlaces de artículos — estructura típica de WordPress
        articles = soup.select("article a[href]")
        if not articles:
            articles = soup.select("h2 a[href], h3 a[href], .entry-title a[href]")
        page_urls = []
        for a in articles:
            href = a.get("href", "")
            if HEADBANGING_BASE_URL in href and href not in urls:
                page_urls.append(href)
        if not page_urls:
            break
        urls.extend(page_urls)
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    return list(dict.fromkeys(urls))  # eliminar duplicados manteniendo orden


def _parse_article(url: str, tipo_texto: str) -> Optional[dict]:
    """Extrae los datos de un artículo individual."""
    resp = _safe_get(url)
    if not resp:
        return None
    soup = BeautifulSoup(resp.text, "lxml")

    # Título
    title_tag = soup.find("h1", class_=lambda c: c and "title" in c) or soup.find("h1")
    titulo = clean_text(title_tag.get_text()) if title_tag else ""

    # Fecha
    fecha = ""
    date_tag = soup.find("time")
    if date_tag:
        fecha = date_tag.get("datetime", date_tag.get_text(strip=True))

    # Autor
    autor = ""
    author_tag = soup.find(class_=lambda c: c and "author" in c)
    if author_tag:
        autor = clean_text(author_tag.get_text())

    # Cuerpo del artículo
    content_tag = (
        soup.find("div", class_=lambda c: c and "entry-content" in c)
        or soup.find("div", class_=lambda c: c and "post-content" in c)
        or soup.find("article")
    )
    if content_tag:
        # Eliminar elementos no deseados
        for tag in content_tag.find_all(["script", "style", "aside", "nav"]):
            tag.decompose()
        raw_text = content_tag.get_text(separator=" ")
    else:
        raw_text = soup.get_text(separator=" ")

    texto = clean_text(raw_text)

    # Tags / categorías para detectar subgénero y banda
    tags = []
    for tag_el in soup.select(".tags a, .post-tags a, .entry-tags a, .cat-links a"):
        tags.append(tag_el.get_text(strip=True).lower())
    tags_str = " ".join(tags)

    combined = f"{titulo} {texto} {tags_str}"

    return {
        "id": str(uuid.uuid4()),
        "fuente": "headbanging",
        "url": url,
        "fecha": fecha,
        "tipo_texto": tipo_texto,
        "autor": autor,
        "titulo": titulo,
        "texto": texto,
        "banda": "",
        "subgenero": _detect_subgenre(combined),
        "ciudad": _detect_city(combined),
        "evento": _detect_event(combined),
        "idioma": get_language(texto),
        "engagement": "",
        "longitud_texto": text_length(texto),
    }


def _section_tipo(section_url: str) -> str:
    if "resena" in section_url or "reseña" in section_url:
        return "resena"
    if "cronica" in section_url or "crónica" in section_url:
        return "noticia"
    return "noticia"


def scrape_headbanging() -> list:
    """Punto de entrada principal: retorna lista de registros de headbanging.com.mx."""
    all_records = []
    seen_urls = set()

    for section_url in HEADBANGING_SECTIONS:
        tipo = _section_tipo(section_url)
        print(f"\n[MetalTDFScraper] {_timestamp()} — Sección: {section_url}")
        article_urls = _get_article_urls(section_url)
        print(f"[MetalTDFScraper] {_timestamp()} — URLs encontradas: {len(article_urls)}")

        for url in tqdm(article_urls, desc=f"Artículos ({tipo})"):
            if url in seen_urls:
                continue
            seen_urls.add(url)
            record = _parse_article(url, tipo)
            if record and record["longitud_texto"] >= MIN_TEXT_LENGTH:
                all_records.append(record)
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    csv_path = f"{RAW_DATA_PATH}/headbanging_raw.csv"
    json_path = f"{RAW_DATA_PATH}/headbanging_raw.json"
    save_csv(all_records, csv_path)
    save_json(all_records, json_path)
    print(f"\n[MetalTDFScraper] {_timestamp()} — Headbanging: {len(all_records)} registros guardados en {csv_path}")
    return all_records


if __name__ == "__main__":
    scrape_headbanging()
