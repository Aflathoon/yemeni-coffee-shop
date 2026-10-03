"""Knowledge-based AI agent. Global spices/herbs, Yemeni coffee & honey flagship."""

KNOWLEDGE = {
    # ---- COFFEE ----
    "yemeni": {
        "origin": "Yemen — Haraz, Bani Matar, Ismaili. Grown 1,500–2,200 m on stone terraces.",
        "recommended_use": "Pour-over or Turkish. Traditionally spiced with cardamom and ginger (gahwa).",
        "flavor_notes": "Wine-like acidity, dark chocolate, dried fruit, tobacco.",
    },
    "brazil": {
        "origin": "Brazil — Cerrado, Santos, Minas Gerais. World's largest coffee producer.",
        "recommended_use": "Espresso, milk drinks, cold brew. The workhorse of blends.",
        "flavor_notes": "Nutty, chocolate, low acidity, sweet.",
    },
    "ethiopia": {
        "origin": "Ethiopia — Yirgacheffe, Sidamo, Harrar. Birthplace of Coffea arabica.",
        "recommended_use": "Pour-over, filter. Serve black to taste the terroir.",
        "flavor_notes": "Jasmine, citrus, bergamot, stone fruit.",
    },
    # ---- HONEY ----
    "sidr": {
        "origin": "Yemen — Hadhramaut. Bees forage on Sidr (jujube) blossoms.",
        "recommended_use": "One spoonful daily. Drizzle on yogurt, cheese, pastries.",
        "flavor_notes": "Rich caramel, butterscotch, faint menthol. Very thick.",
    },
    "manuka": {
        "origin": "New Zealand — Northland. Leptospermum scoparium blossoms.",
        "recommended_use": "Take by spoonful for medicinal benefit; don't cook it.",
        "flavor_notes": "Earthy, mineral, dark. Antibacterial (MGO rating).",
    },
    "wildflower": {
        "origin": "Region-dependent — multi-floral.",
        "recommended_use": "Everyday honey. Tea, toast, baking.",
        "flavor_notes": "Varies by season and flora. Soft, aromatic.",
    },
    # ---- SPICES ----
    "saffron": {
        "origin": "Iran, India (Kashmir), Afghanistan. Hand-harvested Crocus sativus stigmas.",
        "recommended_use": "Bloom in warm milk/water 10 min. Add to rice, kheer, tea.",
        "flavor_notes": "Honey, hay, floral. A pinch is enough.",
    },
    "cardamom": {
        "origin": "India (Kerala), Guatemala, Sri Lanka. Green = Elettaria; black = Amomum.",
        "recommended_use": "Crush pods into coffee, chai, rice pudding.",
        "flavor_notes": "Eucalyptus, citrus, mint. Aromatic and cooling.",
    },
    "cinnamon": {
        "origin": "Ceylon (Sri Lanka, true) vs. Cassia (China, Vietnam). Different species.",
        "recommended_use": "Ceylon: delicate, use freely. Cassia: stronger, use sparingly.",
        "flavor_notes": "Sweet, woody, warm. Ceylon more floral.",
    },
    "turmeric": {
        "origin": "India (Meghalaya — Lakadong), Southeast Asia. Curcuma longa root.",
        "recommended_use": "Golden milk, curries, rice. Bloom in fat for absorption.",
        "flavor_notes": "Earthy, mustard-like, bright gold.",
    },
    "pepper": {
        "origin": "India (Malabar), Vietnam, Indonesia. Piper nigrum vine.",
        "recommended_use": "Crack fresh over everything. Toast whole for deeper flavor.",
        "flavor_notes": "Sharp, citrusy, complex heat.",
    },
    "sumac": {
        "origin": "Turkey, Iran, Levant. Dried Rhus coriaria berries.",
        "recommended_use": "Finish salads, grilled meats, hummus. Bright without acid.",
        "flavor_notes": "Tangy, lemony, deep red.",
    },
    "za'atar": {
        "origin": "Levant (Jordan, Lebanon, Syria). Blend of thyme, sesame, sumac.",
        "recommended_use": "Mix with olive oil for bread dip. Sprinkle on labneh.",
        "flavor_notes": "Herbal, nutty, tart.",
    },
    "ras el hanout": {
        "origin": "Morocco. 'Head of the shop' — 20+ spice blend.",
        "recommended_use": "Tagines, lamb, couscous, roasted vegetables.",
        "flavor_notes": "Warm, floral, complex.",
    },
    "sichuan": {
        "origin": "China (Sichuan). Zanthoxylum — citrus family, not true pepper.",
        "recommended_use": "Toast and grind. Creates 'ma la' numbing sensation.",
        "flavor_notes": "Numbing, citrus, tingle.",
    },
    "himalayan": {
        "origin": "Pakistan — Khewra salt mine, Punjab.",
        "recommended_use": "Finish salt. Grind over grilled meats, salads, chocolate.",
        "flavor_notes": "Mineral, complex, less sharp than sea salt.",
    },
    # ---- HERBS ----
    "mint": {
        "origin": "Mediterranean, Middle East. Yemeni dried mint is especially intense.",
        "recommended_use": "Crush into tea, sprinkle on yogurt, salads.",
        "flavor_notes": "Cool, sharp, refreshing.",
    },
    "lavender": {
        "origin": "Mediterranean (Provence, Spain). Culinary grade ≠ cosmetic grade.",
        "recommended_use": "Infuse honey, cream, shortbread. Add to tea.",
        "flavor_notes": "Floral, sweet, herbaceous.",
    },
    "oregano": {
        "origin": "Greece, Turkey, Italy. Wild mountain oregano is strongest.",
        "recommended_use": "Pizza, salads, grilled lamb, tomato sauces.",
        "flavor_notes": "Peppery, floral, pungent.",
    },
    # ---- TEA ----
    "darjeeling": {
        "origin": "India — Darjeeling, Himalaya foothills. First flush = spring picking.",
        "recommended_use": "Brew 3 min at 90 °C. Drink without milk.",
        "flavor_notes": "Muscatel grape, floral, astringent finish.",
    },
    "assam": {
        "origin": "India — Assam, Brahmaputra valley. Malty, strong.",
        "recommended_use": "Breakfast tea. Milk and sugar welcome.",
        "flavor_notes": "Malty, bold, brisk.",
    },
    "rooibos": {
        "origin": "South Africa — Cederberg. Aspalathus linearis shrub.",
        "recommended_use": "Caffeine-free. Brew 5 min. Great with milk and honey.",
        "flavor_notes": "Honey-sweet, nutty, mild.",
    },
}


def explain_product(name, category=None, country=None):
    """Match on the most specific key found in name/country/category."""
    haystack = " ".join(filter(None, [name, category, country])).lower()
    # Prefer longest match — "ras el hanout" before "ras"
    for key in sorted(KNOWLEDGE, key=len, reverse=True):
        if key in haystack:
            v = KNOWLEDGE[key]
            return {
                "product": name,
                "origin": v["origin"],
                "recommended_use": v["recommended_use"],
                "flavor_notes": v["flavor_notes"],
            }
    return {
        "product": name,
        "origin": "Sourced from small producers — see product page for details.",
        "recommended_use": "Ask our team for tasting notes.",
        "flavor_notes": "Contact us for specifics.",
    }
