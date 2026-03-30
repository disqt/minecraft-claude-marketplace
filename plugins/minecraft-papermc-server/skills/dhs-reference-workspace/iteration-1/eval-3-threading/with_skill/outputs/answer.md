# DHS Threading Analysis: scheduler_threads=8, full_data_request_concurrency_limit=20

## How many LODs can actually be built in parallel?

**7 concurrent LOD builds.** Not 8, and not 20.

Here is why:

### The worker pool is shared

DHS has a single thread pool (`DHSupport-Worker-N`) sized by `scheduler_threads`. With your setting of 8, there are exactly 8 worker threads available. This pool is used for both LOD builder tasks *and* the pregen loop itself.

During pregen, the `PreGenerator.run()` method runs on this same pool via `runOnSeparateThread`. That consumes 1 of your 8 threads as a permanent resident for the duration of the pregen. The remaining **7 threads** are available for actual LOD building.

### full_data_request_concurrency_limit controls in-flight futures, not threads

Your `full_data_request_concurrency_limit: 20` controls how many LOD generation futures the pregen loop will have in-flight before it blocks:

```java
while (this.inFlight >= rateLimit) {
    CompletableFuture.anyOf(requests).join();
    requests.removeIf(CompletableFuture::isDone);
}
```

With a limit of 20, the pregen loop will fire off up to 20 LOD generation requests. Each request triggers async chunk loads (16 chunks per LOD section) and then queues a builder task on the worker pool. But since only 7 worker threads are available for building, at most 7 of those 20 in-flight requests are actively building LODs at any given moment. The other 13 sit in the pool's `LinkedBlockingQueue` waiting for a worker thread to become free.

This is not a deadlock -- the queue is unbounded, so work will always drain -- but throughput is capped at 7 concurrent builds regardless of the concurrency limit.

### Where is the bottleneck?

**The bottleneck is `scheduler_threads`, not `full_data_request_concurrency_limit`.**

With your current settings:

| Resource | Capacity | Actual usage during pregen |
|----------|----------|---------------------------|
| Worker threads (`scheduler_threads`) | 8 | 1 pregen loop + 7 builders = fully saturated |
| In-flight limit (`full_data_request_concurrency_limit`) | 20 | Up to 20 futures queued, but only 7 actively building |
| SQLite writes | 1 (serial) | Single-threaded executor, one write at a time |

There are actually **two bottlenecks** to be aware of:

1. **Worker thread pool (primary):** 7 effective builder threads. Raising `full_data_request_concurrency_limit` beyond 8 (your thread count) provides no additional build parallelism -- it only queues more futures in the backlog. To get more concurrent builds, you would need to increase `scheduler_threads`.

2. **SQLite writes (secondary):** All LOD saves go through `AsyncLodRepository`, which uses a single-threaded executor. Every completed LOD must serialize through this one-at-a-time database writer. If your builds are fast (e.g., `FastOverworldBuilder`), the DB writer can become the limiting factor since 7 builders may produce LODs faster than one thread can write them. The writes queue up but never cause backpressure on the builders -- they just delay the LOD being queryable.

### Should you change anything?

Your `full_data_request_concurrency_limit: 20` is higher than needed. With 8 scheduler threads (7 effective builders), a concurrency limit of 7-10 would produce the same throughput with less memory overhead from queued futures and their associated 16-chunk loads. Having 20 in-flight means up to 13 LOD requests may have their 16 chunks loaded into memory waiting for a builder thread, which wastes RAM for no throughput gain.

There is also a secondary concern: Paper's `global-max-concurrent-loads` setting limits how many async chunk loads can be in-flight server-wide. With 20 in-flight LODs, each needing 16 chunks, you could have up to 320 concurrent chunk load requests hitting Paper's chunk system. If Paper's limit is lower than that, some chunk loads will queue internally in Paper, which is fine but means the high concurrency limit is not actually loading chunks any faster.

### Summary

| Question | Answer |
|----------|--------|
| Max parallel LOD builds during pregen? | **7** (8 threads minus 1 for pregen loop) |
| Is there a bottleneck? | Yes -- `scheduler_threads` is the primary bottleneck. Your 20 concurrency limit cannot be utilized because only 7 workers are available for building |
| Does raising concurrency limit help? | No, not beyond ~8. It only queues more futures without increasing actual parallelism |
| What would help? | Raising `scheduler_threads` (e.g., to 12-16) would allow more concurrent builds, but watch CPU and Paper chunk system load |
