# Stuck DHS Pregen Diagnosis

## Short Answer

Yes, your pregen is almost certainly stuck. The key evidence is `dhs status` showing **0.00 CPS globally with 0 DH players online**. Even though `dhs pregen status` reports 5.35 CPS, that figure is likely a historical/average value rather than a live measurement. If the global DHS status shows 0.00 CPS, no chunks are actually being generated right now.

## Why This Happens

DHS (Distant Horizons Support) pregen can stall for several common reasons:

1. **Thread starvation / deadlock**: DHS pregen tasks can get stuck waiting on world-gen threads that are blocked or deadlocked, especially under heavy pregen loads over long periods. This is the most common cause of a pregen that reports progress but has actually stopped moving.

2. **Memory pressure**: After 17 hours of continuous pregen, the server may have accumulated enough memory pressure that GC pauses or OOM-adjacent conditions are stalling chunk generation. DH's LOD generation is memory-intensive.

3. **Chunk generation conflicts**: If the server's world generation pipeline has hit a problematic chunk (e.g., a structure that triggers excessive computation or a mod-compatibility issue in worldgen), it can block the entire pregen queue.

4. **"Infinite" time remaining**: This confirms the issue. DHS calculates ETA from recent throughput. "Infinite" means recent throughput has dropped to zero or near-zero, even though the lifetime average still shows 5.35 CPS.

## How to Fix It

### Immediate Steps

1. **Stop the current pregen:**
   ```
   dhs pregen stop
   ```
   Wait for confirmation that it has fully stopped.

2. **Check server resource usage:**
   - Check CPU and memory usage. If the server is thrashing on memory, consider increasing `-Xmx` or reducing DH render distance before restarting pregen.
   - Check TPS with `/spark tps` or similar. If TPS is degraded, the server may need a restart.

3. **Restart the pregen from where it left off:**
   ```
   dhs pregen start
   ```
   DHS pregen tracks its progress, so restarting will resume from approximately where it stopped (around 21%). It does not start over from 0%.

### If It Stalls Again After Restart

1. **Restart the server entirely**, then start the pregen again. A fresh JVM clears any accumulated memory fragmentation or thread deadlocks.

2. **Lower the pregen thread count** if you have it set high. Fewer threads reduces the chance of thread contention:
   ```
   dhs pregen threads <lower_number>
   ```
   Try 1-2 threads if you were using more.

3. **Lower the pregen generation detail level**. If you are generating high-detail LODs, consider dropping to a lower detail level for the bulk pregen, then letting real-time generation fill in higher detail as players explore.

4. **Run pregen in shorter sessions**. Instead of one continuous 80+ hour session, run it for a few hours at a time with server restarts in between. This avoids the long-running memory and thread issues.

### Preventive Measures for Future Pregens

- **Monitor `dhs status` periodically**, not just `dhs pregen status`. The global CPS is the ground truth for whether work is actually happening.
- **Set up a restart schedule** if running very large pregens (restart server every 6-12 hours).
- **Ensure adequate memory allocation**. DH pregen benefits from generous heap space. 6-8GB minimum for dedicated pregen runs.
- **Keep DHS and Distant Horizons updated**. Pregen stall bugs are actively being fixed in newer releases.

## Summary

| Indicator | Value | Meaning |
|-----------|-------|---------|
| `dhs pregen status` CPS | 5.35 | Lifetime/rolling average -- misleading |
| `dhs status` CPS | 0.00 | **Actual current throughput -- nothing is happening** |
| DH players online | 0 | No real-time generation either |
| Time remaining | Infinite | Recent throughput is zero |

**Verdict**: Pregen is stuck. Stop it, optionally restart the server, then resume. It will pick up from ~21%.
