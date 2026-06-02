"""
MetalTDFScraper — Visualizaciones del Análisis de Sentimientos
==============================================================

Genera 8 gráficas y las guarda en data/processed/graficas/

Uso:
    python visualizations.py
"""

import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # sin GUI — guarda directo a archivo
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from datetime import datetime

# ── Rutas ──────────────────────────────────────────────────────────
INPUT_CSV  = "data/processed/metaltdf_sentiment.csv"
OUTPUT_DIR = "data/processed/graficas"

# ── Paleta de colores del metal ────────────────────────────────────
COLOR_POS = "#2ecc71"   # verde
COLOR_NEU = "#95a5a6"   # gris
COLOR_NEG = "#e74c3c"   # rojo
COLOR_BG  = "#1a1a2e"   # azul oscuro (fondo)
COLOR_TEXT = "#ecf0f1"  # blanco hueso
ACCENT    = "#e94560"   # rojo metal
PALETTE_SENT = {"POS": COLOR_POS, "NEU": COLOR_NEU, "NEG": COLOR_NEG}

# Estilo global oscuro metal
plt.rcParams.update({
    "figure.facecolor": COLOR_BG,
    "axes.facecolor": "#16213e",
    "axes.edgecolor": "#0f3460",
    "axes.labelcolor": COLOR_TEXT,
    "xtick.color": COLOR_TEXT,
    "ytick.color": COLOR_TEXT,
    "text.color": COLOR_TEXT,
    "grid.color": "#0f3460",
    "grid.linestyle": "--",
    "grid.alpha": 0.5,
    "font.family": "DejaVu Sans",
    "axes.titlesize": 14,
    "axes.labelsize": 11,
})

SENT_ORDER = ["POS", "NEU", "NEG"]


def _save(fig, nombre: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = f"{OUTPUT_DIR}/{nombre}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=COLOR_BG)
    plt.close(fig)
    print(f"  ✓ {path}")


def grafica_1_distribucion_global(df):
    """Gráfica de dona — distribución global de sentimiento."""
    counts = df["sentimiento"].value_counts().reindex(SENT_ORDER).fillna(0)
    fig, ax = plt.subplots(figsize=(7, 7))
    wedges, texts, autotexts = ax.pie(
        counts,
        labels=SENT_ORDER,
        colors=[COLOR_POS, COLOR_NEU, COLOR_NEG],
        autopct="%1.1f%%",
        startangle=90,
        wedgeprops={"width": 0.55, "edgecolor": COLOR_BG, "linewidth": 2},
        textprops={"color": COLOR_TEXT, "fontsize": 13},
    )
    for at in autotexts:
        at.set_fontsize(12)
        at.set_color(COLOR_BG)
        at.set_fontweight("bold")
    ax.set_title("Distribución Global de Sentimiento\nMetalTDFScraper — 1,633 registros",
                 fontsize=15, fontweight="bold", pad=20)
    # Texto central
    ax.text(0, 0, f"{len(df)}\nregistros", ha="center", va="center",
            fontsize=12, color=COLOR_TEXT, fontweight="bold")
    _save(fig, "1_distribucion_global")


def grafica_2_por_fuente(df):
    """Barras apiladas 100% — sentimiento por fuente."""
    orden_fuentes = ["headbanging", "reddit_arctic", "reddit_old", "musicbrainz"]
    nombres = {
        "headbanging": "Headbanging.com.mx",
        "reddit_arctic": "Reddit (Arctic Shift)",
        "reddit_old": "Reddit (old.reddit)",
        "musicbrainz": "MusicBrainz",
    }
    pivot = (df.groupby(["fuente", "sentimiento"])
               .size().unstack(fill_value=0)
               .reindex(orden_fuentes)
               .reindex(columns=SENT_ORDER, fill_value=0))
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100

    fig, ax = plt.subplots(figsize=(10, 6))
    bottom = pd.Series([0.0] * len(pivot_pct), index=pivot_pct.index)
    for sent, color in zip(SENT_ORDER, [COLOR_POS, COLOR_NEU, COLOR_NEG]):
        vals = pivot_pct[sent]
        bars = ax.barh([nombres.get(f, f) for f in pivot_pct.index],
                       vals, left=bottom, color=color, label=sent, height=0.6)
        # Etiquetas dentro de la barra si hay espacio
        for bar, val in zip(bars, vals):
            if val > 8:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_y() + bar.get_height() / 2,
                        f"{val:.0f}%", ha="center", va="center",
                        fontsize=10, color=COLOR_BG, fontweight="bold")
        bottom += vals

    ax.set_xlim(0, 100)
    ax.set_xlabel("Porcentaje (%)")
    ax.set_title("Sentimiento por Fuente de Datos", fontweight="bold", pad=15)
    ax.legend(loc="lower right", framealpha=0.2, labelcolor=COLOR_TEXT)
    ax.grid(axis="x")
    _save(fig, "2_sentimiento_por_fuente")


def grafica_3_por_subgenero(df):
    """Barras agrupadas — sentimiento por subgénero."""
    sub = df[df["subgenero"].notna() & (df["subgenero"] != "")]
    pivot = (sub.groupby(["subgenero", "sentimiento"])
                .size().unstack(fill_value=0)
                .reindex(columns=SENT_ORDER, fill_value=0))
    pivot = pivot.sort_values("NEG", ascending=False)

    x = range(len(pivot))
    width = 0.28
    fig, ax = plt.subplots(figsize=(12, 6))
    for i, (sent, color) in enumerate(zip(SENT_ORDER, [COLOR_POS, COLOR_NEU, COLOR_NEG])):
        offset = (i - 1) * width
        bars = ax.bar([xi + offset for xi in x], pivot[sent],
                      width=width, color=color, label=sent, alpha=0.9)
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.5,
                        str(int(h)), ha="center", va="bottom", fontsize=8)

    ax.set_xticks(list(x))
    ax.set_xticklabels([s.title() for s in pivot.index], rotation=30, ha="right")
    ax.set_ylabel("Número de registros")
    ax.set_title("Sentimiento por Subgénero de Metal", fontweight="bold", pad=15)
    ax.legend(framealpha=0.2)
    ax.grid(axis="y")
    _save(fig, "3_sentimiento_por_subgenero")


def grafica_4_por_idioma(df):
    """Barras apiladas — sentimiento por idioma (es vs en)."""
    sub = df[df["idioma"].isin(["es", "en"])]
    pivot = (sub.groupby(["idioma", "sentimiento"])
                .size().unstack(fill_value=0)
                .reindex(columns=SENT_ORDER, fill_value=0))
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100
    nombres_idioma = {"es": "Español (944)", "en": "Inglés (521)"}

    fig, ax = plt.subplots(figsize=(7, 5))
    bottom = pd.Series([0.0] * len(pivot_pct), index=pivot_pct.index)
    for sent, color in zip(SENT_ORDER, [COLOR_POS, COLOR_NEU, COLOR_NEG]):
        vals = pivot_pct[sent]
        bars = ax.bar([nombres_idioma.get(i, i) for i in pivot_pct.index],
                      vals, bottom=bottom, color=color, label=sent, width=0.5)
        for bar, val in zip(bars, vals):
            if val > 6:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_y() + bar.get_height() / 2,
                        f"{val:.0f}%", ha="center", va="center",
                        fontsize=11, color=COLOR_BG, fontweight="bold")
        bottom += vals

    ax.set_ylim(0, 100)
    ax.set_ylabel("Porcentaje (%)")
    ax.set_title("Sentimiento por Idioma", fontweight="bold", pad=15)
    ax.legend(framealpha=0.2)
    ax.grid(axis="y")
    _save(fig, "4_sentimiento_por_idioma")


def grafica_5_distribucion_scores(df):
    """Histogramas superpuestos de score_pos y score_neg."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Distribución de Scores de Confianza", fontsize=15, fontweight="bold")

    for ax, col, color, label in [
        (axes[0], "score_pos", COLOR_POS, "Score Positivo"),
        (axes[1], "score_neg", COLOR_NEG, "Score Negativo"),
    ]:
        for idioma, ls in [("es", "-"), ("en", "--")]:
            data = df[df["idioma"] == idioma][col].dropna()
            ax.hist(data, bins=30, alpha=0.6, color=color,
                    linestyle=ls, edgecolor=COLOR_BG, label=f"{idioma.upper()} (n={len(data)})",
                    density=True)
        ax.set_xlabel(label)
        ax.set_ylabel("Densidad")
        ax.legend(framealpha=0.2)
        ax.grid(axis="y")

    _save(fig, "5_distribucion_scores")


def grafica_6_tipo_texto(df):
    """Heatmap — sentimiento (%) por tipo de texto."""
    pivot = (df.groupby(["tipo_texto", "sentimiento"])
               .size().unstack(fill_value=0)
               .reindex(columns=SENT_ORDER, fill_value=0))
    pivot_pct = (pivot.div(pivot.sum(axis=1), axis=0) * 100).round(1)

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.heatmap(
        pivot_pct,
        annot=True, fmt=".1f", cmap="RdYlGn",
        linewidths=0.5, linecolor=COLOR_BG,
        ax=ax, cbar_kws={"label": "%"},
        annot_kws={"size": 11, "color": "black"},
    )
    ax.set_title("Sentimiento (%) por Tipo de Texto", fontweight="bold", pad=15)
    ax.set_xlabel("Sentimiento")
    ax.set_ylabel("Tipo de texto")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=0)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0)
    _save(fig, "6_heatmap_tipo_texto")


def grafica_7_top_positivos_negativos(df):
    """Barras horizontales — top subgéneros más positivos y más negativos."""
    sub = df[df["subgenero"].notna() & (df["subgenero"] != "")]
    pivot = (sub.groupby(["subgenero", "sentimiento"])
                .size().unstack(fill_value=0)
                .reindex(columns=SENT_ORDER, fill_value=0))
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Subgéneros más Positivos vs más Negativos", fontsize=14, fontweight="bold")

    # Más positivos
    top_pos = pivot_pct["POS"].sort_values(ascending=True)
    ax1.barh(top_pos.index, top_pos.values, color=COLOR_POS, alpha=0.85)
    for i, v in enumerate(top_pos.values):
        ax1.text(v + 0.5, i, f"{v:.1f}%", va="center", fontsize=9)
    ax1.set_title("% Positivo por subgénero", color=COLOR_POS)
    ax1.set_xlabel("% POS")
    ax1.grid(axis="x")

    # Más negativos
    top_neg = pivot_pct["NEG"].sort_values(ascending=True)
    ax2.barh(top_neg.index, top_neg.values, color=COLOR_NEG, alpha=0.85)
    for i, v in enumerate(top_neg.values):
        ax2.text(v + 0.5, i, f"{v:.1f}%", va="center", fontsize=9)
    ax2.set_title("% Negativo por subgénero", color=COLOR_NEG)
    ax2.set_xlabel("% NEG")
    ax2.grid(axis="x")

    _save(fig, "7_top_subgeneros_pos_neg")


def grafica_8_confianza_por_modelo(df):
    """Boxplot — distribución de confianza por modelo."""
    # Simplificar nombre del modelo
    df2 = df.copy()
    df2["modelo_simple"] = df2["modelo_sentimiento"].str.replace(r"\+metal_correction", "", regex=True)
    modelos = df2["modelo_simple"].value_counts().index.tolist()

    fig, ax = plt.subplots(figsize=(8, 5))
    data_plot = [df2[df2["modelo_simple"] == m]["confianza"].dropna().values for m in modelos]
    nombres_modelo = {
        "pysentimiento-es": "pysentimiento\n(Español)",
        "vader-en": "VADER\n(Inglés)",
        "fallback": "Fallback",
    }
    bp = ax.boxplot(data_plot,
                    patch_artist=True,
                    medianprops={"color": ACCENT, "linewidth": 2},
                    whiskerprops={"color": COLOR_TEXT},
                    capprops={"color": COLOR_TEXT},
                    flierprops={"markerfacecolor": COLOR_NEG, "alpha": 0.4})
    colors = [COLOR_POS, "#3498db", COLOR_NEU]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax.set_xticklabels([nombres_modelo.get(m, m) for m in modelos])
    ax.set_ylabel("Score de Confianza")
    ax.set_title("Distribución de Confianza por Modelo", fontweight="bold", pad=15)
    ax.grid(axis="y")

    # Anotación con n
    for i, (m, d) in enumerate(zip(modelos, data_plot), 1):
        ax.text(i, -0.05, f"n={len(d)}", ha="center", va="top",
                transform=ax.get_xaxis_transform(), fontsize=9, color=COLOR_TEXT)

    _save(fig, "8_confianza_por_modelo")


def main():
    print(f"\n[MetalTDFScraper] Generando visualizaciones...")

    if not os.path.exists(INPUT_CSV):
        print(f"No se encontró {INPUT_CSV}")
        print("Corre primero: python sentiment_analysis.py")
        return

    df = pd.read_csv(INPUT_CSV)
    print(f"  Dataset: {len(df)} registros\n")

    grafica_1_distribucion_global(df)
    grafica_2_por_fuente(df)
    grafica_3_por_subgenero(df)
    grafica_4_por_idioma(df)
    grafica_5_distribucion_scores(df)
    grafica_6_tipo_texto(df)
    grafica_7_top_positivos_negativos(df)
    grafica_8_confianza_por_modelo(df)

    print(f"\n[MetalTDFScraper] ✅ 8 gráficas guardadas en {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
