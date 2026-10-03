#!/usr/bin/env python3
"""
Multi-source image fetcher with rate-limit handling.

Usage:
    python fetch_images.py
    python fetch_images.py --source wikimedia
    python fetch_images.py --only cardamom
    python fetch_images.py --limit 5
    python fetch_images.py --retry-failed
    python fetch_images.py --retry-failed --source wikimedia --wiki-only-delay 1.5
"""
import os, re, sys, time, argparse, requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

UNSPLASH_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "").strip()
WIKI_UA = os.getenv(
    "WIKIMEDIA_USER_AGENT",
    "YemeniSpiceShop/1.0 (https://github.com/Aflathoon; contact@example.com)",
)

IMAGE_DIR = Path("app/static/images")
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

WIKI_MIN_INTERVAL = 1.2
_last_wiki_call = [0.0]
UNSPLASH_MIN_INTERVAL = 0.8
_last_unsplash_call = [0.0]

# (filename_key_without_ext, unsplash_query, wikimedia_query)
QUERIES = [
    ("yemeni_mokha_haraz",   "yemen coffee beans roasted",  "Coffea arabica beans"),
    ("yemeni_bani_matar",    "coffee beans dark roast",     "coffee cherry plant"),
    ("yemeni_ismaili",       "light roast coffee beans",    "green coffee beans"),
    ("brazil_cerrado",       "brazil coffee beans",         "Coffea arabica Brazil"),
    ("brazil_santos",        "coffee sack beans",           "coffee bag warehouse"),
    ("ethiopia_yirgacheffe", "ethiopian coffee cup",        "Ethiopia coffee drying"),
    ("yemeni_sidr_honey",    "amber honey jar",             "honey jar glass"),
    ("yemeni_sumar_honey",   "raw honey spoon",             "honey dipper wooden"),
    ("yemeni_honeycomb",     "honeycomb fresh",             "honeycomb bee"),
    ("manuka_honey",         "dark honey jar",              "Manuka honey jar"),
    ("provence_honey",       "wildflower honey",            "wildflower meadow honey"),
    ("kashmiri_saffron",     "saffron threads red",         "Crocus sativus saffron"),
    ("malabar_pepper",       "black peppercorns pile",      "Piper nigrum dried"),
    ("alleppey_cardamom",    "green cardamom pods",         "Elettaria cardamomum pods"),
    ("ceylon_cinnamon",      "cinnamon sticks bundle",      "Cinnamomum verum bark"),
    ("star_anise",           "star anise whole",            "Illicium verum"),
    ("zanzibar_cloves",      "cloves dried spice",          "Syzygium aromaticum dried"),
    ("lakadong_turmeric",    "turmeric powder golden",      "Curcuma longa powder"),
    ("rajasthan_cumin",      "cumin seeds bowl",            "Cuminum cyminum seeds"),
    ("coriander_seed",       "coriander seeds",             "Coriandrum sativum seeds"),
    ("himalayan_pink_salt",  "himalayan pink salt",         "halite pink salt"),
    ("kashmiri_chili",       "red chili powder spice",      "Capsicum annuum powder"),
    ("ajwain",               "carom seeds ajwain",          "Trachyspermum ammi"),
    ("fenugreek",            "fenugreek seeds",             "Trigonella foenum-graecum"),
    ("black_cardamom",       "black cardamom pods",         "Amomum subulatum"),
    ("zaatar",               "zaatar spice blend",          "Za'atar herb mix"),
    ("sumac",                "sumac spice red",             "Rhus coriaria ground"),
    ("ras_el_hanout",        "moroccan spices market",      "Ras el hanout"),
    ("baharat",              "middle eastern spices",       "Baharat spice mix"),
    ("sichuan_peppercorn",   "sichuan peppercorns",         "Zanthoxylum piperitum"),
    ("galangal",             "galangal dried slices",       "Alpinia galanga"),
    ("lemongrass",           "lemongrass dried stalks",     "Cymbopogon citratus"),
    ("kaffir_lime",          "kaffir lime leaves",          "Citrus hystrix leaves"),
    ("yemeni_mint",          "dried mint leaves",           "Mentha dried"),
    ("greek_oregano",        "dried oregano greek",         "Origanum vulgare dried"),
    ("provence_lavender",    "culinary lavender flowers",   "Lavandula angustifolia"),
    ("herbes_provence",      "herbes de provence mix",      "Herbes de Provence"),
    ("rooibos",              "rooibos tea cup red",         "Aspalathus linearis"),
    ("darjeeling",           "darjeeling tea cup",          "Camellia sinensis leaves"),
    ("assam",                "assam tea strong cup",        "Camellia sinensis plantation"),
    ("ceylon_tea",           "ceylon tea black cup",        "Camellia sinensis Sri Lanka"),
]


def _throttle(bucket, interval):
    now = time.monotonic()
    delta = now - bucket[0]
    if delta < interval:
        time.sleep(interval - delta)
    bucket[0] = time.monotonic()


def _retry_after(resp, default=3.0):
    h = resp.headers.get("Retry-After")
    if h:
        try:
            return max(float(h), 1.0)
        except ValueError:
            pass
    return default


def fetch_unsplash(query, out_path, index=0, max_retries=2):
    if not UNSPLASH_KEY:
        return False
    headers = {"Authorization": f"Client-ID {UNSPLASH_KEY}"}
    params = {"query": query, "per_page": 3, "orientation": "squarish"}
    url = "https://api.unsplash.com/search/photos"

    for attempt in range(max_retries + 1):
        try:
            _throttle(_last_unsplash_call, UNSPLASH_MIN_INTERVAL)
            r = requests.get(url, headers=headers, params=params, timeout=20)

            if r.status_code == 401:
                print("   ❌ Unsplash 401 — key invalid or app not approved")
                return False
            if r.status_code == 403:
                print("   ❌ Unsplash 403 — rate limit / quota")
                if attempt < max_retries:
                    time.sleep(5 * (attempt + 1))
                    continue
                return False
            r.raise_for_status()

            results = r.json().get("results", [])
            if not results:
                print(f"   ⚠  Unsplash: no results for '{query}'")
                return False

            pick = results[min(index, len(results) - 1)]
            img_url = pick["urls"]["regular"]

            _throttle(_last_unsplash_call, UNSPLASH_MIN_INTERVAL)
            img = requests.get(img_url, timeout=30)
            img.raise_for_status()
            out_path.write_bytes(img.content)

            attribution = pick.get("user", {}).get("name", "unknown")
            print(f"   ✅ Unsplash → {out_path.name}  (by {attribution})")
            return True
        except requests.HTTPError as e:
            code = e.response.status_code if e.response else "?"
            print(f"   ❌ Unsplash HTTP {code} for '{query}'")
            if attempt < max_retries:
                time.sleep(2 * (attempt + 1))
                continue
        except Exception as e:
            print(f"   ❌ Unsplash error: {e}")
            if attempt < max_retries:
                time.sleep(2 * (attempt + 1))
                continue
    return False


WIKI_API = "https://commons.wikimedia.org/w/api.php"


def fetch_wikimedia(query, out_path, max_retries=4):
    headers = {"User-Agent": WIKI_UA, "Accept": "application/json"}
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": 6,
        "gsrlimit": 5,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 800,
    }

    for attempt in range(max_retries + 1):
        try:
            _throttle(_last_wiki_call, WIKI_MIN_INTERVAL)
            r = requests.get(WIKI_API, headers=headers, params=params, timeout=20)

            if r.status_code == 429:
                wait = _retry_after(r, default=4.0 * (attempt + 1))
                print(f"   ⏳ Wikimedia 429 — waiting {wait:.1f}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
                continue

            r.raise_for_status()
            data = r.json()
            pages = data.get("query", {}).get("pages", {})
            if not pages:
                print(f"   ⚠  Wikimedia: no results for '{query}'")
                return False

            for page in pages.values():
                infos = page.get("imageinfo", [])
                if not infos:
                    continue
                info = infos[0]
                img_url = info.get("thumburl") or info.get("url")
                if not img_url:
                    continue

                _throttle(_last_wiki_call, WIKI_MIN_INTERVAL)
                img = requests.get(img_url, headers=headers, timeout=30)
                img.raise_for_status()
                out_path.write_bytes(img.content)

                artist = info.get("extmetadata", {}).get("Artist", {}).get("value", "unknown")
                artist = re.sub(r"<[^>]+>", "", artist).strip() or "unknown"
                print(f"   ✅ Wikimedia → {out_path.name}  (by {artist})")
                return True

            print("   ⚠  Wikimedia: pages found, no usable image URL")
            return False
        except requests.HTTPError as e:
            code = e.response.status_code if e.response else "?"
            if code == 429 and attempt < max_retries:
                wait = 4.0 * (attempt + 1)
                print(f"   ⏳ Wikimedia 429 — backing off {wait:.1f}s")
                time.sleep(wait)
                continue
            print(f"   ❌ Wikimedia HTTP {code} for '{query}'")
            if attempt < max_retries:
                time.sleep(2 * (attempt + 1))
                continue
        except Exception as e:
            print(f"   ❌ Wikimedia error: {e}")
            if attempt < max_retries:
                time.sleep(2 * (attempt + 1))
                continue
    return False


def fetch_one(name, unsplash_q, wiki_q, sources, index=0):
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
    ap.add_argument("--limit", type=int)
    ap.add_argument("--variants", type=int, default=1)
    ap.add_argument("--retry-failed", action="store_true",
                    help="Only try items whose .jpg is missing from disk")
    ap.add_argument("--wiki-only-delay", type=float, default=WIKI_MIN_INTERVAL)
    args = ap.parse_args()

    global WIKI_MIN_INTERVAL
    WIKI_MIN_INTERVAL = args.wiki_only_delay

    sources = ("unsplash", "wikimedia") if args.source == "both" else (args.source,)
    print(f"📸 Sources: {', '.join(sources)}")
    print(f"📁 Output : {IMAGE_DIR}")
    print(f"🐢 Wikimedia delay: {WIKI_MIN_INTERVAL}s\n")

    targets = QUERIES
    if args.only:
        targets = [q for q in QUERIES if args.only.lower() in q[0].lower()]
    if args.retry_failed:
        targets = [q for q in targets if not (IMAGE_DIR / f"{q[0]}.jpg").exists()]

    print(f"🎯 {len(targets)} target(s)\n")

    ok, fail = 0, 0
    for name, usq, wmq in targets:
        print(f"→ {name}")
        for variant in range(args.variants):
            suffix = f"_{variant + 1}" if variant > 0 else ""
            if fetch_one(f"{name}{suffix}", usq, wmq, sources, index=variant):
                ok += 1
            else:
                fail += 1

    print(f"\n✅ {ok} fetched, ❌ {fail} failed")
    print(f"📁 Saved to {IMAGE_DIR}/")


if __name__ == "__main__":
    main()

