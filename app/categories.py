"""
Category metadata for the shop.

Each category gets:
  - slug         (URL)
  - label        (display name)
  - tagline      (short hero subtitle)
  - description  (longer paragraph for SEO)
  - image        (hero image filename in app/static/images/)
"""

CATEGORIES = {
    "coffee": {
        "label": "Coffee",
        "tagline": "Single-origin beans from Yemen, Brazil, Ethiopia and beyond",
        "description": (
            "Heirloom Yemeni Mokha, Brazilian Cerrado, Ethiopian Yirgacheffe. "
            "Roasted for filter, espresso, or traditional gahwa."
        ),
        "image": "yemeni_mokha_haraz.jpg",
    },
    "tea": {
        "label": "Tea",
        "tagline": "Black, green, and herbal from across the tea belt",
        "description": (
            "Darjeeling first flush, malty Assam, high-grown Ceylon, and caffeine-free "
            "Rooibos. Loose-leaf, single-estate where possible."
        ),
        "image": "darjeeling.jpg",
    },
    "spices": {
        "label": "Spices",
        "tagline": "Whole and ground, sourced from the source",
        "description": (
            "Kashmiri saffron, Malabar pepper, Alleppey cardamom, Lakadong turmeric, "
            "Ceylon cinnamon, Himalayan pink salt, and blends like Za'atar and Ras el Hanout."
        ),
        "image": "kashmiri_saffron.jpg",
    },
    "herbs": {
        "label": "Herbs",
        "tagline": "Culinary and medicinal, dried at origin",
        "description": (
            "Yemeni dried mint, Greek oregano, Provence lavender, "
            "Herbes de Provence, and Thai aromatics like lemongrass and kaffir lime."
        ),
        "image": "greek_oregano.jpg",
    },
    "honey": {
        "label": "Honey",
        "tagline": "Raw, unheated, straight from the hive",
        "description": (
            "Yemeni Sidr from Hadhramaut, Sumar from the Sana'a highlands, "
            "Manuka MGO 850+, and Provence wildflower. Nothing filtered, nothing blended."
        ),
        "image": "yemeni_sidr_honey.jpg",
    },
    "blends": {
        "label": "Blends",
        "tagline": "Our house mixes and traditional combinations",
        "description": (
            "Curated blends for cooking, brewing, and gifting. "
            "Developed in-house with our own stocks."
        ),
        "image": "ras_el_hanout.jpg",
    },
    "accessories": {
        "label": "Accessories",
        "tagline": "Teaware, grinders, and gifts",
        "description": (
            "Cast iron teapots, pour-over kits, brass coffee grinders, "
            "gift boxes, and branded bags. For the shelf and the kitchen."
        ),
        "image": "placeholder.jpg",
    },
}


def get_category(slug):
    """Return (slug, meta) or None."""
    if slug in CATEGORIES:
        return slug, CATEGORIES[slug]
    return None


def all_categories():
    """Return list of (slug, meta) tuples, ordered."""
    order = ["coffee", "tea", "spices", "herbs", "honey", "blends", "accessories"]
    return [(s, CATEGORIES[s]) for s in order if s in CATEGORIES]
