"""
MetalTDFScraper — Orquestador principal.

Uso:
  python main.py --all          # Corre todos los scrapers
  python main.py --reddit       # Solo Reddit
  python main.py --headbanging  # Solo Headbanging
  python main.py --bandcamp     # Solo Bandcamp
  python main.py --merge        # Solo merge y limpieza final
"""

import argparse
import glob
import os
from datetime import datetime

import pandas as pd

from config import MIN_TEXT_LENGTH, RAW_DATA_PATH, PROCESSED_DATA_PATH, PROJECT_NAME
from utils.deduplicator import deduplicate_records
from utils.exporter import save_csv, save_json, ensure_dir
from utils.cleaner import is_binary_text


def _timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _print_summary(df: pd.DataFrame):
    """Imprime resumen del dataset combinado."""
    print(f"\n{'='*60}")
    print(f"[MetalTDFScraper] RESUMEN FINAL DEL DATASET")
    print(f"{'='*60}")
    print(f"Total de registros: {len(df)}")

    print("\n--- Por fuente ---")
    if "fuente" in df.columns:
        print(df["fuente"].value_counts().to_string())

    print("\n--- Por idioma ---")
    if "idioma" in df.columns:
        print(df["idioma"].value_counts().to_string())

    print("\n--- Por subgénero ---")
    if "subgenero" in df.columns:
        sg = df["subgenero"].replace("", "sin_clasificar").value_counts()
        print(sg.to_string())

    print("\n--- Por tipo de texto ---")
    if "tipo_texto" in df.columns:
        print(df["tipo_texto"].value_counts().to_string())
    print(f"{'='*60}\n")


def merge_and_clean():
    """Combina todos los CSVs raw, deduplica y guarda el dataset procesado."""
    print(f"\n[MetalTDFScraper] {_timestamp()} — Iniciando merge y limpieza...")

    csv_files = glob.glob(f"{RAW_DATA_PATH}/*.csv")
    if not csv_files:
        print(f"[MetalTDFScraper] No se encontraron archivos CSV en {RAW_DATA_PATH}/")
        return []

    dfs = []
    for f in csv_files:
        try:
            df_tmp = pd.read_csv(f)
            dfs.append(df_tmp)
            print(f"[MetalTDFScraper] Cargado: {f} ({len(df_tmp)} registros)")
        except Exception as e:
            print(f"[MetalTDFScraper] Error al leer {f}: {e}")

    if not dfs:
        print("[MetalTDFScraper] No se pudieron cargar datos.")
        return []

    df = pd.concat(dfs, ignore_index=True)
    print(f"[MetalTDFScraper] Total antes de limpieza: {len(df)} registros")

    # Deduplicar
    records = df.to_dict("records")
    records = deduplicate_records(records)

    # Filtrar por longitud mínima
    records = [r for r in records if int(r.get("longitud_texto", 0) or 0) >= MIN_TEXT_LENGTH]

    # Eliminar registros con texto binario (imágenes EXIF, datos corruptos)
    antes = len(records)
    records = [r for r in records if not is_binary_text(str(r.get("texto", "") or ""))]
    descartados_binarios = antes - len(records)
    if descartados_binarios:
        print(f"[MetalTDFScraper] Registros binarios descartados: {descartados_binarios}")

    # Corregir idiomas mal detectados en textos cortos (< 50 chars)
    for r in records:
        texto = str(r.get("texto", "") or "")
        if len(texto) < 50 and r.get("idioma") not in ("es", "en", "unknown"):
            r["idioma"] = "unknown"

    print(f"[MetalTDFScraper] Total después de limpieza: {len(records)} registros")

    # Guardar
    ensure_dir(PROCESSED_DATA_PATH)
    csv_out = f"{PROCESSED_DATA_PATH}/metaltdf_dataset.csv"
    json_out = f"{PROCESSED_DATA_PATH}/metaltdf_dataset.json"
    save_csv(records, csv_out)
    save_json(records, json_out)
    print(f"[MetalTDFScraper] Dataset guardado en {csv_out}")

    df_final = pd.DataFrame(records)
    _print_summary(df_final)
    return records


def main():
    parser = argparse.ArgumentParser(
        description=f"{PROJECT_NAME} — Scraper de metal mexicano para análisis de sentimientos"
    )
    parser.add_argument("--all", action="store_true", help="Correr todos los scrapers")
    parser.add_argument("--reddit", action="store_true", help="Solo scraper de Reddit")
    parser.add_argument("--headbanging", action="store_true", help="Solo scraper de Headbanging")
    parser.add_argument("--bandcamp", action="store_true", help="Solo scraper de Bandcamp")
    parser.add_argument("--merge", action="store_true", help="Solo merge y limpieza final")
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        return

    print(f"\n[MetalTDFScraper] {_timestamp()} — Iniciando {PROJECT_NAME}")
    ensure_dir(RAW_DATA_PATH)
    ensure_dir(PROCESSED_DATA_PATH)

    if args.reddit or args.all:
        from scrapers.reddit_scraper import scrape_reddit
        print(f"\n[MetalTDFScraper] {_timestamp()} — === REDDIT ===")
        scrape_reddit()

    if args.headbanging or args.all:
        from scrapers.headbanging_scraper import scrape_headbanging
        print(f"\n[MetalTDFScraper] {_timestamp()} — === HEADBANGING ===")
        scrape_headbanging()

    if args.bandcamp or args.all:
        from scrapers.bandcamp_scraper import scrape_bandcamp
        print(f"\n[MetalTDFScraper] {_timestamp()} — === BANDCAMP ===")
        scrape_bandcamp()

    if args.merge or args.all:
        merge_and_clean()
    elif args.reddit or args.headbanging or args.bandcamp:
        # Merge automático al terminar cualquier scraper
        merge_and_clean()

    print(f"[MetalTDFScraper] {_timestamp()} — Proceso completado.")


if __name__ == "__main__":
    main()
