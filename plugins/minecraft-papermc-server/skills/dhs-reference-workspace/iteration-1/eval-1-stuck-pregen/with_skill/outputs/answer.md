# Diagnosis: Your Pregen Is Dead

Yes, it is stuck. More precisely, the pregen worker thread has silently died, but DHS still thinks it is running. Here is exactly what happened and how to fix it.

## What Went Wrong

You are hitting **Bug #2: PreGenerator Silent Death**. The `PreGenerator.run()` method has no try-catch around its main loop. At some point during the 17-hour run, one of the in-flight LOD generation futures threw an exception (could be a chunk load failure, an NPE from Bug #3 or #4, or any other transient error). That exception propagated through `CompletableFuture.anyOf(requests).join()` as a `CompletionException`, which killed the DHSupport-Worker thread running the pregen loop.

The critical detail: the `run` flag is only set to `false` at the very end of `run()` (line 129 in PreGenerator.java). Since the exception killed the thread before reaching that line, the flag stays `true`. That is why `dhs pregen status` still reports it as "running" at 21% -- it is reading stale in-memory state from a dead thread.

## How to Read the Symptoms

| Symptom | Explanation |
|---------|-------------|
| `dhs pregen status` says 21%, 5.35 CPS, time remaining infinite | The 5.35 CPS is a **stale cached value** from when the pregen was last actively generating. "Time remaining: infinite" means momentary CPS is actually 0 (division by zero). The pregen status display does not know the thread is dead. |
| `dhs status` shows 0.00 CPS globally | This is the **real-time** generation speed. Zero confirms nothing is being generated. |
| 0 DH players online | This is expected and not the cause -- pregen does not require connected DH players. It runs independently on the worker pool. |

## How to Confirm (If You Want Proof)

Two ways to verify the thread is dead before acting:

1. **Check worker threads:** Run `jstack <server-pid> | grep DHSupport` on the server. If zero DHSupport-Worker threads exist, the pool has timed out (workers die after 60 seconds of idleness) because the pregen thread that was keeping them busy is gone.

2. **Check database activity:** Run `stat plugins/DHSupport/data.sqlite` and check the modification time. If it has not changed in hours, nothing is writing LODs.

## How to Fix It

1. **Stop the dead pregen:**
   ```
   dhs pregen stop <world>
   ```
   This clears the stale `run` flag.

2. **Restart the pregen with the same parameters:**
   ```
   dhs pregen start <world> <centerX> <centerZ> <radius>
   ```
   The pregen skips LODs that already exist in `data.sqlite`, so the 21% of LODs already generated will be skipped quickly. You do not lose progress -- just the running task.

3. **Do NOT use `force`** unless you want to regenerate the LODs you already have. Without `force`, it picks up roughly where it left off.

## Preventing Future Deaths

There is no config-level fix for Bug #2 -- it requires a code patch (wrapping `run()` in a try-catch). Until that is fixed upstream, the pregen can silently die at any time from a transient exception. Mitigation strategies:

- **Monitor periodically:** Check `dhs status` for 0.00 CPS during pregen runs. If it drops to zero and stays there, the thread is dead.
- **Check `data.sqlite` mtime:** A simple cron or manual check -- if the file stops being modified, pregen has stalled.
- **Reduce blast radius:** Run pregen in smaller radius increments rather than one massive job. That way a crash loses less "momentum" and you notice sooner.

## Also Worth Knowing

**Bug #1 (chunk leak):** During pregen, DHS loads 16 chunks per LOD section but only properly discards 1 of 16 due to a map key collision bug. The other 15 chunks per section are loaded (and potentially generated if `generate_new_chunks: true`) but never explicitly unloaded. Over a long pregen run, this can cause significant memory pressure, which may increase the likelihood of exceptions that trigger Bug #2. Monitor server memory usage during pregen runs.
