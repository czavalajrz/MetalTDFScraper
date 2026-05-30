# MetalTDFScraper — Configuración central

PROJECT_NAME = "MetalTDFScraper"

# --- Keywords ---
KEYWORDS_ES = [
    "metal", "metalero", "metalera", "headbanger", "thrash", "death metal",
    "black metal", "doom metal", "heavy metal", "power metal",
    "concierto metal", "festival metal", "banda de metal",
    "Hell and Heaven", "Mexico Metal Fest", "Imperio Azteca Metal Fest",
    "Headbanging", "El Chopo", "escena metal", 'metal mexicano', 'metal en mexico', 'metal en cdmx', 
    'metal mexico', 'headbanger mexico', 'heavy metal mexicano', 'thrash metal mexicano', 'death metal mexicano', 
    'black metal mexicano', 'promotores metal mexico', 'conciertos metal mexico', 'festivales metal mexico'
]

KEYWORDS_EN = [
    "mexican metal", "mexico metal", "cdmx metal",
    "metal mexico", "mexico headbanger", "mexican heavy metal", 'mexican thrash metal', 
    'mexican death metal', 'mexican black metal','hell and heaven metal fest', 'mexico metal fest', 
    'imperio azteca metal fest', 'headbanging mexico', 'el chopo metal', 'mexico metal scene'
]

ALL_KEYWORDS = KEYWORDS_ES + KEYWORDS_EN

# --- Reddit (JSON público, sin API key) ---
SUBREDDITS = [
    "MetalMexico",
    "mexico",
    "Metal",
    "folkmetal",
    'deathmetal',
    'thrashmetal',
    'heavymetal',
    'doommetal',
    'blackmetal',
    'metalcore',
    'power metal',
    'metalmemes',
    "numetal",
    "MetalForTheMasses"
]
MAX_POSTS_PER_SUBREDDIT = 100
MAX_COMMENTS_PER_POST = 30
REDDIT_BASE_URL = "https://www.reddit.com/r/{subreddit}.json"
REDDIT_SEARCH_URL = "https://www.reddit.com/r/{subreddit}/search.json"
USER_AGENT = "MetalTDFScraper/1.0 (investigacion academica metal mexico)"

# --- Headbanging.com.mx ---
HEADBANGING_BASE_URL = "https://headbanging.com.mx"
HEADBANGING_SECTIONS = [
    "https://headbanging.com.mx/category/noticias/",
    "https://headbanging.com.mx/category/resenas/",
    "https://headbanging.com.mx/category/cronicas/"
]
MAX_PAGES_HEADBANGING = 10

# --- Bandcamp ---
BANDCAMP_TAGS = [
    "mexican-metal",
    "black-metal-mexicano",
    "death-metal-mexicano",
    "thrash-metal-mexicano",
    "mexico"
]
BANDCAMP_BASE_URL = "https://bandcamp.com/discover/{tag}"

# --- Delays éticos (segundos) ---
DELAY_MIN = 2
DELAY_MAX = 5

# --- Texto mínimo válido ---
MIN_TEXT_LENGTH = 30

# --- Rutas de salida ---
RAW_DATA_PATH = "data/raw"
PROCESSED_DATA_PATH = "data/processed"
