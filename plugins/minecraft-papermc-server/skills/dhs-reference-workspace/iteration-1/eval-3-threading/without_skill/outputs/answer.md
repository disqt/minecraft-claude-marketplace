# DHS Threading During Pregen: Analysis of Your Configuration

## Your Settings

- `scheduler_threads`: 8
- `full_data_request_concurrency_limit`: 20

## How DHS Threading Works

I need to be upfront: my knowledge of the Distant Horizons Server-side (DHS) plugin's internal threading architecture is limited. DHS is a relatively niche server-side companion to the Distant Horizons client mod, and its internal scheduling details are not something I have thorough documentation on.

That said, here is what I can reason about from general knowledge of the Distant Horizons ecosystem and typical server-side LOD generation patterns:

### What These Settings Likely Control

**`scheduler_threads` (8):** This is almost certainly the thread pool size for the actual LOD computation work -- taking chunk data and building the Level of Detail representations. With 8 threads, you have 8 workers that can process LOD tasks concurrently.

**`full_data_request_concurrency_limit` (20):** This likely caps how many concurrent requests DHS can make to the server's world/chunk system to retrieve full chunk data needed for LOD generation. This is an I/O-bound limit -- how many chunks can be read from disk or requested from the world generator simultaneously.

### The Bottleneck Analysis

**The effective parallelism is likely capped at 8, not 20.**

Here is the reasoning: LOD generation is a two-stage pipeline:

1. **Data acquisition** -- read/generate the chunk data (bounded by `full_data_request_concurrency_limit` = 20)
2. **LOD computation** -- process that chunk data into LOD format (bounded by `scheduler_threads` = 8)

Even though you can have up to 20 chunk data requests in flight, only 8 LODs can actually be computed at any given moment. The pipeline means that having the data request limit higher than the thread count (20 > 8) is actually sensible -- it allows prefetching of chunk data so the 8 computation threads always have work ready and are never starved waiting for I/O.

### During Pregen With No Players

With no players online during pregen:

- The server has minimal other load, so your 8 scheduler threads should get good CPU time
- The 20 concurrent data requests can keep a healthy queue of chunks ready for processing
- **The practical throughput bottleneck is the 8 scheduler threads** -- this is where the actual LOD math happens and it is CPU-bound work
- A secondary bottleneck can be **disk I/O** if the chunks need to be generated or read from disk, but with 20 concurrent requests feeding 8 workers, you have good buffering

### Is Your Configuration Reasonable?

Your ratio of 20:8 (data requests to compute threads) is sensible. The data request limit being ~2.5x the thread count means there should generally be queued work available for each thread when it finishes a task.

**Potential improvements to consider:**

- If your server has more than 8 cores available and CPU utilization is not saturated, you could try increasing `scheduler_threads` to 10-12
- If you are seeing the 8 threads consistently idle-waiting for data, the bottleneck is on the data acquisition side (disk I/O or world generation speed), and increasing `full_data_request_concurrency_limit` further might help -- but 20 should be plenty for most setups
- If pregen involves generating new chunks (not just reading existing ones), the vanilla/Paper world generation itself becomes a major bottleneck, as it has its own threading constraints

## Caveat

I am not confident in the precise internal architecture of DHS. The plugin's threading model, queue management, and how these two settings interact at the code level may differ from my reasoning above. I would recommend checking the DHS documentation, Discord, or source code for authoritative answers about the threading pipeline.
