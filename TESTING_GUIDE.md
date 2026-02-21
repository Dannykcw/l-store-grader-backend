# Guide: Testing Wheel Support

This guide walks you through verifying that the grader correctly handles student submissions that include pre-built `.whl` files (Rust/PyO3, C++/pybind11, etc.).

In case something broke.

---
## Test vs submission
You are testing on your local computer. Therefore, there is no need to build for foreign targets. You will notice that the compilation command are shorter since there is no need for cross compilation.

---

## How the Grader Handles Wheels

When a submission arrives, `setup_submission_env()` in `app.py`:

1. Scans the submission folder for any `*.whl` files (recursive).
2. If found, creates a fresh virtual environment and installs the wheel(s) into it.
3. Returns the venv's `python` binary — all test runs use this binary.
4. If no wheels or `requirements.txt` are found, falls back to the system Python (no venv created).

The grader also prepends the submission folder to `PYTHONPATH`, so Python wrappers sitting alongside a wheel are picked up automatically.

---

## Prerequisites

Python 3.x - To Run the test script
Git - If you want to clone more repos to test with.

### Rust
Note that system package manager also works, but these commands work out of the box.

- Maturin -  Build `.whl` from Rust. 
  - conda: Run `conda install -c conda-forge maturin`. This will also install the rust toolchain for you.
  - pip: Run `pip install maturin`. Maturin will include a temporary rust toolchain for you if you didn't install a separate one.

Rust toolchain - Build Rust/PyO3 wheels. If you want to install it separately from maturin (for extended testing), run `curl https://sh.rustup.rs -sSf \| sh`

Check you have everything. Note that if you didn't install cargo separately you might not have `cargo` and that's fine cause you don't need it.

```bash
python3 --version
cargo --version
maturin --version
```

## C++
Does anyone actually do C++ in this class?

---

## Step 1: Set Up Test Fixtures

The test script expects two student repos cloned under `test-fixtures/` and their built wheels under `test-fixtures/wheels/`. run `git submodule update --init --recursive --remote` to get the repos.

```bash
cd test-fixtures
```

### Clone the repos (one-time)

```bash
git clone https://github.com/JakeRoggenbuck/RedoxQL
git clone https://github.com/keyur-parikh/cowabunga-db
```

### Build RedoxQL

RedoxQL is self-contained — the wheel includes both the native `.so` and the `lstore/` Python wrappers.

```bash
cd RedoxQL

# Python 3.14+ only: set this flag
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1

maturin build --release -o ../wheels
# Output: target/wheels/lstore-*.whl

cd ..
```

### Build CowabungaDB

CowabungaDB's wheel only contains the native extension. The `lstore/` Python wrappers must be submitted alongside it (the test script handles this automatically).

```bash
cd cowabunga-db
maturin build --release -o ../wheels
# Output: target/wheels/cowabunga_rs-*.whl
cd ..
```

You should see two `.whl` files in wheels directory.

---

## Step 2: Update the Test Script for Your Platform

The wheel filenames embed the platform tag (Python version + OS + architecture). The below is a example: 

```python
REDOXQL_WHEEL = os.path.join(
    FIXTURES, "wheels", "lstore-0.1.0-cp314-cp314-macosx_11_0_arm64.whl"
    #                           ^^^^ update to your actual filename
)
COWABUNGA_WHEEL = os.path.join(
    FIXTURES, "wheels", "cowabunga_rs-0.1.0-cp314-cp314-macosx_11_0_arm64.whl"
    #                              ^^^^ update to your actual filename
)
```

The test code should be able to handle any environment tahnks to regex. In case it didn't work for you, just change the `find_file` call or replace it with the exact string.

These paths are near the bottom of `test_wheel_support.py`.

The actual filenames are whatever `ls test-fixtures/wheels/` shows you.

---

## Step 3: Run the Test Script

From the repo root:

```bash
python3 test_wheel_support.py
```

### Expected output

```
============================================================
TEST: Pure Python (no wheels, no requirements.txt)
============================================================
  --- setup_submission_env ---
  Pure Python submission: using system python
  Returned python: /usr/bin/python3
  --- Import test ---
  STDOUT: OK: Pure Python import works
  RESULT: PASS

============================================================
TEST: RedoxQL
============================================================
  --- setup_submission_env ---
  Creating virtualenv at: /tmp/grader_test_RedoxQL_.../venv
  Detected wheels: installing into venv (1 file(s))
  Returned python: /tmp/grader_test_RedoxQL_.../venv/bin/python
  --- Import test ---
  STDOUT: OK: Database imported and instantiated
  RESULT: PASS

============================================================
TEST: CowabungaDB
============================================================
  --- setup_submission_env ---
  Creating virtualenv at: /tmp/grader_test_CowabungaDB_.../venv
  Detected wheels: installing into venv (1 file(s))
  Returned python: /tmp/grader_test_CowabungaDB_.../venv/bin/python
  --- Import test ---
  STDOUT: OK: Database imported and instantiated
  RESULT: PASS

============================================================
SUMMARY
============================================================
  Pure Python: PASS
  RedoxQL: PASS
  CowabungaDB: PASS
```

The script exits `0` on all-pass, `1` if any test fails.

---

## Troubleshooting

### `ERROR: No wheel with pattern: {pattern} in directory: {directory}`

You haven't built the wheels yet. Run `ls test-fixtures/wheels/`.

### `RESULT: FAIL` — pip install error in stderr

The wheel was built for a different Python version or OS. Rebuild on the same machine where you're running the test:

```bash
# Check what Python the script uses
python3 --version && python3 -c "import platform; print(platform.machine())"

# Rebuild wheels on this machine
cd test-fixtures/RedoxQL && maturin build --release
cd test-fixtures/cowabunga-db && maturin build --release
```

### `RESULT: FAIL` — `ModuleNotFoundError: No module named 'lstore'`

For RedoxQL: the wheel may not have built correctly (lstore should be inside it). Check `maturin build` output.

For CowabungaDB: `COWABUNGA_LSTORE` path doesn't point to the `lstore/` folder. Verify:

```bash
ls test-fixtures/cowabunga-db/lstore/
# Should show: __init__.py, db.py, query.py, ...
```

### Venv creation fails / times out

Python's `venv` module must be available. On some Linux distros it's a separate package:

```bash
# Debian/Ubuntu
sudo apt install python3-venv
```

---

## Note

- None of the test are in this repo.
- A wheel built on your machine won't install on a server with a different OS/Python. If the wheel is incorrectly build fo rthe servers's platform, the error should be propergated back to you.
- TODO: Testing `requirements.txt` submission. I couulnd't find a good one, so they're not covered by these fixtures. To test manually, add a `requirements.txt` (e.g., containing `sortedcontainers`) to a temp lstore folder and call `setup_submission_env()` directly.

---

## Adding a New Student Repo as a Test Case

If it's pure python (even with `requirements.txt`), you only need to:

1. Clone the repo into `test-fixtures/`.
2. Add a `test_submission(...)` call in `test_wheel_support.py`

If it's not:

1. Clone the repo into `test-fixtures/`.
2. Build the wheel (`maturin build --release` or equivalent). 
3. Copy the `.whl` to `test-fixtures/wheels/`.
4. Add a `test_submission(...)` call in `test_wheel_support.py`, following the RedoxQL or CowabungaDB pattern depending on whether the wheel is self-contained or needs separate Python wrappers.
