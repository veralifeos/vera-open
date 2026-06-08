"""Testes da calibracao do jobs pack."""

from unittest.mock import patch

from vera.research.packs.jobs.calibration import (
    _job_dict_to_item,
    format_report,
    run_calibration,
)


_FIXTURE_PROFILE = {
    "target_roles": {
        "exact": ["CRO Manager"],
        "close": ["PMM"],
        "adjacent": ["RevOps"],
    },
    "stack": {"strong": ["GA4", "HubSpot"]},
    "sectors_preferred": ["fintech"],
    "scoring_weights": {
        "title_exact": 3.0,
        "title_close": 2.0,
        "title_adjacent": 1.0,
        "cro_keywords": 0.5,
        "b2b_saas": 1.5,
        "stack_match_2plus": 1.0,
        "remote": 1.0,
        "clt_or_usd": 0.5,
        "clt_explicit": 1.0,
        "brasil_location": 0.5,
        "portugues": 0.3,
        "beneficios": 0.3,
        "preferred_sector": 0.5,
        "easy_apply": 0.3,
        "small_pipeline": 0.2,
        "referral": 0.5,
        "target_company": 2.0,
    },
    "blockers": {"titles": ["data analyst"]},
}


def test_job_dict_to_item_preserves_metadata():
    item = _job_dict_to_item(
        {
            "id": "abc",
            "title": "CRO Manager",
            "description": "fintech B2B SaaS",
            "location": "remote",
            "is_remote": True,
            "company": "Foo",
        }
    )
    assert item.title == "CRO Manager"
    assert item.content == "fintech B2B SaaS"
    assert item.metadata["location"] == "remote"
    assert item.metadata["is_remote"] is True
    assert item.metadata["company"] == "Foo"


def test_run_calibration_high_fixture_passes():
    # exact 3.0 + b2b 1.5 + stack 1.0 + remote 1.0 + brasil 0.5 + sector 0.5 = 7.5
    fixtures = [
        {
            "name": "CRO ideal",
            "stage": "Processo",
            "manual_fit": 9,
            "expected": "high",
            "job": {
                "title": "CRO Manager",
                "description": "B2B SaaS fintech with GA4 and HubSpot",
                "location": "Remote - Brasil",
                "is_remote": True,
            },
        }
    ]
    with patch(
        "vera.research.packs.jobs.calibration.load_profile",
        return_value=_FIXTURE_PROFILE,
    ), patch(
        "vera.research.packs.jobs.scorer.load_profile",
        return_value=_FIXTURE_PROFILE,
    ), patch(
        "vera.research.packs.jobs.scorer.load_target_companies",
        return_value=set(),
    ):
        cal = run_calibration(fixtures=fixtures)
    assert cal["total"] == 1
    assert cal["passed"] == 1
    assert cal["accuracy"] == 1.0
    assert cal["by_category"]["high"] == {"total": 1, "passed": 1}


def test_run_calibration_blocked_detected():
    fixtures = [
        {
            "name": "Data Analyst",
            "expected": "blocked",
            "job": {"title": "Data Analyst", "description": "SQL"},
        }
    ]
    with patch(
        "vera.research.packs.jobs.calibration.load_profile",
        return_value=_FIXTURE_PROFILE,
    ), patch(
        "vera.research.packs.jobs.scorer.load_profile",
        return_value=_FIXTURE_PROFILE,
    ), patch(
        "vera.research.packs.jobs.scorer.load_target_companies",
        return_value=set(),
    ):
        cal = run_calibration(fixtures=fixtures)
    assert cal["passed"] == 1
    assert cal["results"][0]["is_blocked"]


def test_run_calibration_failure_reported():
    # Vaga que o profile nao deveria marcar como high mas fixture espera high
    fixtures = [
        {
            "name": "Role sem match",
            "expected": "high",
            "job": {"title": "Something random", "description": ""},
        }
    ]
    with patch(
        "vera.research.packs.jobs.calibration.load_profile",
        return_value=_FIXTURE_PROFILE,
    ), patch(
        "vera.research.packs.jobs.scorer.load_profile",
        return_value=_FIXTURE_PROFILE,
    ), patch(
        "vera.research.packs.jobs.scorer.load_target_companies",
        return_value=set(),
    ):
        cal = run_calibration(fixtures=fixtures)
    assert cal["failed"] == 1
    assert "FORA" in cal["results"][0]["reason"]


def test_format_report_renders():
    cal = {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "accuracy": 0.5,
        "mae_vs_manual": 1.5,
        "by_category": {"high": {"total": 1, "passed": 1}, "low": {"total": 1, "passed": 0}},
        "results": [
            {
                "name": "OK case",
                "stage": "Processo",
                "expected": "high",
                "manual_fit": 9,
                "rule_score": 8.5,
                "is_blocked": False,
                "blocker_reason": None,
                "passed": True,
                "reason": "ok",
            },
            {
                "name": "Fail case",
                "stage": "Descartei",
                "expected": "low",
                "manual_fit": 2,
                "rule_score": 5.0,
                "is_blocked": False,
                "blocker_reason": None,
                "passed": False,
                "reason": "score 5.0 FORA de [0, 2]",
            },
        ],
        "failures": [{"name": "Fail case", "reason": "score 5.0 FORA de [0, 2]"}],
    }
    report = format_report(cal)
    assert "CALIBRATION" in report
    assert "OK case" in report
    assert "Fail case" in report
    assert "FORA" in report
    assert "MAE vs manual:   1.50" in report
