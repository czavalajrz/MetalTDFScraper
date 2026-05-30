import hashlib

def text_hash(text: str) -> str:
    text = (text or "").strip().lower()
    return hashlib.sha1(text.encode("utf-8")).hexdigest()

def deduplicate_records(records):
    seen_urls = set()
    seen_hashes = set()
    unique_records = []

    for record in records:
        url = (record.get("url") or "").strip()
        text = (record.get("texto") or "").strip()
        current_hash = text_hash(text)

        if url and url in seen_urls:
            continue

        if text and current_hash in seen_hashes:
            continue

        if url:
            seen_urls.add(url)

        if text:
            seen_hashes.add(current_hash)

        unique_records.append(record)

    return unique_records
