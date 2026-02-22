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
from packaging.utils import parse_wheel_filename
from packaging.tags import sys_tags, Tag


# --------------- setup_submission_env (copied from app.py) ---------------
# This is a verbatim copy so we can test without importing app.py
# (which has import-time side effects: MongoDB connection, env vars, etc.)


def is_wheel_compatible(wheel_path: str):
    # Validate wheel filename
    filename = os.path.basename(wheel_path)
    try:
        _,_,_, wheel_tags = parse_wheel_filename(filename)
    except ValueError:
        return False, "Invalid filename format (not a valid wheel name)"
    
    # Get system supported tags
    supported_tags: list[Tag] = list(sys_tags())
    supported_set = set(supported_tags)
    
    if not wheel_tags.isdisjoint(supported_set):
        return True, "compatible"
    
    # Case no match
    curr_sys_tag = supported_tags[0]
    curr_w_tag = list(wheel_tags)[0]
    
    mismatches = []
    
    if curr_w_tag.interpreter != curr_sys_tag.interpreter:
        mismatches.append(f"Python Version Mismatch: Wheel expects {curr_w_tag.interpreter}, System is {curr_sys_tag.interpreter}")
    
    if curr_w_tag.abi != curr_sys_tag.abi:
        mismatches.append(f"ABI Mismatch: Wheel expects {curr_w_tag.abi}, System is {curr_sys_tag.abi}")
        
    if curr_w_tag.platform != curr_sys_tag.platform:
        mismatches.append(f"Platform Mismatch: Wheel expects {curr_w_tag.platform}, System is {curr_sys_tag.platform}")
        
    reason = " | ".join(mismatches) if mismatches else "Unknown tag incompatibility"
    
    return False, reason


def setup_submission_env(extract_path, lstore_path) -> tuple[str | None, str | None]:
    """
    Detects whether the submission contains pre-built wheel files or a requirements.txt,
    and if so creates a per-submission virtualenv and installs the dependencies into it.

    Returns:
        tuple: (python_executable: str or None, error_message: str or None)
    """
    venv_dir = os.path.join(extract_path, "venv")

    # Detect any wheels in lstore_path
    all_found_wheels = glob.glob(os.path.join(lstore_path, "**", "*.whl"), recursive=True)
    
    incompatible_errors = []
    valid_wheels = []
    
    for whl in all_found_wheels:
        is_ok, reason = is_wheel_compatible(whl) # Assuming this is defined elsewhere
        if is_ok:
            valid_wheels.append(whl)
        else:
            incompatible_errors.append(f"{os.path.basename(whl)}: {reason}")
    
    # No point continuing if any wheels don't work cause the code probably depends on all of them
    if incompatible_errors:
        error_details = "\n".join(incompatible_errors)
        return None, f"Compatibility Error:\n{error_details}"

    # Detect requirements.txt directly inside lstore_path
    requirements_file = os.path.join(lstore_path, "requirements.txt")
    has_requirements = os.path.isfile(requirements_file)

    if not all_found_wheels and not has_requirements:
        return sys.executable, None

    # Create virtualenv
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", venv_dir],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return None, "Environment Error: Virtualenv creation timed out."
    except Exception as e:
        return None, f"Environment Error: Virtualenv creation failed: {e}"

    # Resolve platform-specific python path inside venv
    if os.name == "nt":
        venv_python = os.path.join(venv_dir, "Scripts", "python")
    else:
        venv_python = os.path.join(venv_dir, "bin", "python")

    # Install wheels
    if valid_wheels:
        for whl in valid_wheels:
            try:
                subprocess.run(
                    [venv_python, "-m", "pip", "install", whl, "--quiet"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                return None, f"Install Error: pip install timed out for {os.path.basename(whl)}"
            except Exception as e:
                return None, f"Install Error: pip install failed for {os.path.basename(whl)}: {e}"

    # Install requirements
    if has_requirements:
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
            return None, "Install Error: pip install -r requirements.txt timed out"
        except Exception as e:
            return None, f"Install Error: pip install -r requirements.txt failed: {e}"

    return venv_python, None


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
        python_exe, errors = setup_submission_env(extract_path, lstore_path)

            
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
        python_exe, error = setup_submission_env(extract_path, lstore_path)
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
