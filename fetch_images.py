#!/usr/bin/env python3
"""Fetch product images from Unsplash. Run once before starting Flask."""
import os, requests, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
if not ACCESS_KEY or ACCESS_KEY == "PASTE_YOUR_KEY_HERE":
    raise SystemExit("❌ Set UNSPLASH_ACCESS_KEY in .env first. Get one free at unsplash.com/developers")

IMAGE_DIR = Path("app/static/images")
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# Each entry: (search query, filename base)
QUERIES = [
    ("yemeni coffee beans", "yemeni_coffee"),
    ("arabica coffee cherry", "arabica_cherry"),
    ("coffee roasting beans", "coffee_roast"),
    ("coffee cup pour over", "coffee_pour"),
    ("honey jar amber", "honey_jar"),
    ("raw honeycomb", "honeycomb"),
    ("spices market bowls", "spices_market"),
    ("cardamom pods", "cardamom"),
    ("cinnamon sticks", "cinnamon"),
    ("black pepper corns", "pepper"),
    ("turmeric powder", "turmeric"),
    ("saffron threads", "saffron"),
    ("fresh mint leaves", "mint"),
    ("dried herbs bundle", "herbs_bundle"),
    ("lavender flowers", "lavender"),
    ("tea leaves ceramic", "tea_leaves"),
]

def download(query, base_name):
    url = "https://api.unsplash.com/search/photos"
    params = {"query": query, "per_page": 2, "orientation": "landscape"}
    headers = {"Authorization": f"Client-ID {ACCESS_KEY}"}
    
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        
        for i, result in enumerate(data.get("results", [])[:2]):
            img_url = result["urls"]["regular"]
            # Download at reasonable size, resize later
            img_data = requests.get(img_url, timeout=30).content
            filename = f"{base_name}_{i+1}.jpg"
            filepath = IMAGE_DIR / filename
            filepath.write_bytes(img_data)
            print(f"✅ {filename}")
            time.sleep(1)  # rate limit courtesy
    except Exception as e:
        print(f"❌ {query}: {e}")

if __name__ == "__main__":
    print(f"📸 Downloading {len(QUERIES)} image sets to {IMAGE_DIR}/\n")
    for query, name in QUERIES:
        download(query, name)
    print(f"\n✅ Done. Images in {IMAGE_DIR}/")
