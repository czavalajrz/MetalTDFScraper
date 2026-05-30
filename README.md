# MetalTDFScraper

Sistema de scraping en Python para recolectar datos del género musical **metal en México**, orientado a análisis de sentimientos. Recolecta posts, comentarios, noticias, reseñas y descripciones de álbumes de múltiples fuentes.

## Fuentes de datos

- **Reddit** — Posts y comentarios de subreddits como r/MetalMexico, r/Metal, r/deathmetal, entre otros
- **Headbanging.com.mx** — Noticias, reseñas y crónicas del principal sitio de metal mexicano
- **Bandcamp** — Descripciones de lanzamientos con tags de metal mexicano

## Requisitos

- Python 3.9+
- macOS / Linux (probado en macOS)

## Instalación

```bash
# Clonar el repositorio
git clone <url-del-repo>
cd MetalTDFScraper

# Crear y activar entorno virtual
python3 -m venv venv
source venv/bin/activate  # macOS/Linux

# Instalar dependencias
pip install -r requirements.txt
```

## Uso

```bash
# Activar el entorno virtual antes de usar
source venv/bin/activate

# Correr todos los scrapers y generar dataset final
python main.py --all

# Solo Reddit
python main.py --reddit

# Solo Headbanging.com.mx
python main.py --headbanging

# Solo Bandcamp
python main.py --bandcamp

# Solo merge y limpieza (si ya tienes datos en data/raw/)
python main.py --merge
```

## Estructura del proyecto

```
MetalTDFScraper/
├── config.py                        # Configuración central (keywords, URLs, parámetros)
├── main.py                          # Orquestador principal
├── requirements.txt
├── scrapers/
│   ├── reddit_scraper.py            # Scraper de Reddit (JSON público)
│   ├── headbanging_scraper.py       # Scraper de headbanging.com.mx
│   └── bandcamp_scraper.py          # Scraper de Bandcamp
├── utils/
│   ├── cleaner.py                   # Limpieza de texto y detección de idioma
│   ├── deduplicator.py              # Deduplicación por URL y hash de texto
│   └── exporter.py                  # Exportación a CSV y JSON
└── data/
    ├── raw/                         # Datos crudos por fuente
    └── processed/                   # Dataset final combinado
```

## Columnas del dataset

| Columna | Descripción |
|---|---|
| `id` | UUID único del registro |
| `fuente` | Origen: `reddit`, `headbanging`, `bandcamp` |
| `url` | URL del contenido original |
| `fecha` | Fecha de publicación (ISO 8601) |
| `tipo_texto` | `post`, `comentario`, `noticia`, `resena`, `descripcion` |
| `autor` | Usuario o autor del contenido |
| `titulo` | Título del post o artículo (vacío si no aplica) |
| `texto` | Texto limpio del contenido |
| `banda` | Nombre de banda si se menciona explícitamente |
| `subgenero` | Subgénero detectado (death metal, black metal, thrash, etc.) |
| `ciudad` | Ciudad mexicana mencionada (CDMX, Guadalajara, Monterrey, etc.) |
| `evento` | Nombre de festival o concierto si aplica |
| `idioma` | Idioma detectado (`es`, `en`, `unknown`) |
| `engagement` | Score de Reddit o métrica equivalente |
| `longitud_texto` | Número de caracteres del texto |

## Archivos de salida

- `data/raw/reddit_raw.csv` / `.json` — Datos crudos de Reddit
- `data/raw/headbanging_raw.csv` / `.json` — Datos crudos de Headbanging
- `data/raw/bandcamp_raw.csv` / `.json` — Datos crudos de Bandcamp
- `data/processed/metaltdf_dataset.csv` / `.json` — Dataset final limpio y deduplicado

## Ética del scraping

- **Delays aleatorios** entre requests (2–5 segundos por defecto) para no saturar los servidores
- **User-Agent identificado** como investigación académica
- **Sin credenciales** — Reddit se accede vía JSON público sin API key
- Se recomienda revisar los archivos `robots.txt` de cada sitio antes de usar en producción:
  - https://www.reddit.com/robots.txt
  - https://headbanging.com.mx/robots.txt
  - https://bandcamp.com/robots.txt
- Los datos recolectados son de acceso público y se usan con fines de investigación académica
