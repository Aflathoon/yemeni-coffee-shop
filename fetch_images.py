#!/usr/bin/env python3
"""
Multi-source image fetcher.

Sources:
  1. Unsplash API   — high-quality stock (needs UNSPLASH_ACCESS_KEY)
  2. Wikimedia      — public domain, no key, factual images

Usage:
    python fetch_images.py                 # fetch all
    python fetch_images.py --source unsplash
    python fetch_images.py --source wikimedia
    python fetch_images.py --only cardamom
    python fetch_images.py --limit 5
"""
import os
import re
import sys
import time
import json
import argparse
import hashlib
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

UNSPLASH_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "").strip()
WIKI_UA = os.getenv(
    "WIKIMEDIA_USER_AGENT",
    "YemeniSpiceShop/1.0 (https://github.com/Aflathoon; dev@localhost)",
)

IMAGE_DIR = Path("app/static/images")
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# QUERIES: (filename_key, unsplash_query, wikimedia_query)
# ---------------------------------------------------------------------------
QUERIES = [
    # Yemeni coffee
    ("yemeni_mokha_haraz",  "yemen coffee beans roasted",  "Coffea arabica beans"),
    ("yemeni_bani_matar",   "coffee beans dark roast",     "coffee cherry plant"),
    ("yemeni_ismaili",      "light roast coffee beans",    "green coffee beans"),
    # Brazil / Ethiopia / global coffee
    ("brazil_cerrado",      "brazil coffee beans",         "Coffea arabica Brazil"),
    ("brazil_santos",       "coffee sack beans",           "coffee bag warehouse"),
    ("ethiopia_yirgacheffe","ethiopian coffee cup",        "Ethiopia coffee drying"),
    # Yemeni honey
    ("yemeni_sidr_honey",   "amber honey jar",             "honey jar glass"),
    ("yemeni_sumar_honey",  "raw honey spoon",             "honey dipper wooden"),
    ("yemeni_honeycomb",    "honeycomb fresh",             "honeycomb bee"),
    ("manuka_honey",        "dark honey jar",              "Manuka honey jar"),
    ("provence_honey",      "wildflower honey",            "wildflower meadow honey"),
    # Indian spices
    ("kashmiri_saffron",    "saffron threads red",         "Crocus sativus saffron"),
    ("malabar_pepper",      "black peppercorns pile",      "Piper nigrum dried"),
    ("alleppey_cardamom",   "green cardamom pods",         "Elettaria cardamomum pods"),
    ("ceylon_cinnamon",     "cinnamon sticks bundle",      "Cinnamomum verum bark"),
    ("star_anise",          "star anise whole",            "Illicium verum"),
    ("zanzibar_cloves",     "cloves dried spice",          "Syzygium aromaticum dried"),
    ("lakadong_turmeric",   "turmeric powder golden",      "Curcuma longa powder"),
    ("rajasthan_cumin",     "cumin seeds bowl",            "Cuminum cyminum seeds"),
    ("coriander_seed",      "coriander seeds",             "Coriandrum sativum seeds"),
    # Pakistani spices
    ("himalayan_pink_salt", "himalayan pink salt",         "halite pink salt"),
    ("kashmiri_chili",      "red chili powder spice",      "Capsicum annuum powder"),
    ("ajwain",              "carom seeds ajwain",          "Trachyspermum ammi"),
    ("fenugreek",           "fenugreek seeds",             "Trigonella foenum-graecum"),
    ("black_cardamom",      "black cardamom pods",         "Amomum subulatum"),
    # Middle Eastern
    ("zaatar",              "zaatar spice blend",          "Za'atar herb mix"),
    ("sumac",               "sumac spice red",             "Rhus coriaria ground"),
    ("ras_el_hanout",       "moroccan spices market",      "Ras el hanout"),
    ("baharat",             "middle eastern spices",       "Baharat spice mix"),
    # Asian
    ("sichuan_peppercorn",  "sichuan peppercorns",         "Zanthoxylum piperitum"),
    ("galangal",            "galangal dried slices",       "Alpinia galanga"),
    ("lemongrass",          "lemongrass dried stalks",     "Cymbopogon citratus"),
    ("kaffir_lime",         "kaffir lime leaves",          "Citrus hystrix leaves"),
    # Herbs
    ("yemeni_mint",         "dried mint leaves",           "Mentha dried"),
    ("greek_oregano",       "dried oregano greek",         "Origanum vulgare dried"),
    ("provence_lavender",   "culinary lavender flowers",   "Lavandula angustifolia"),
    ("herbes_provence",     "herbes de provence",          "Herbes de Provence"),
    # Tea
    ("rooibos",             "rooibos tea red",             "Aspalathus linearis"),
    ("darjeeling",          "darjeeling tea leaves",       "Camellia sinensis Darjeeling"),
    ("assam",               "assam black tea",             "Camellia sinensis Assam"),
    ("ceylon_tea",          "ceylon black tea",            "Camellia sinensis Sri Lanka"),
]


# ---------------------------------------------------------------------------
# Unsplash
# ---------------------------------------------------------------------------
def fetch_unsplash(query: str, out_path: Path, index: int = 0) -> bool:
    if not UNSPLASH_KEY:
        return False
    url = "https://api.unsplash.com/search/photos"
    headers = {"Authorization": f"Client-ID {UNSPLASH_KEY}"}
    params = {"query": query, "per_page": 3, "orientation": "squarish"}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        if r.status_code == 401:
            print(f"   ❌ Unsplash 401 — key invalid or not approved yet")
            return False
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            print(f"   ⚠️  Unsplash: no results for '{query}'")
            return False

        pick = results[min(index, len(results) - 1)]
        # Use "regular" size for balance of quality vs. file size
        img_url = pick["urls"]["regular"]
        img = requests.get(img_url, timeout=30)
        img.raise_for_status()
        out_path.write_bytes(img.content)
        attribution = pick.get("user", {}).get("name", "unknown")
        print(f"   ✅ Unsplash → {out_path.name}  (by {attribution})")
        time.sleep(1.2)  # Unsplash rate-limit courtesy
        return True
    except requests.HTTPError as e:
        print(f"   ❌ Unsplash HTTP {e.response.status_code} for '{query}'")
        return False
    except Exception as e:
        print(f"   ❌ Unsplash error: {e}")
        return False


# ---------------------------------------------------------------------------
# Wikimedia Commons
# ---------------------------------------------------------------------------
WIKI_API = "https://commons.wikimedia.org/w/api.php"


def fetch_wikimedia(query: str, out_path: Path) -> bool:
    headers = {"User-Agent": WIKI_UA}
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": 6,          # File namespace
        "gsrlimit": 5,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 800,          # request a scaled thumbnail
    }
    try:
        r = requests.get(WIKI_API, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        if not pages:
            print(f"   ⚠️  Wikimedia: no results for '{query}'")
            return False

        # Pick the first image with a thumburl
        for page in pages.values():
            infos = page.get("imageinfo", [])
            if not infos:
                continue
            info = infos[0]
            img_url = info.get("thumburl") or info.get("url")
            if not img_url:
                continue
            img = requests.get(img_url, headers=headers, timeout=30)
            img.raise_for_status()
            out_path.write_bytes(img.content)
            artist = (
                info.get("extmetadata", {})
                .get("Artist", {})
                .get("value", "unknown")
            )
            # Strip HTML from artist name
            artist = re.sub(r"<[^>]+>", "", artist).strip() or "unknown"
            print(f"   ✅ Wikimedia → {out_path.name}  (by {artist})")
            time.sleep(0.5)
            return True

        print(f"   ⚠️  Wikimedia: results found, but no usable image URL")
        return False
    except Exception as e:
        print(f"   ❌ Wikimedia error: {e}")
        return False


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def fetch_one(name: str, unsplash_q: str, wiki_q: str, sources, index: int = 0):
    out_path = IMAGE_DIR / f"{name}.jpg"
    if out_path.exists() and out_path.stat().st_size > 5000:
        print(f"   ⏭  {out_path.name} already exists")
        return True

    if "unsplash" in sources:
        if fetch_unsplash(unsplash_q, out_path, index=index):
            return True
        if "wikimedia" not in sources:
            return False

    if "wikimedia" in sources:
        if fetch_wikimedia(wiki_q, out_path):
            return True

    print(f"   ❌ Failed to fetch {name}")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["unsplash", "wikimedia", "both"], default="both")
    ap.add_argument("--only", help="Substring filter on key name")
    ap.add_argument("--limit", type=int, help="Max number of images to fetch")
    ap.add_argument("--variants", type=int, default=1,
                    help="How many variants per query (unsplash only)")
    args = ap.parse_args()

    sources = ("unsplash", "wikimedia") if args.source == "both" else (args.source,)

    print(f"📸 Sources: {', '.join(sources)}")
    print(f"📁 Output : {IMAGE_DIR}\n")

    targets = QUERIES
    if args.only:
        targets = [q for q in QUERIES if args.only.lower() in q[0].lower()]
    if args.limit:
        targets = targets[: args.limit]

    ok, fail = 0, 0
    for name, usq, wmq in targets:
        print(f"→ {name}")
        for variant in range(args.variants):
            suffix = f"_{variant + 1}" if variant > 0 else ""
            this_name = f"{name}{suffix}"
            if fetch_one(this_name, usq, wmq, sources, index=variant):
                ok += 1
            else:
                fail += 1

    print(f"\n✅ {ok} fetched, ❌ {fail} failed")
    print(f"📁 Saved to {IMAGE_DIR}/")


if __name__ == "__main__":
    main()
