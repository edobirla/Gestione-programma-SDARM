"""Text normalization for accent-insensitive search across all languages."""
import unicodedata


def normalize(s: str) -> str:
    """Lowercase and strip diacritics so 'à'→'a', 'ș'→'s', 'ñ'→'n', etc."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    out = "".join(c for c in nfkd if not unicodedata.combining(c))
    return out.lower().strip()
