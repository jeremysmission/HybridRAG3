from pathlib import Path

from src.tools.bulk_transfer_v2 import BulkTransferV2, TransferConfig, SourceDiscovery, AtomicTransferWorker


def test_skip_full_discovery_uses_resume_seed_only(tmp_path, monkeypatch):
    """
    When skip_full_discovery=True, engine should not run source crawl.
    It should transfer only resume-seeded candidates.
    """
    src_root = tmp_path / "src"
    dst_root = tmp_path / "dst"
    src_root.mkdir()
    dst_root.mkdir()
    sample = src_root / "seed.txt"
    sample.write_text("hello", encoding="utf-8")

    seeded_item = (str(sample), str(src_root), sample.name, sample.stat().st_size)
    seen = {"items": []}

    def fake_resume_seed_iter(self):
        yield seeded_item

    def fake_discover_iter(self):
        raise AssertionError("discover_iter should not run when skip_full_discovery=True")

    def fake_transfer(self, queue):
        seen["items"] = list(queue)
        self.stats.files_copied = len(seen["items"])

    monkeypatch.setattr(SourceDiscovery, "resume_seed_iter", fake_resume_seed_iter)
    monkeypatch.setattr(SourceDiscovery, "discover_iter", fake_discover_iter)
    monkeypatch.setattr(AtomicTransferWorker, "transfer", fake_transfer)

    cfg = TransferConfig(
        source_paths=[str(src_root)],
        dest_path=str(dst_root),
        workers=1,
        skip_full_discovery=True,
    )
    engine = BulkTransferV2(cfg)
    stats = engine.run()

    assert len(seen["items"]) == 1
    assert seen["items"][0][0] == str(sample)
    assert stats.files_copied == 1
