import re
from langdetect import detect, LangDetectException

# Proporción máxima de caracteres no-ASCII permitida antes de descartar el texto
_MAX_NON_ASCII_RATIO = 0.30

# Patrón que detecta cabeceras EXIF / datos binarios embebidos como texto
_BINARY_PATTERN = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]|Exif|JFIF|Canon|Nikon|Adobe Lightroom', re.IGNORECASE)


def is_binary_text(text: str) -> bool:
    """Devuelve True si el texto parece datos binarios (imágenes, EXIF, etc.)."""
    if not text:
        return False
    # Detectar cabeceras de archivos binarios comunes
    if _BINARY_PATTERN.search(text[:200]):
        return True
    # Detectar alta proporción de caracteres no imprimibles
    non_printable = sum(1 for c in text[:500] if ord(c) < 32 and c not in '\t\n\r')
    if non_printable / max(len(text[:500]), 1) > 0.05:
        return True
    # Detectar alta proporción de caracteres no-ASCII (texto en alfabeto no latino)
    non_ascii = sum(1 for c in text if ord(c) > 127)
    if len(text) > 0 and non_ascii / len(text) > _MAX_NON_ASCII_RATIO:
        return True
    return False


def clean_text(text: str) -> str:
    if not text:
        return ""
    # Descartar texto binario antes de cualquier procesamiento
    if is_binary_text(text):
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"http[s]?://\S+", " ", text)
    text = re.sub(r"www\.\S+", " ", text)
    # Eliminar caracteres de control no deseados (excepto saltos de línea/tab)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_language(text: str) -> str:
    # Umbral mínimo más alto para evitar detecciones erróneas en textos cortos
    if not text or len(text.strip()) < 50:
        return "unknown"
    # Descartar texto binario
    if is_binary_text(text):
        return "unknown"
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def text_length(text: str) -> int:
    return len(text or "")
