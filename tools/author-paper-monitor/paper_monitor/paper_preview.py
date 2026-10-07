"""Short, source-derived previews. No model call or inferred result is required."""
import html
import re


def plain(value):
    return ' '.join(re.sub(r'<[^>]+>', ' ', html.unescape(value or '')).split())


def sentence(value, limit=220):
    text = plain(value)
    first = re.split(r'(?<=[.!?。！？])\s+', text, maxsplit=1)[0]
    if len(first) <= limit:
        return first
    return first[:limit-1].rsplit(' ', 1)[0].rstrip(',;:') + '…'


def preview(paper):
    if paper.summary:
        return 'summary', sentence(paper.summary)
    terms = [plain(k) for k in paper.keywords if plain(k) and len(plain(k)) <= 70]
    if not terms:
        # Extract phrases verbatim from the descriptive part of the title.
        # This cannot invent a scientific result, even when no abstract exists.
        title = plain(paper.title).split(':', 1)[-1]
        phrases = re.split(r'\b(?:from|using|via|with|for|and|through|by|towards?|of|in|to)\b|[;—–]', title, flags=re.I)
        terms = [p.strip(' .,-') for p in phrases if 5 <= len(p.strip()) <= 70
                 and len(p.split()) >= 2 and p.strip().casefold() != plain(paper.title).casefold()]
    terms = list(dict.fromkeys(terms))[:3]
    if terms:
        return 'keywords', ' · '.join(terms)[:220]
    if paper.abstract:
        return 'abstract', sentence(paper.abstract)
    return '', ''
