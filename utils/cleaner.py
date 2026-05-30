import re
from langdetect import detect, LangDetectException

def clean_text(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"http[s]?://\S+", " ", text)
    text = re.sub(r"www\.\S+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def get_language(text: str) -> str:
    if not text or len(text.strip()) < 10:
        return "unknown"
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"

def text_length(text: str) -> int:
    return len(text or "")
