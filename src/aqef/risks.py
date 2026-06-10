"""Product risk register: machine-readable risks driving regression selection.

Risk-based testing made mechanical: each risk carries likelihood x impact
(1-5 each), the code areas it lives in (globs), and the test selectors that
protect it. Selection is then a ranking problem — risks touched by the change
first, then by residual risk tier — instead of a rerun-everything default.

Tier bands (5x5 matrix convention):
  critical >= 15 | high >= 10 | medium >= 5 | low < 5
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable, Sequence

import yaml

TIERS = ("low", "medium", "high", "critical")


class RiskRegisterError(ValueError):
    """Raised when a risk register file is structurally invalid."""


def tier_for_score(score: int) -> str:
    if score >= 15:
        return "critical"
    if score >= 10:
        return "high"
    if score >= 5:
        return "medium"
    return "low"


@dataclass(frozen=True)
class Risk:
    id: str
    title: str
    description: str
    areas: tuple[str, ...]
    likelihood: int
    impact: int
    tests: tuple[str, ...]
    owner: str
    review_by: str

    @property
    def score(self) -> int:
        return self.likelihood * self.impact

    @property
    def tier(self) -> str:
        return tier_for_score(self.score)

    def matches_changed(self, changed_files: Iterable[str]) -> bool:
        """True when any changed file falls inside one of this risk's areas.
        fnmatch semantics: '*' crosses directory separators."""
        for raw in changed_files:
            normalized = str(raw).replace("\\", "/")
            for pattern in self.areas:
                if fnmatch(normalized, pattern.replace("\\", "/")):
                    return True
        return False


@dataclass(frozen=True)
class RiskRegister:
    product: str
    risks: tuple[Risk, ...]

    def untested(self, min_tier: str = "high") -> list[Risk]:
        """Risks at or above min_tier with no linked tests — coverage debt."""
        floor = TIERS.index(min_tier)
        return [
            r for r in self.risks if not r.tests and TIERS.index(r.tier) >= floor
        ]


def load_register(path: str | Path) -> RiskRegister:
    raw = Path(path).read_text(encoding="utf-8-sig")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise RiskRegisterError(f"{path}: top level must be a mapping")
    risks_raw = data.get("risks")
    if not isinstance(risks_raw, list) or not risks_raw:
        raise RiskRegisterError(f"{path}: must define a non-empty 'risks' list")

    risks = []
    seen_ids: set[str] = set()
    for i, entry in enumerate(risks_raw):
        where = f"risk #{i + 1}"
        if not isinstance(entry, dict):
            raise RiskRegisterError(f"{where}: must be a mapping")
        risk_id = entry.get("id")
        if not risk_id or not isinstance(risk_id, str):
            raise RiskRegisterError(f"{where}: 'id' is required")
        if risk_id in seen_ids:
            raise RiskRegisterError(f"{where}: duplicate id {risk_id!r}")
        seen_ids.add(risk_id)
        if not entry.get("title"):
            raise RiskRegisterError(f"risk {risk_id!r}: 'title' is required")
        likelihood = entry.get("likelihood")
        impact = entry.get("impact")
        for name, value in (("likelihood", likelihood), ("impact", impact)):
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
                raise RiskRegisterError(
                    f"risk {risk_id!r}: {name} must be an integer 1-5, got {value!r}"
                )
        risks.append(
            Risk(
                id=risk_id,
                title=str(entry["title"]),
                description=str(entry.get("description", "")),
                areas=tuple(str(a) for a in entry.get("areas", [])),
                likelihood=likelihood,
                impact=impact,
                tests=tuple(str(t) for t in entry.get("tests", [])),
                owner=str(entry.get("owner", "")),
                review_by=str(entry.get("review_by", "")),
            )
        )

    return RiskRegister(product=str(data.get("product", "unnamed")), risks=tuple(risks))


@dataclass(frozen=True)
class SelectionItem:
    selector: str
    risk_id: str
    tier: str
    score: int
    impacted: bool
    reason: str


def select_tests(
    register: RiskRegister,
    changed_files: Sequence[str] | None = None,
    min_tier: str = "medium",
    limit: int | None = None,
) -> list[SelectionItem]:
    """Risk-ranked regression selection.

    Ordering: risks impacted by the change first (score descending), then
    unimpacted risks at or above min_tier (score descending). An impacted risk
    is always selected regardless of tier — a change in low-risk code is still
    a change. Duplicate selectors keep their highest-priority occurrence.
    """
    if min_tier not in TIERS:
        raise ValueError(f"min_tier must be one of {TIERS}, got {min_tier!r}")
    floor = TIERS.index(min_tier)
    changed = list(changed_files or [])

    ranked: list[tuple[Risk, bool]] = []
    for risk in register.risks:
        impacted = bool(changed) and risk.matches_changed(changed)
        if impacted or TIERS.index(risk.tier) >= floor:
            ranked.append((risk, impacted))
    ranked.sort(key=lambda pair: (not pair[1], -pair[0].score))

    items: list[SelectionItem] = []
    seen_selectors: set[str] = set()
    for risk, impacted in ranked:
        reason = (
            f"{risk.id} ({risk.tier}, score {risk.score})"
            + (" — area touched by change" if impacted else "")
        )
        for selector in risk.tests:
            if selector in seen_selectors:
                continue
            seen_selectors.add(selector)
            items.append(
                SelectionItem(
                    selector=selector,
                    risk_id=risk.id,
                    tier=risk.tier,
                    score=risk.score,
                    impacted=impacted,
                    reason=reason,
                )
            )
    if limit is not None:
        items = items[:limit]
    return items


def selection_to_dict(items: list[SelectionItem]) -> dict:
    return {
        "selectors": [i.selector for i in items],
        "selection": [
            {
                "selector": i.selector,
                "risk_id": i.risk_id,
                "tier": i.tier,
                "score": i.score,
                "impacted": i.impacted,
                "reason": i.reason,
            }
            for i in items
        ],
    }
