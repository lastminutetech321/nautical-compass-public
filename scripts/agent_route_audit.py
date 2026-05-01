import os
import re

ROUTES = []
TEMPLATE_LINKS = []

print("Scanning routes...\n")

# Find all route definitions
for root, _, files in os.walk("./routes"):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

                matches = re.findall(r'@.*?\\("(.*?)"', content)
                for m in matches:
                    ROUTES.append(m)

# Scan templates for links/buttons
print("Scanning templates...\n")

for root, _, files in os.walk("./templates"):
    for file in files:
        if file.endswith(".html"):
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

                links = re.findall(r'href="(.*?)"', content)
                for l in links:
                    TEMPLATE_LINKS.append(l)

# Compare
print("\n--- ROUTE AUDIT ---\n")

missing = []

for link in TEMPLATE_LINKS:
    if link.startswith("/") and link not in ROUTES:
        missing.append(link)

print(f"Total Routes Found: {len(ROUTES)}")
print(f"Total Template Links: {len(TEMPLATE_LINKS)}\n")

if missing:
    print("⚠️ BROKEN / UNMATCHED LINKS:\n")
    for m in set(missing):
        print(m)
else:
    print("✅ All template links match routes")

print("\n--- END ---")
