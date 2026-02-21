# L-Store Submission Guide

Submit your project as a single `.zip` file. This file must contain one top-level folder with your code and any necessary build artifacts. The grader uses several modes to handle different project types.

## Supported Submission Modes

### Mode 1: Pure Python
Use this if your implementation is written entirely in Python without external dependencies. Just zip your folder containing the `lstore` package.

### Mode 2: Pre-built Wheel (Native Extensions)
Use this if you wrote parts of your database in Rust, C++, or Go. You must build a `.whl` file on your machine and include it in your zip.

There are two ways to organize this:
*   **Self-contained wheel:** The wheel includes both your binary and your Python wrapper files.
*   **Extension + Wrappers:** The wheel only installs the native module. You must also include your `lstore/` Python folder in the zip so the grader can find it.

**If you are doing wheels, Make sure to read the platform constrain section.** It contains important information about platform compatibility. Mode 1 & 3 need not apply.

### Mode 3: Requirements File
Use this if your project needs external packages from PyPI. Include a `requirements.txt` file at the root of your submission folder. The grader will create a virtual environment and install these dependencies before running tests.

## Directory Structure Examples

**Mode 1 (Pure Python)**
```
my_submission.zip
└── my_lstore_project/
    └── lstore/
        ├── __init__.py
        ├── db.py
        ├── query.py
        └── ...
```

**Mode 2a (Self-contained wheel)**
```
my_submission.zip
└── my_lstore_project/
    └── lstore-0.1.0-cp311-cp311-linux_x86_64.whl
```

**Mode 2b (Native extension + Python wrappers)**
```
my_submission.zip
└── my_lstore_project/
    ├── my_native_ext-0.1.0-cp311-cp311-linux_x86_64.whl
    └── lstore/
        ├── __init__.py
        ├── db.py
        └── ...
```

**Mode 3 (Requirements file)**
```
my_submission.zip
└── my_lstore_project/
    ├── requirements.txt
    └── lstore/
        ├── __init__.py
        └── ...
```

## Building with Maturin

Before you build your wheels, **you must configure your binding library to use abi3**. This means that you may not use the Pypy interpreter. (it does not support abi3, in fact, it does not have a stable abi)

The below example uses `abi3-py39`, meaning that it supports target of python 3.9 and above. If you run into trouble, you may use `abi3-py38` and so on for compatibility. You may also try bumping it to `abi3-py311` if you want to squeeze a tiny bit of performance.

```toml
[dependencies]
# Note the feature 
pyo3 = { version = "0.28.0", features = ["extension-module", "abi3-py39"] }
```

Then, to ensure glibc compatibility, you have two options.
1. Using zig. (`pip install ziglang`)
2. Using docker. Any docker compatible daemon works (Docker, podman, orbstack)

zig is going to be the easiest and most storage friendly. You only really need Docker for some edge cases.

If you use Rust and PyO3, follow these steps to create your wheel:

### zig

```bash
# Install maturin
pip install maturin
pip install ziglang

# Build a release wheel
maturin build --release --target x86_64-unknown-linux-gnu --zig
```

### Docker

```bash
# Make sure the docker engine is installed and running
docker run --rm --platform linux/amd64 -v $(pwd):/io ghcr.io/pyo3/maturin build --release
```

The output appears in `target/wheels/` regardless of methods. Take the `.whl` file from there and put it in your submission folder (i.e. the project root). Alternatively, the -o flag for maturin may be used.

## Platform Constraints

The wheel must match the server platform exactly. A wheel built for macOS won't run on a Linux server. 

Check the platform tag in your wheel filename. For example, `lstore-0.1.0-cp311-cp311-linux_x86_64.whl` is for CPython 3.11 on Linux x86_64.

## Submission
The zip should contain (at minimum) what is necessary to run the testers. This means:
- the `lstore/` folder
- Wheels (if any)
- dependency/project config file (e.g. pyproject.toml, cargo.toml, CMakelist.txt).
- The .git folder. **

You can also just zip up everything because the grader read only the necessary part.

## Common Mistakes

*   **Wrong platform:** Submitting a macOS or Windows wheel to a Linux grader. It will fail to install.
*   **Invalid package path:** The grader expects to import lstore directly. Your Python class definitions must be inside the `lstore/` folder. Intermediate directories like `python/lstore/` will break the grader's import logic.
*   **Wrong file location:** Putting `requirements.txt`, `cargo.toml`, or other config file inside the `lstore/` folder. It must be at the top level of your submission folder.
