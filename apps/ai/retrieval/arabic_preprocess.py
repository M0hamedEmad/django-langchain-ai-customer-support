import re

# Basic Arabic normalization utilities suitable for search & embeddings

diacritics = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
TATWEEL = "\u0640"

ALIF_VARIANTS = {
    "\u0622": "\u0627",  # ALEF WITH MADDA ABOVE -> ALEF
    "\u0623": "\u0627",  # ALEF WITH HAMZA ABOVE -> ALEF
    "\u0625": "\u0627",  # ALEF WITH HAMZA BELOW -> ALEF
}

TEH_MARBUTA = "\u0629"
HEH = "\u0647"


def normalize_arabic(text: str, remove_diacritics: bool = True) -> str:
    if not text:
        return ""
    x = text
    x = x.replace(TATWEEL, "")
    for src, dst in ALIF_VARIANTS.items():
        x = x.replace(src, dst)
    x = x.replace(TEH_MARBUTA, HEH)
    if remove_diacritics:
        x = diacritics.sub("", x)
    x = re.sub(r"\s+", " ", x).strip()
    return x


def clean_query(text: str) -> str:
    return normalize_arabic(text).lower()
