# Runtime Threadpool Compatibility Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the custom daemon threadpool so real market-data collection works under the current Python runtime without losing fast process-exit behavior.

**Architecture:** Keep `DaemonThreadPoolExecutor`, but isolate the runtime-dependent worker bootstrap into a small compatibility helper that chooses the correct `_worker` argument shape for the active interpreter and logs the selected mode. Protect it with focused regression tests plus a full test run.

**Tech Stack:** Python, asyncio, concurrent.futures, pytest

---

### Task 1: Add failing runtime-compatibility tests

**Files:**
- Modify: `tests/test_data_fetcher.py`
- Modify: `src/collector/data_fetcher.py`

**Step 1: Write the failing test**

Add tests proving:

- `DaemonThreadPoolExecutor` reports a supported bootstrap mode for the current runtime
- `_build_worker_args()` returns the expected tuple shape for the active interpreter
- `DataCollector._run_blocking()` executes a trivial callable successfully

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py -q`

**Step 3: Write minimal implementation**

- add a helper that selects runtime worker bootstrap mode
- wire `_adjust_thread_count()` through that helper
- add one-time compatibility logging

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py -q`

**Step 5: Commit**

```bash
git add src/collector/data_fetcher.py tests/test_data_fetcher.py
git commit -m "fix: support current runtime daemon threadpool bootstrap"
```

### Task 2: Add a targeted runtime sanity check

**Files:**
- Modify: `tests/test_data_fetcher.py`
- Modify: `src/collector/data_fetcher.py`

**Step 1: Write the failing test**

Add a test proving the executor exposes a non-empty compatibility mode string and that mode is stable after first resolution.

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py -q`

**Step 3: Write minimal implementation**

- cache the compatibility mode on the executor instance
- expose it through a small helper used by tests and logging

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py -q`

**Step 5: Commit**

```bash
git add src/collector/data_fetcher.py tests/test_data_fetcher.py
git commit -m "test: lock runtime executor compatibility mode"
```

### Task 3: Verify integration

**Files:**
- No code change required

**Step 1: Run focused tests**

```bash
source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py -q
```

**Step 2: Run full suite**

```bash
source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest -q
```

**Step 3: Run runtime smoke check**

```bash
source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && python -m src.main --mode swing --dry-run --output json | tail -n 1 | jq '{data_timestamp, market_conclusion}'
```

Confirm:

- no `_create_worker_context`-style executor bootstrap error appears
- collector proceeds past threadpool startup

**Step 4: Commit docs**

```bash
git add docs/plans/2026-03-26-runtime-threadpool-compat-design.md docs/plans/2026-03-26-runtime-threadpool-compat-implementation.md
git commit -m "docs: add runtime threadpool compatibility plan"
```
