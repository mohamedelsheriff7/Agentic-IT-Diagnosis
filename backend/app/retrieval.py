import re
import math
import unicodedata
from collections import Counter

STOP = set('the a an is my to of and in for not i have it this with me please'.split())
def tokens(text):
    text = unicodedata.normalize('NFKC', text).lower()
    text = re.sub('[\u064b-\u065f\u0640]', '', text)
    text = text.translate(str.maketrans('أإآى', 'اااي'))
    return [t for t in re.findall(r'\w+', text) if t not in STOP]

def rank(query, documents, limit):
    q = Counter(tokens(query))
    scored = []
    for identifier, text in documents:
        d = Counter(tokens(text))
        overlap = sum(q[t] * d[t] for t in q.keys() & d.keys())
        score = overlap / (math.sqrt(sum(v*v for v in q.values()) * sum(v*v for v in d.values())) or 1)
        if score >= 0.12:
            scored.append((identifier, round(score, 5)))
    return sorted(scored, key=lambda p: (-p[1], p[0]))[:limit]
