from deep_translator import GoogleTranslator


def translate_text(text: str, source: str = "en", target: str = "ru") -> str:
    if not text.strip():
        return ""
    # GoogleTranslator has request length limits; translate chunks conservatively.
    translator = GoogleTranslator(source=source, target=target)
    chunks = []
    current = ""
    for line in text.splitlines():
        if len(current) + len(line) + 1 > 3500 and current:
            chunks.append(current)
            current = ""
        current += (line + "\n")
    if current.strip():
        chunks.append(current)
    translated = []
    for chunk in chunks:
        try:
            translated.append(translator.translate(chunk) or chunk)
        except Exception:
            translated.append("[Перевод временно недоступен; ниже исходный текст]\n" + chunk)
    return "\n".join(translated)
