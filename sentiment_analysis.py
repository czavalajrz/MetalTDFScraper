"""
MetalTDFScraper — Análisis de Sentimientos
==========================================

Estrategia:
- Español (es, ca, pt, etc.) → pysentimiento RoBERTa entrenado en tweets en español
- Inglés (en) → VADER (léxico especializado en texto informal/social media)
- Otros / unknown → intento con pysentimiento, fallback a VADER

Salida:
  data/processed/metaltdf_sentiment.csv   — dataset completo con columnas de sentimiento
  data/processed/metaltdf_sentiment.json  — misma data en JSON
  data/processed/sentiment_report.txt     — reporte de resultados

Nota sobre vocabulario metal:
  Palabras como "brutal", "crushing", "killer", "devastating" tienen
  connotación POSITIVA en el contexto del metal. Se aplica una lista
  de corrección de dominio antes del análisis.
"""

import os
import re
import time
from datetime import datetime

import pandas as pd
from tqdm import tqdm

# ── Configuración de rutas ────────────────────────────────────────
PROCESSED_PATH = "data/processed"
INPUT_CSV = f"{PROCESSED_PATH}/metaltdf_dataset.csv"
OUTPUT_CSV = f"{PROCESSED_PATH}/metaltdf_sentiment.csv"
OUTPUT_JSON = f"{PROCESSED_PATH}/metaltdf_sentiment.json"
REPORT_TXT = f"{PROCESSED_PATH}/sentiment_report.txt"

# ── Vocabulario de dominio metal ──────────────────────────────────
# Palabras que en metal son POSITIVAS pero los modelos generales clasifican como negativas
METAL_POSITIVE_ES = [
    "brutal", "brutalidad", "brutal", "aplastante", "devastador", "demoledor",
    "agresivo", "pesado", "crudo", "oscuro", "oscuridad", "satánico",
    "infernal", "mortal", "asesino", "matar", "muerte", "guerra",
    "destrucción", "caos", "violento", "sangre", "infierno",
    "headbang", "headbanging", "mosh", "moshing", "pit", "riff", "riffs",
]
METAL_POSITIVE_EN = [
    "brutal", "crushing", "devastating", "killer", "deadly", "evil", "dark",
    "darkness", "death", "satan", "satanic", "infernal", "hellish", "bloody",
    "violent", "aggressive", "heavy", "raw", "chaos", "war", "destroy",
    "headbang", "mosh", "pit", "riff", "riffs", "shred", "shredding",
]

# ── Patrones de sentimiento específicos del metal ─────────────────
METAL_POSITIVE_PATTERNS_ES = [
    r'\bbanda\s+(increíble|excelente|brutal|épica|chingona|buenísima)',
    r'\b(gran|gran|excelente|increíble|épico)\s+(concierto|show|presentación|álbum)',
    r'\b(mucho|gran|enorme)\s+(talento|técnica|calidad)',
    r'\b(mejor|mejores)\s+(banda|bandas|show|concierto)',
    r'\b(recomiendo|recomendado|imperdible|obligatorio)',
]
METAL_POSITIVE_PATTERNS_EN = [
    r'\b(great|amazing|awesome|incredible|epic|killer)\s+(band|show|album|concert|gig)',
    r'\b(highly|strongly)\s+recommend',
    r'\b(best|top)\s+(band|album|show)',
]


def _timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _contains_metal_positive(text: str, lang: str) -> bool:
    """Detecta si el texto contiene contexto positivo de metal."""
    text_lower = text.lower()
    words = METAL_POSITIVE_EN if lang == "en" else METAL_POSITIVE_ES
    patterns = METAL_POSITIVE_PATTERNS_EN if lang == "en" else METAL_POSITIVE_PATTERNS_ES
    word_count = sum(1 for w in words if w in text_lower)
    pattern_match = any(re.search(p, text_lower) for p in patterns)
    return word_count >= 2 or pattern_match


def _load_models():
    """Carga los modelos de análisis de sentimientos."""
    print(f"[MetalTDFScraper] {_timestamp()} — Cargando modelos de sentimiento...")

    from pysentimiento import create_analyzer
    analyzer_es = create_analyzer(task="sentiment", lang="es")
    print(f"[MetalTDFScraper] ✓ pysentimiento (español) cargado")

    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    analyzer_en = SentimentIntensityAnalyzer()
    print(f"[MetalTDFScraper] ✓ VADER (inglés) cargado")

    return analyzer_es, analyzer_en


def _analyze_es(text: str, analyzer_es) -> dict:
    """Analiza sentimiento en español con pysentimiento."""
    try:
        # pysentimiento acepta máx ~512 tokens — truncar texto largo
        truncated = text[:1000]
        result = analyzer_es.predict(truncated)
        return {
            "sentimiento": result.output,          # POS / NEG / NEU
            "score_pos": round(result.probas.get("POS", 0), 4),
            "score_neg": round(result.probas.get("NEG", 0), 4),
            "score_neu": round(result.probas.get("NEU", 0), 4),
            "confianza": round(max(result.probas.values()), 4),
            "modelo": "pysentimiento-es",
        }
    except Exception as e:
        return _fallback_result(f"error_es: {e}")


def _analyze_en(text: str, analyzer_en) -> dict:
    """Analiza sentimiento en inglés con VADER."""
    try:
        scores = analyzer_en.polarity_scores(text[:1000])
        compound = scores["compound"]
        if compound >= 0.05:
            sentimiento = "POS"
        elif compound <= -0.05:
            sentimiento = "NEG"
        else:
            sentimiento = "NEU"
        return {
            "sentimiento": sentimiento,
            "score_pos": round(scores["pos"], 4),
            "score_neg": round(scores["neg"], 4),
            "score_neu": round(scores["neu"], 4),
            "confianza": round(abs(compound), 4),
            "modelo": "vader-en",
        }
    except Exception as e:
        return _fallback_result(f"error_en: {e}")


def _fallback_result(note: str = "") -> dict:
    return {
        "sentimiento": "NEU",
        "score_pos": 0.0,
        "score_neg": 0.0,
        "score_neu": 1.0,
        "confianza": 0.0,
        "modelo": f"fallback{':' + note if note else ''}",
    }


def _apply_metal_correction(result: dict, text: str, lang: str) -> dict:
    """
    Corrección de dominio: si el texto tiene contexto positivo de metal
    y el modelo lo clasificó como NEG, ajustar a NEU o POS según confianza.
    """
    if result["sentimiento"] == "NEG" and _contains_metal_positive(text, lang):
        if result["confianza"] < 0.70:
            result["sentimiento"] = "NEU"
            result["modelo"] += "+metal_correction"
    return result


def analyze_dataset():
    """Punto de entrada principal: analiza el dataset completo."""
    # Cargar dataset
    if not os.path.exists(INPUT_CSV):
        print(f"[MetalTDFScraper] No se encontró {INPUT_CSV}")
        print("  Corre primero: python main.py --all")
        return

    print(f"[MetalTDFScraper] {_timestamp()} — Cargando dataset...")
    df = pd.read_csv(INPUT_CSV)
    print(f"[MetalTDFScraper] {len(df)} registros cargados")

    # Cargar modelos
    analyzer_es, analyzer_en = _load_models()

    # Columnas de resultado
    resultados = []
    errores = 0

    print(f"\n[MetalTDFScraper] {_timestamp()} — Analizando sentimientos...")
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Análisis de sentimiento"):
        texto = str(row.get("texto", "") or "").strip()
        idioma = str(row.get("idioma", "unknown") or "unknown")

        if not texto or len(texto) < 10:
            resultados.append(_fallback_result("texto_vacio"))
            continue

        try:
            # Elegir modelo según idioma
            if idioma in ("es", "ca", "pt", "gl"):
                result = _analyze_es(texto, analyzer_es)
            elif idioma == "en":
                result = _analyze_en(texto, analyzer_en)
            else:
                # Para idioma desconocido: intentar español primero
                result = _analyze_es(texto, analyzer_es)
                if result["confianza"] < 0.50:
                    result_en = _analyze_en(texto, analyzer_en)
                    if result_en["confianza"] > result["confianza"]:
                        result = result_en

            # Corrección de dominio metal
            lang_for_correction = "en" if idioma == "en" else "es"
            result = _apply_metal_correction(result, texto, lang_for_correction)
            resultados.append(result)

        except Exception as e:
            errores += 1
            resultados.append(_fallback_result(str(e)[:50]))

    # Agregar columnas al DataFrame
    df_result = df.copy()
    df_result["sentimiento"] = [r["sentimiento"] for r in resultados]
    df_result["score_pos"] = [r["score_pos"] for r in resultados]
    df_result["score_neg"] = [r["score_neg"] for r in resultados]
    df_result["score_neu"] = [r["score_neu"] for r in resultados]
    df_result["confianza"] = [r["confianza"] for r in resultados]
    df_result["modelo_sentimiento"] = [r["modelo"] for r in resultados]

    # Guardar resultados
    os.makedirs(PROCESSED_PATH, exist_ok=True)
    df_result.to_csv(OUTPUT_CSV, index=False)
    df_result.to_json(OUTPUT_JSON, orient="records", force_ascii=False, indent=2)
    print(f"\n[MetalTDFScraper] Guardado: {OUTPUT_CSV}")

    # ── Reporte ──────────────────────────────────────────────────
    reporte = _generar_reporte(df_result, errores)
    with open(REPORT_TXT, "w", encoding="utf-8") as f:
        f.write(reporte)
    print(reporte)
    print(f"[MetalTDFScraper] Reporte guardado: {REPORT_TXT}")


def _generar_reporte(df: pd.DataFrame, errores: int) -> str:
    sep = "=" * 60
    lines = [
        sep,
        "MetalTDFScraper — REPORTE DE ANÁLISIS DE SENTIMIENTOS",
        sep,
        f"Fecha: {_timestamp()}",
        f"Total registros analizados: {len(df)}",
        f"Errores durante análisis: {errores}",
        "",
    ]

    # Distribución global
    lines.append("── Distribución global de sentimiento ──")
    dist = df["sentimiento"].value_counts()
    for sent, count in dist.items():
        pct = count / len(df) * 100
        lines.append(f"  {sent}: {count} ({pct:.1f}%)")

    # Por fuente
    lines.append("\n── Sentimiento por fuente ──")
    for fuente in df["fuente"].unique():
        sub = df[df["fuente"] == fuente]
        d = sub["sentimiento"].value_counts()
        lines.append(f"  {fuente} ({len(sub)} registros):")
        for s, c in d.items():
            lines.append(f"    {s}: {c} ({c/len(sub)*100:.1f}%)")

    # Por subgénero (solo los que tienen registros)
    lines.append("\n── Sentimiento por subgénero ──")
    subgeneros = df[df["subgenero"] != ""]["subgenero"].unique()
    for sg in sorted(subgeneros):
        sub = df[df["subgenero"] == sg]
        d = sub["sentimiento"].value_counts()
        pos = d.get("POS", 0)
        neg = d.get("NEG", 0)
        neu = d.get("NEU", 0)
        lines.append(f"  {sg} ({len(sub)})  POS={pos} NEG={neg} NEU={neu}")

    # Por idioma
    lines.append("\n── Sentimiento por idioma ──")
    for lang in ["es", "en"]:
        sub = df[df["idioma"] == lang]
        if len(sub) == 0:
            continue
        d = sub["sentimiento"].value_counts()
        lines.append(f"  {lang} ({len(sub)} registros):")
        for s, c in d.items():
            lines.append(f"    {s}: {c} ({c/len(sub)*100:.1f}%)")

    # Top 5 textos más positivos
    lines.append("\n── Top 5 textos más positivos (score_pos) ──")
    top_pos = df.nlargest(5, "score_pos")[["fuente", "tipo_texto", "score_pos", "texto"]]
    for _, r in top_pos.iterrows():
        lines.append(f"  [{r['fuente']}|{r['tipo_texto']}] score={r['score_pos']:.3f}")
        lines.append(f"  {str(r['texto'])[:120]}...")

    # Top 5 textos más negativos
    lines.append("\n── Top 5 textos más negativos (score_neg) ──")
    top_neg = df.nlargest(5, "score_neg")[["fuente", "tipo_texto", "score_neg", "texto"]]
    for _, r in top_neg.iterrows():
        lines.append(f"  [{r['fuente']}|{r['tipo_texto']}] score={r['score_neg']:.3f}")
        lines.append(f"  {str(r['texto'])[:120]}...")

    # Confianza promedio por modelo
    lines.append("\n── Confianza promedio por modelo ──")
    for modelo in df["modelo_sentimiento"].unique():
        sub = df[df["modelo_sentimiento"] == modelo]
        lines.append(f"  {modelo}: {sub['confianza'].mean():.3f} (n={len(sub)})")

    lines.append(f"\n{sep}")
    return "\n".join(lines)


if __name__ == "__main__":
    analyze_dataset()
