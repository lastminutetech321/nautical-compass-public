import os
import py_compile

EXCLUDE_DIRS = {"venv", "__pycache__", ".git"}
ERRORS = []

def should_skip(path):
    return any(part in EXCLUDE_DIRS for part in path.split(os.sep))

for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

    for file in files:
        if file.endswith(".py"):
            full_path = os.path.join(root, file)

            if should_skip(full_path):
                continue

            try:
                py_compile.compile(full_path, doraise=True)
                print(f"[OK] {full_path}")
            except Exception as e:
                ERRORS.append((full_path, str(e)))
                print(f"[ERROR] {full_path} -> {e}")

print("\n--- SUMMARY ---")
if ERRORS:
    print(f"FAILED: {len(ERRORS)} file(s)")
    for path, err in ERRORS:
        print(f"{path}: {err}")
    exit(1)
else:
    print("SUCCESS: All Python files compiled cleanly")
