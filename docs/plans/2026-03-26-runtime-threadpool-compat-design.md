# Runtime Threadpool Compatibility Design

**Goal:** Restore real market-data collection under the current Python runtime by making the custom daemon threadpool compatible with the active `concurrent.futures.thread` worker signature while preserving fast CLI exit behavior.

## Problem

`DataCollector` uses a custom `DaemonThreadPoolExecutor` so hung third-party calls do not block process exit. That executor copied CPython internals from an older runtime. Under the project's current virtualenv, `ThreadPoolExecutor` workers are started with a different argument shape than the one our subclass hardcodes. The result is a runtime crash during real data collection before any source request completes.

## Scope

- Fix only the executor/runtime compatibility layer.
- Keep the existing `DataCollector` fetch, retry, timeout, and circuit-breaker logic intact.
- Add explicit diagnostics so runtime incompatibility becomes visible immediately instead of surfacing as opaque downstream source failures.

## Recommended Approach

Keep the custom daemon executor, but stop assuming a single private CPython layout.

1. Build worker-thread arguments dynamically from the active runtime.
2. Prefer the current stdlib `ThreadPoolExecutor` contract when available.
3. Keep daemon thread creation as the only intentional override.
4. Emit one structured compatibility log line when the executor chooses its worker bootstrap mode.

This is the smallest change that fixes production behavior without reopening the original shutdown-hang risk.

## Design Details

### Executor Bootstrap

Add a helper inside `DaemonThreadPoolExecutor` that inspects the runtime shape and returns the correct `_worker` args tuple:

- Python runtimes exposing `_initializer` / `_initargs` use `(executor_reference, work_queue, initializer, initargs)`.
- Runtimes exposing `_create_worker_context()` use `(executor_reference, ctx, work_queue)`.

If neither layout is available, raise a targeted `RuntimeError` that includes the runtime version and executor attributes that were inspected. This gives a deterministic failure instead of the current misleading source-level errors.

### Diagnostics

Log the chosen bootstrap mode once per executor instance:

- `legacy_initializer_args`
- `worker_context_args`

If the runtime is unsupported, log and raise immediately during thread creation.

### Test Strategy

Cover three behaviors:

1. The executor still produces daemon threads.
2. The runtime-specific worker arg builder returns the correct tuple for the current interpreter.
3. `_run_blocking()` can execute a simple callable end-to-end without hitting the old `_create_worker_context` failure path.

## Risks

- We still depend on CPython private internals, so future runtime bumps can break again.
- That risk is acceptable because:
  - daemonized workers are still needed for safe process exit,
  - the new helper centralizes the compatibility boundary,
  - diagnostics make the next break obvious and localized.

## Out of Scope

- Replacing the executor architecture entirely.
- Reworking collector source fallback logic.
- Fixing unrelated market-data source failures.
