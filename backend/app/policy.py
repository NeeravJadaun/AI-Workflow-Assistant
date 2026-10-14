import re
from dataclasses import dataclass
from functools import lru_cache

from . import config

FALLBACK_ID = "P-6"


@dataclass(frozen=True)
class Policy:
    id: str
    title: str
    urgency: str
    category: str
    keywords: tuple[str, ...]
    rule: str


@lru_cache(maxsize=4)
def _load(path: str) -> tuple[Policy, ...]:
    text = open(path, encoding="utf-8").read()
    policies = []
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        head, *lines = block.strip().splitlines()
        pid, _, title = head.partition(" ")
        fields = {}
        for line in lines:
            key, _, value = line.partition(":")
            fields[key.strip().lower()] = value.strip()
        policies.append(Policy(
            id=pid, title=title,
            urgency=fields["urgency"], category=fields["category"],
            keywords=tuple(k.strip().lower() for k in fields.get("keywords", "").split(",") if k.strip()),
            rule=fields["rule"],
        ))
    return tuple(policies)


def all_policies() -> tuple[Policy, ...]:
    return _load(str(config.policy_path()))


def lookup_policy(query: str, limit: int = 3) -> list[Policy]:
    """Return policies whose keywords appear in the query, best match first.

    Falls back to the general policy when nothing matches. Emergency policies win ties.
    """
    text = " " + re.sub(r"[^a-z0-9 ]", " ", query.lower()) + " "
    scored = []
    for i, p in enumerate(all_policies()):
        score = sum(1 for k in p.keywords if f" {k} " in text)
        if score:
            scored.append((-score, i, p))
    scored.sort(key=lambda t: (t[0], t[1]))
    result = [p for _, _, p in scored[:limit]]
    if not result:
        result = [p for p in all_policies() if p.id == FALLBACK_ID]
    return result
