import re


def remove_pii(text: str) -> str:
    """Remove names, phone numbers, and addresses. Returns cleaned text."""
    text = re.sub(r"\b\d{10}\b", "[PHONE]", text)
    text = re.sub(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", "[NAME]", text)
    # Address-like: number + street name + st/ave/rd/blvd/way/drive etc.
    text = re.sub(
        r"\b\d+\s+[A-Za-z0-9\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Way|Drive|Dr|Lane|Ln|Court|Ct)\b",
        "[ADDRESS]",
        text,
        flags=re.IGNORECASE,
    )
    # US zip: 12345 or 12345-6789
    text = re.sub(r"\b\d{5}(?:-\d{4})?\b", "[ZIP]", text)
    return text
