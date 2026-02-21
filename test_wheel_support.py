#!/usr/bin/env python3
"""
Standalone test for setup_submission_env() wheel support.

Tests that the grader can accept submissions containing pre-built .whl files
(Rust/PyO3 native bindings) by simulating the submission flow:
  1. Create a temp directory mimicking a student submission
  2. Call setup_submission_env() to detect wheels and create a venv
  3. Run a simple import test through the venv python

Tested against:
  - RedoxQL (https://github.com/JakeRoggenbuck/RedoxQL)
    Self-contained wheel — lstore package + native .so inside the wheel
  - CowabungaDB (https://github.com/keyur-parikh/cowabunga-db)
    Wheel only has native cowabunga_rs extension — lstore/ Python wrappers
    must be alongside it, picked up via PYTHONPATH
"""

import glob
import os
import shutil
import subprocess
import sys
import tempfile


# --------------- setup_submission_env (copied from app.py) ---------------
# This is a verbatim copy so we can test without importing app.py
# (which has import-time side effects: MongoDB connection, env vars, etc.)


def setup_submission_env(extract_path, lstore_path):
    venv_dir = os.path.join(extract_path, "venv")

    wheel_files = glob.glob(os.path.join(lstore_path, "**", "*.whl"), recursive=True)

    requirements_file = os.path.join(lstore_path, "requirements.txt")
    has_requirements = os.path.isfile(requirements_file)

    if not wheel_files and not has_requirements:
        print("Pure Python submission: using system python")
        return sys.executable

    try:
        print(f"  Creating virtualenv at: {venv_dir}")
        subprocess.run(
            [sys.executable, "-m", "venv", venv_dir],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        print("  Venv creation timed out; falling back to system python")
        return sys.executable
    except Exception as e:
        print(f"  Venv creation failed: {e}; falling back to system python")
        return sys.executable

    if os.name == "nt":
        venv_python = os.path.join(venv_dir, "Scripts", "python")
    else:
        venv_python = os.path.join(venv_dir, "bin", "python")

    if wheel_files:
        print(f"  Detected wheels: installing into venv ({len(wheel_files)} file(s))")
        for whl in wheel_files:
            try:
                subprocess.run(
                    [venv_python, "-m", "pip", "install", whl, "--quiet"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                print(f"  pip install timed out for {whl} (continuing)")
            except Exception as e:
                print(f"  pip install failed for {whl}: {e} (continuing)")

    if has_requirements:
        print("  Detected requirements.txt: installing into venv")
        try:
            subprocess.run(
                [
                    venv_python,
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    requirements_file,
                    "--quiet",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            print("  pip install -r requirements.txt timed out (continuing)")
        except Exception as e:
            print(f"  pip install -r requirements.txt failed: {e} (continuing)")

    return venv_python


# --------------- Test helpers ---------------


def run_import_test(python_cmd, lstore_path, test_code):
    """Run a Python snippet using the given python executable with PYTHONPATH set."""
    env = os.environ.copy()
    env["PYTHONPATH"] = lstore_path + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [python_cmd, "-c", test_code],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    return result


def test_submission(name, wheel_src, python_wrappers_src=None):
    """
    Simulate a student submission:
      1. Create temp extract_path and lstore_path
      2. Copy wheel(s) and optional Python wrappers into lstore_path
      3. Run setup_submission_env()
      4. Verify 'from lstore.db import Database' works
    """
    print(f"\n{'=' * 60}")
    print(f"TEST: {name}")
    print(f"{'=' * 60}")

    tmpdir = tempfile.mkdtemp(prefix=f"grader_test_{name}_")
    extract_path = tmpdir
    lstore_path = os.path.join(tmpdir, "lstore")
    os.makedirs(lstore_path, exist_ok=True)

    try:
        # Copy wheel into lstore_path (where glob will find it)
        whl_name = os.path.basename(wheel_src)
        shutil.copy2(wheel_src, os.path.join(lstore_path, whl_name))
        print(f"  Copied wheel: {whl_name}")

        # Copy Python wrappers if provided (CowabungaDB case)
        if python_wrappers_src:
            wrapper_dest = os.path.join(lstore_path, "lstore")
            shutil.copytree(python_wrappers_src, wrapper_dest)
            print(f"  Copied Python wrappers from: {python_wrappers_src}")

        # Run setup_submission_env
        print("\n  --- setup_submission_env ---")
        python_exe = setup_submission_env(extract_path, lstore_path)
        print(f"  Returned python: {python_exe}")

        # Test import
        print("\n  --- Import test ---")
        test_code = "from lstore.db import Database; db = Database(); print('OK: Database imported and instantiated')"
        result = run_import_test(python_exe, lstore_path, test_code)

        if result.returncode == 0:
            print(f"  STDOUT: {result.stdout.strip()}")
            print(f"  RESULT: PASS")
            return True
        else:
            print(f"  STDOUT: {result.stdout.strip()}")
            print(f"  STDERR: {result.stderr.strip()}")
            print(f"  RESULT: FAIL (exit code {result.returncode})")
            return False

    finally:
        # Cleanup
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_pure_python():
    """Test that a submission with no wheels returns sys.executable."""
    print(f"\n{'=' * 60}")
    print("TEST: Pure Python (no wheels, no requirements.txt)")
    print(f"{'=' * 60}")

    tmpdir = tempfile.mkdtemp(prefix="grader_test_pure_")
    extract_path = tmpdir
    lstore_path = os.path.join(tmpdir, "lstore")
    os.makedirs(lstore_path, exist_ok=True)

    try:
        # Write a dummy lstore/__init__.py
        os.makedirs(os.path.join(lstore_path, "lstore"), exist_ok=True)
        with open(os.path.join(lstore_path, "lstore", "__init__.py"), "w") as f:
            f.write("# pure python\n")
        with open(os.path.join(lstore_path, "lstore", "db.py"), "w") as f:
            f.write("class Database:\n    pass\n")

        print("\n  --- setup_submission_env ---")
        python_exe = setup_submission_env(extract_path, lstore_path)
        print(f"  Returned python: {python_exe}")

        if python_exe == sys.executable:
            print("  Correctly returned sys.executable (no venv created)")
        else:
            print(f"  WARNING: Expected sys.executable, got {python_exe}")

        # Verify import still works via PYTHONPATH
        print("\n  --- Import test ---")
        test_code = (
            "from lstore.db import Database; print('OK: Pure Python import works')"
        )
        result = run_import_test(python_exe, lstore_path, test_code)

        if result.returncode == 0:
            print(f"  STDOUT: {result.stdout.strip()}")
            print(f"  RESULT: PASS")
            return True
        else:
            print(f"  STDERR: {result.stderr.strip()}")
            print(f"  RESULT: FAIL")
            return False

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        
def find_file(directory:str, pattern:str):
        full_pattern = os.path.join(directory, pattern)
        matches = glob.glob(full_pattern)
        
        if not matches:
            print(f"ERROR: No wheel with pattern: {pattern} in directory: {directory}")
            if os.path.exists(directory):
                print(f"Available files: {os.listdir(directory)}")
            sys.exit(1)
            
        return matches[0]


# --------------- Main ---------------

if __name__ == "__main__":
    HERE = os.path.dirname(os.path.abspath(__file__))
    FIXTURES = os.path.join(HERE, "test-fixtures")
    WHEELS_DIR = os.path.join(FIXTURES, "wheels")
    #! this generic wheel name might break other test one day...
    # TODO better solution for 50 wheels with name lstore-* cause people can't come up with better names

    # Check wheels exist
    REDOXQL_WHEEL = find_file(WHEELS_DIR, "lstore-0.1.0-*.whl")
    COWABUNGA_WHEEL = find_file(WHEELS_DIR, "cowabunga_rs-0.1.0-*.whl")
    COWABUNGA_LSTORE = find_file(os.path.join(FIXTURES, "cowabunga-db"), "lstore")

    results = {}

    # Test 1: Pure Python (baseline — no wheels)
    results["Pure Python"] = test_pure_python()

    # Test 2: RedoxQL (self-contained wheel — lstore package inside the wheel)
    results["RedoxQL"] = test_submission(
        name="RedoxQL",
        wheel_src=REDOXQL_WHEEL,
    )

    # Test 3: CowabungaDB (wheel + separate Python wrappers)
    results["CowabungaDB"] = test_submission(
        name="CowabungaDB",
        wheel_src=COWABUNGA_WHEEL,
        python_wrappers_src=COWABUNGA_LSTORE,
    )

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    all_pass = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_pass = False

    print()
    sys.exit(0 if all_pass else 1)
