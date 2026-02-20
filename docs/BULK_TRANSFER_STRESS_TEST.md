# Bulk Transfer V2 Stress Test Results

```

==================================================================================================
  STRESS TEST: Original HybridRAG3 vs Bulk Transfer V2
==================================================================================================

  Simulated: 5.00 GB across 962 files
  Network: 100 Mbps simulated

  METRIC                                                     ORIGINAL           V2 (BULK TRANSFER)
  -------------------------------------- ---------------------------- ----------------------------

  -- PERFORMANCE --
  Discovery time                                                 1.9s                         0.5s
  Transfer time                                                1m 22s                        14.4s
  Total time                                                   1m 24s                        14.9s
  Speedup                                             1.0x (baseline)                  5.7x faster
  Workers                                                           1                            8
  Data transferred                                            4.13 GB                     821.4 MB
  Wasted bandwidth (non-RAG)                                  3.09 GB                          0 B
  Avg speed                                                 49.8 MB/s                    55.2 MB/s
  Effective RAG throughput                                  12.5 MB/s                    55.2 MB/s

  -- FILE COUNTS --
  Files copied                                                    932                          636
  Files deduplicated                                                0                           92
  Filtered (wrong ext)                                              0                          125
  Filtered (size)                                                   0                            0
  Locked files detected                                            30                           16
  Hidden/system skipped                                             0                           62
  Symlinks skipped                                                  0                            8
  Encoding issues caught                                            0                           10
  Long path (>260) caught                                           0                            3
  Mid-write detected                                                0                           10
  Corrupt (hash mismatch)                                           0                            0
  Quarantined                                                       0                           26
  Failed                                                           30                            0

  -- INTEGRITY & SAFETY --
  Atomic copy (.tmp pattern)                                       NO                          YES
  Three-stage staging dirs                                         NO                          YES
  SHA-256 hash verification                                        NO                          YES
  Files verified                                                    0                          636
  Locked file detection                                            NO                          YES
  Mid-write detection                                              NO                          YES
  Quarantine for failures                                          NO                          YES

  -- INTELLIGENCE --
  Content deduplication                                            NO                          YES
  Delta sync (change detect)                                       NO                          YES
  Renamed file detection                                           NO                          YES
  Deleted file detection                                           NO                          YES
  Symlink loop guard                                               NO                          YES
  Long path awareness                                              NO                          YES
  Hidden/system awareness                                          NO                          YES
  Filename encoding check                                          NO                          YES

  -- OBSERVABILITY --
  Zero-gap manifest                                                NO                          YES
  Per-file timing/speed                                            NO                          YES
  Live progress + ETA                                              NO                          YES

  -- RAG READINESS --
  RAG-parseable files                                             819                          636
  RAG-parseable data                                          1.03 GB                     821.4 MB

  -------------------------------------- ---------------------------- ----------------------------

  FILES BY TYPE (top 10):

    .pdf                                                          209                          163
    .docx                                                         158                          119
    .xlsx                                                          90                           70
    .pptx                                                          68                           55
    .txt                                                           51                           42
    .png                                                           51                           37
    .jpg                                                           39                           34
    .csv                                                           42                           31
    .eml                                                           31                           23
    .log                                                           22                           18

  -------------------------------------- ---------------------------- ----------------------------

  KEY FINDINGS:

  1. SPEED: V2 is 5.7x faster (14.9s vs 1m 24s)
     via 8-thread parallelism + pre-filtering.

  2. BANDWIDTH: Original wasted 3.09 GB copying non-RAG files.
     V2 saves this entirely by filtering at discovery time.

  3. INTEGRITY: V2 verified 636 files via SHA-256
     (hash at source BEFORE copy, hash at dest AFTER copy).
     Original has no verification -- corrupt copies go undetected.

  4. ATOMIC COPY: V2 writes to .tmp, verifies hash, then atomic
     rename to verified/. A crash mid-copy leaves no partial files
     in the indexer's input directory. Original has no protection.

  5. LOCKED FILES: V2 detected 16 locked/in-use files
     (including PSTs) and quarantined them. Original would retry
     endlessly or copy a corrupt mid-write snapshot.

  6. MID-WRITE SAFETY: V2 caught 10 files being
     actively written (hash changed between read start and end).
     Original copies these silently -- producing corrupt embeddings.

  7. DEDUPLICATION: V2 eliminated 92 duplicates
     (158.3 MB saved). Original copies every duplicate.

  8. ZERO-GAP MANIFEST: V2 accounts for every single file in the
     source -- transferred, skipped, locked, quarantined. Original
     has no manifest; files that fail silently are invisible.

  9. DELTA SYNC: V2 supports incremental runs -- only transfers
     new/modified files. Detects renames (avoids re-indexing)
     and deletions (flags orphaned chunks for removal).

  10. EDGE CASES: V2 caught 10 encoding issues,
      3 long paths, 8 symlinks,
      62 hidden files. Original ignores all of these.

==================================================================================================
```
