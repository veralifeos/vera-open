"""Calibracao do scoring — valida regras contra vagas anotadas.

Portado de vera-private/vera/scoring/calibration.py. Usa JobScorer 14-dim +
check_blockers. Fixtures ficam em config/calibration_fixtures.yaml (gitignored).

Escala: scorer retorna 0.0-1.0, calibration trabalha em 0-10 (x10 para
casar com fixtures do private).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from vera.research.base import ResearchItem
from vera.research.packs.jobs.blockers import check_blockers
from vera.research.packs.jobs.profile import load_profile
from vera.research.packs.jobs.scorer import JobScorer
from vera.research.scoring import ScoringEngine

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_FIXTURES_PATH = _REPO_ROOT / "config" / "calibration_fixtures.yaml"

# Faixas esperadas por categoria (rule scorer em escala 0-10)
_EXPECTED_RANGES = {
    "high": (7.0, 10.0),
    "medium": (3.0, 6.9),
    "low": (0.0, 2.9),
    "blocked": None,  # deve ser bloqueado
}


def load_fixtures(path: Path | None = None) -> list[dict]:
    """Carrega fixtures de calibracao do YAML."""
    p = path or _FIXTURES_PATH
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("fixtures", [])


def _job_dict_to_item(job: dict) -> ResearchItem:
    """Converte um dict de fixture em ResearchItem."""
    return ResearchItem(
        id=job.get("id", "fixture"),
        title=job.get("title", ""),
        url=job.get("url", ""),
        source_name=job.get("source", "fixture"),
        published=datetime.now(timezone.utc),
        content=job.get("description", ""),
        metadata={
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "is_remote": job.get("is_remote", False),
            "salary_currency": job.get("salary_currency", ""),
            "contract_type": job.get("contract_type", ""),
            "easy_apply": job.get("easy_apply", False),
            "applicants": job.get("applicants"),
            "is_referral": job.get("is_referral", False),
        },
    )


def run_calibration(
    fixtures: list[dict] | None = None,
    path: Path | None = None,
    verbose: bool = False,
) -> dict:
    """Executa calibracao: pontua cada fixture e compara com expectativa."""
    if fixtures is None:
        fixtures = load_fixtures(path)

    profile = load_profile()
    scorer = JobScorer(ScoringEngine())
    results: list[dict] = []

    for fixture in fixtures:
        name = fixture.get("name", "?")
        expected = fixture.get("expected", "medium")
        manual_fit = fixture.get("manual_fit")
        stage = fixture.get("stage", "?")
        job = fixture.get("job", {})
        item = _job_dict_to_item(job)

        # Verificar bloqueio
        blocker = check_blockers(item, profile=profile)
        is_blocked = blocker is not None

        # Pontuar sempre (para diagnostico) — em escala 0-10
        rule_score = scorer.score_rules(item, {}) * 10.0

        # Avaliar acerto
        if expected == "blocked":
            passed = is_blocked
            reason = blocker["reason"] if is_blocked else "NAO foi bloqueado (deveria)"
        else:
            if is_blocked:
                passed = False
                reason = f"bloqueado indevidamente: {blocker['reason']}"
            else:
                low, high = _EXPECTED_RANGES[expected]
                passed = low <= rule_score <= high
                if passed:
                    reason = f"score {rule_score:.1f} dentro de [{low:.0f}, {high:.0f}]"
                else:
                    reason = f"score {rule_score:.1f} FORA de [{low:.0f}, {high:.0f}]"

        result = {
            "name": name,
            "stage": stage,
            "expected": expected,
            "manual_fit": manual_fit,
            "rule_score": rule_score,
            "is_blocked": is_blocked,
            "blocker_reason": blocker["reason"] if is_blocked else None,
            "passed": passed,
            "reason": reason,
        }
        results.append(result)

        if verbose:
            status = "OK" if passed else "FAIL"
            print(f"  [{status}] {name}")
            print(
                f"     stage={stage} | expected={expected} | score={rule_score:.1f} | blocked={is_blocked}"
            )
            if not passed:
                print(f"     -> {reason}")

    # Estatisticas
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    failed = [r for r in results if not r["passed"]]

    by_category: dict[str, dict] = {}
    for r in results:
        cat = r["expected"]
        if cat not in by_category:
            by_category[cat] = {"total": 0, "passed": 0}
        by_category[cat]["total"] += 1
        if r["passed"]:
            by_category[cat]["passed"] += 1

    # Correlacao manual_fit vs rule_score (nao-bloqueados com fit)
    pairs = [
        (r["manual_fit"], r["rule_score"])
        for r in results
        if r["manual_fit"] is not None and not r["is_blocked"]
    ]
    mae = _mean_absolute_error(pairs) if pairs else None

    return {
        "total": total,
        "passed": passed_count,
        "failed": len(failed),
        "accuracy": round(passed_count / total, 3) if total > 0 else 0,
        "mae_vs_manual": round(mae, 2) if mae is not None else None,
        "by_category": by_category,
        "results": results,
        "failures": failed,
    }


def _mean_absolute_error(pairs: list[tuple[float, float]]) -> float:
    if not pairs:
        return 0.0
    total = sum(abs(manual - auto) for manual, auto in pairs)
    return total / len(pairs)


def format_report(cal: dict) -> str:
    """Formata relatorio de calibracao para terminal."""
    lines: list[str] = []
    lines.append("=" * 65)
    lines.append("  VERA JOBS SCORING CALIBRATION")
    lines.append("=" * 65)
    lines.append("")
    lines.append(f"  Total fixtures:  {cal['total']}")
    lines.append(f"  Passed:          {cal['passed']}")
    lines.append(f"  Failed:          {cal['failed']}")
    lines.append(f"  Accuracy:        {cal['accuracy']:.1%}")
    if cal["mae_vs_manual"] is not None:
        lines.append(f"  MAE vs manual:   {cal['mae_vs_manual']:.2f} pts")
    lines.append("")

    lines.append("  By category:")
    for cat, stats in sorted(cal["by_category"].items()):
        t = stats["total"]
        p = stats["passed"]
        pct = p / t if t > 0 else 0
        mark = "OK" if p == t else "!!"
        lines.append(f"    [{mark}] {cat:<10s}  {p}/{t}  ({pct:.0%})")
    lines.append("")

    lines.append("  Details:")
    for r in cal["results"]:
        status = "OK  " if r["passed"] else "FAIL"
        score_str = f"{r['rule_score']:.1f}" if not r["is_blocked"] else "BLK "
        manual_str = f"fit={r['manual_fit']}" if r["manual_fit"] is not None else "fit=?"
        lines.append(f"    [{status}] [{score_str:>4s}] {r['name']}")
        lines.append(f"           stage={r['stage']} | {manual_str} | expected={r['expected']}")
        if not r["passed"]:
            lines.append(f"           -> {r['reason']}")
    lines.append("")

    if cal["failures"]:
        lines.append("  FAILURES:")
        for f in cal["failures"]:
            lines.append(f"    * {f['name']}: {f['reason']}")
        lines.append("")

    lines.append("=" * 65)
    return "\n".join(lines)
