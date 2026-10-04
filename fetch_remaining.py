"""One-off fetch for the 5 stubborn images with simpler queries."""
import time
import requests
from pathlib import Path

UA = "YemeniSpiceShop/1.0 (https://github.com/Aflathoon; contact@example.com)"
API = "https://commons.wikimedia.org/w/api.php"
IMG = Path("app/static/images")

# (filename_without_ext, simpler wikimedia query)
TARGETS = [
    ("yemeni_mokha_haraz", "coffee beans roast"),
    ("manuka_honey",       "honey jar"),
    ("zaatar",             "Za'atar"),
    ("sumac",              "sumac spice"),
    ("assam",              "Assam tea"),
]


def fetch(name, query):
    out = IMG / f"{name}.jpg"
    if out.exists() and out.stat().st_size > 5000:
        print(f"   ⏭  {out.name} already exists")
        return True

    headers = {"User-Agent": UA, "Accept": "application/json"}
    params = {
        "action": "query", "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": 6, "gsrlimit": 8,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 800,
    }

    for attempt in range(4):
        try:
            time.sleep(1.5)
            r = requests.get(API, headers=headers, params=params, timeout=25)
            if r.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"   ⏳ 429, waiting {wait}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
            if not pages:
                print(f"   ⚠  no results for '{query}'")
                return False
            for page in pages.values():
                infos = page.get("imageinfo", [])
                if not infos:
                    continue
                info = infos[0]
                url = info.get("thumburl") or info.get("url")
                if not url:
                    continue
                time.sleep(1.2)
                img = requests.get(url, headers=headers, timeout=30)
                img.raise_for_status()
                out.write_bytes(img.content)
                artist = info.get("extmetadata", {}).get("Artist", {}).get("value", "unknown")
                import re
                artist = re.sub(r"<[^>]+>", "", artist).strip() or "unknown"
                print(f"   ✅ {out.name}  (by {artist})")
                return True
            print("   ⚠  pages but no usable URL")
            return False
        except Exception as e:
            print(f"   ❌ {type(e).__name__}: {e}")
            time.sleep(2 * (attempt + 1))
    return False


ok = 0
for name, q in TARGETS:
    print(f"→ {name}  (query: '{q}')")
    if fetch(name, q):
        ok += 1

print(f"\n✅ {ok}/{len(TARGETS)} fetched")
