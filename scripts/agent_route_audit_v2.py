import os
import re

ROUTES = []
TEMPLATE_LINKS = []

EXCLUDE = {".git", ".venv", "__pycache__"}

for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in EXCLUDE]

    for f in files:
        if f.endswith(".py"):
            path = os.path.join(root, f)
            with open(path, "r", encoding="utf-8", errors="ignore") as file:
                content = file.read()

            matches = re.findall(r'@\w+\.\w+\(\s*["\']([^"\']+)["\']', content)
            ROUTES.extend(matches)

for root, dirs, files in os.walk("./templates"):
    dirs[:] = [d for d in dirs if d not in EXCLUDE]

    for f in files:
        if f.endswith(".html"):
            path = os.path.join(root, f)
            with open(path, "r", encoding="utf-8", errors="ignore") as file:
                content = file.read()

            links = re.findall(r'href=["\']([^"\']+)["\']', content)

            for l in links:
                if "{{" in l:
                    continue
                if not l.startswith("/"):
                    continue
                if l.startswith("/static"):
                    continue

                TEMPLATE_LINKS.append(l.split("?")[0].split("#")[0])

missing = sorted(set([l for l in TEMPLATE_LINKS if l not in ROUTES]))

print("\n--- CLEAN ROUTE AUDIT ---\n")
print(f"Routes: {len(set(ROUTES))}")
print(f"Links: {len(TEMPLATE_LINKS)}\n")

for m in missing:
    print(m)
