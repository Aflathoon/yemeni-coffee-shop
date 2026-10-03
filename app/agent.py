"""Knowledge-based AI agent for product explanations.
Swap the _call_llm function with OpenAI/Anthropic API for true generation."""

# The agent's "brain" — structured knowledge
KNOWLEDGE = {
    "yemeni coffee": {
        "origin": "Haraz and Bani Matar regions, Yemen. Grown at 1,500–2,200m altitude.",
        "use": "Brew as pour-over or Turkish. Traditionally spiced with cardamom and ginger.",
        "flavor": "Wine-like acidity, chocolate, dried fruit, sometimes tobacco."
    },
    "arabica": {
        "origin": "Ethiopia originally, now grown worldwide. Yemeni Arabica is heirloom varietal.",
        "use": "Any brew method. Yemeni Arabica shines in espresso and pour-over.",
        "flavor": "Bright, fruity, floral with honey sweetness."
    },
    "sidr honey": {
        "origin": "Hadhramaut, Yemen. Bees feed on Sidr (jujube) tree blossoms.",
        "use": "Take a spoonful daily. Drizzle on yogurt, cheese, or pastries.",
        "flavor": "Rich, caramel, slightly medicinal. Thicker than regular honey."
    },
    "cardamom": {
        "origin": "Guatemala, India, Sri Lanka. Yemen imports and uses heavily.",
        "use": "Crush pods into coffee, tea, rice pudding. Essential for Yemeni qishr.",
        "flavor": "Eucalyptus, citrus, mint. Aromatic and cooling."
    },
    "saffron": {
        "origin": "Iran, Afghanistan, Kashmir. Hand-harvested stigmas.",
        "use": "Bloom in warm water or milk. Add to rice, tea, desserts.",
        "flavor": "Honey, hay, floral. Extremely potent—a pinch is enough."
    },
    "cinnamon": {
        "origin": "Ceylon (Sri Lanka) vs. Cassia (China/Vietnam). Ceylon is true cinnamon.",
        "use": "Stir into coffee, tea, oatmeal. Simmer in stews.",
        "flavor": "Sweet, woody, warm. Ceylon is more delicate than cassia."
    },
    "lavender": {
        "origin": "Mediterranean (France, Spain). Culinary grade is different from cosmetic.",
        "use": "Infuse honey, bake into shortbread, add to tea.",
        "flavor": "Floral, slightly sweet, herbaceous."
    },
    "mint": {
        "origin": "Mediterranean, Middle East. Yemeni mint is dried, intense.",
        "use": "Crush into tea, sprinkle on salads, mix into yogurt.",
        "flavor": "Cool, sharp, refreshing."
    },
}

def explain_product(product_name):
    """Return a structured explanation for any product."""
    key = product_name.lower()
    for k, v in KNOWLEDGE.items():
        if k in key:
            return {
                "product": product_name,
                "origin": v["origin"],
                "recommended_use": v["use"],
                "flavor_notes": v["flavor"]
            }
    return {
        "product": product_name,
        "origin": "Information coming soon.",
        "recommended_use": "Ask us in chat for details.",
        "flavor_notes": "Contact us for tasting notes."
    }

# For real LLM integration, replace with:
# def _call_llm(prompt):
#     import openai
#     return openai.ChatCompletion.create(...)
