import os
import re

ROUTES = []
TEMPLATE_LINKS = []

EXCLUDE_DIRS = {".git", ".venv", "venv", "__pycache__"}

def skip_path(path):
    parts = set(path.split(os.sep))
    return bool(parts & EXCLUDE_DIRS)

print("Scanning routes...\n")

for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

    for file in files:
        if not file.endswith(".py"):
            continue

        path = os.path.join(root, file)

        if skip_path(path):
            continue

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        matches = re.findall(r'@\w+\.\w+\(\s*["\']([^"\']+)["\']', content)
        for route in matches:
            ROUTES.append(route)

print("Scanning templates...\n")

for root, dirs, files in os.walk("./templates"):
    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

    for file in files:
        if not file.endswith(".html"):
            continue

        path = os.path.join(root, file)

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        links = re.findall(r'href=["\']([^"\']+)["\']', content)
        for link in links:
            TEMPLATE_LINKS.append(link)

missing = []

for link in TEMPLATE_LINKS:
    if not link.startswith("/"):
        continue
    if link.startswith("/static"):
        continue
    if link.startswith("/#"):
        continue

    clean_link = link.split("?")[0].split("#")[0]

    if clean_link not in ROUTES:
        missing.append(clean_link)

print("\n--- ROUTE AUDIT ---\n")
print(f"Total Routes Found: {len(set(ROUTES))}")
print(f"Total Template Links: {len(TEMPLATE_LINKS)}\n")

if missing:
    print("BROKEN / UNMATCHED LINKS:\n")
    for item in sorted(set(missing)):
        print(item)
else:
    print("All template links match discovered routes")

print("\n--- END ---")
