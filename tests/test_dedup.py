"""Testes para DedupEngine."""

from datetime import datetime, timedelta, timezone

import pytest

from vera.research.base import ResearchItem
from vera.research.dedup import DedupEngine


def _make_item(id="item-1", title="Test", url="https://example.com"):
    return ResearchItem(
        id=id,
        title=title,
        url=url,
        source_name="Test",
        published=None,
        content="content",
    )


@pytest.fixture
def dedup_path(tmp_path):
    return tmp_path / "dedup" / "test.json"


class TestDedupEngine:
    def test_compute_id_deterministic(self):
        id1 = DedupEngine.compute_id("Title", "https://url.com", "Source")
        id2 = DedupEngine.compute_id("Title", "https://url.com", "Source")
        assert id1 == id2

    def test_compute_id_case_insensitive(self):
        id1 = DedupEngine.compute_id("Title", "https://url.com", "Source")
        id2 = DedupEngine.compute_id("title", "https://url.com", "Source")
        assert id1 == id2

    def test_is_seen_new_item(self, dedup_path):
        dedup = DedupEngine(dedup_path, default_ttl_days=7)
        assert not dedup.is_seen("new-item")

    def test_mark_and_check(self, dedup_path):
        dedup = DedupEngine(dedup_path, default_ttl_days=7)
        dedup.mark_seen("item-1")
        assert dedup.is_seen("item-1")

    def test_ttl_expiry(self, dedup_path):
        dedup = DedupEngine(dedup_path, default_ttl_days=7)
        # Marca com TTL ja expirado
        expired = datetime.now(timezone.utc) - timedelta(hours=1)
        dedup._seen["old-item"] = expired.isoformat()
        assert not dedup.is_seen("old-item")

    def test_filter_new(self, dedup_path):
        dedup = DedupEngine(dedup_path, default_ttl_days=7)
        dedup.mark_seen("item-1")

        items = [_make_item("item-1"), _make_item("item-2"), _make_item("item-3")]
        new = dedup.filter_new(items)
        assert len(new) == 2
        assert all(i.id != "item-1" for i in new)

    def test_cleanup_expired(self, dedup_path):
        dedup = DedupEngine(dedup_path, default_ttl_days=7)

        # Uma valida, uma expirada
        dedup.mark_seen("valid")
        expired = datetime.now(timezone.utc) - timedelta(days=1)
        dedup._seen["expired"] = expired.isoformat()

        removed = dedup.cleanup_expired()
        assert removed == 1
        assert dedup.is_seen("valid")
        assert not dedup.is_seen("expired")

    def test_persistence_save_load(self, dedup_path):
        dedup = DedupEngine(dedup_path, default_ttl_days=7)
        dedup.mark_seen("persisted")
        dedup.save()

        # Reload
        dedup2 = DedupEngine(dedup_path, default_ttl_days=7)
        assert dedup2.is_seen("persisted")

    def test_seen_count(self, dedup_path):
        dedup = DedupEngine(dedup_path, default_ttl_days=7)
        assert dedup.seen_count == 0
        dedup.mark_seen("a")
        dedup.mark_seen("b")
        assert dedup.seen_count == 2

    def test_mark_items(self, dedup_path):
        dedup = DedupEngine(dedup_path, default_ttl_days=7)
        items = [_make_item("a"), _make_item("b")]
        dedup.mark_items(items)
        assert dedup.is_seen("a")
        assert dedup.is_seen("b")

    def test_load_corrupted_file(self, dedup_path):
        dedup_path.parent.mkdir(parents=True, exist_ok=True)
        dedup_path.write_text("not json", encoding="utf-8")
        dedup = DedupEngine(dedup_path)
        assert dedup.seen_count == 0
