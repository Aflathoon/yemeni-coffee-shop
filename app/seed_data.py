"""Global catalog seed data. Yemeni coffee & honey flagship; spices worldwide."""

PRODUCTS = [
    # ===== YEMENI COFFEE (flagship) =====
    {"name": "Yemeni Mokha Haraz", "category": "coffee", "subcategory": "single-origin",
     "origin_country": "Yemen", "origin_region": "Haraz Mountains",
     "short_desc": "Legendary highland Arabica — wine, chocolate, dried fruit.",
     "description": "Grown at 1,800–2,200 m in the Haraz range. Heirloom varietals, sun-dried on rooftops. Notes of red wine, dark chocolate, dried figs, tobacco leaf. Unwashed, wild, unmistakable.",
     "price": 32.00, "weight_grams": 250, "image": "yemeni_mokha_haraz.jpg", "featured": True},

    {"name": "Yemeni Bani Matar", "category": "coffee", "subcategory": "single-origin",
     "origin_country": "Yemen", "origin_region": "Bani Matar",
     "short_desc": "Small-lot heirloom — cardamom, honey, stone fruit.",
     "description": "From smallholder terraces west of Sana'a. Fermented in traditional clay. Expect cardamom, wildflower honey, apricot, a long earthy finish.",
     "price": 34.00, "weight_grams": 250, "image": "yemeni_bani_matar.jpg", "featured": True},

    {"name": "Yemeni Ismaili", "category": "coffee", "subcategory": "single-origin",
     "origin_country": "Yemen", "origin_region": "Ismaili",
     "short_desc": "Bright, floral, tea-like — rare micro-lot.",
     "description": "Delicate, floral, jasmine and bergamot over stone fruit. Roasted light to preserve terroir.",
     "price": 38.00, "weight_grams": 250, "image": "yemeni_ismaili.jpg", "featured": True},

    # ===== BRAZILIAN / GLOBAL COFFEE =====
    {"name": "Brazil Cerrado Yellow Bourbon", "category": "coffee", "subcategory": "single-origin",
     "origin_country": "Brazil", "origin_region": "Cerrado Mineiro",
     "short_desc": "Nutty, chocolate, low-acid — espresso workhorse.",
     "description": "Pulped-natural Yellow Bourbon from Cerrado Mineiro. Peanut brittle, milk chocolate, brown sugar. Superb as espresso or with milk.",
     "price": 18.00, "weight_grams": 250, "image": "brazil_cerrado.jpg"},

    {"name": "Brazil Santos 17/18", "category": "coffee", "subcategory": "single-origin",
     "origin_country": "Brazil", "origin_region": "Santos",
     "short_desc": "Classic smooth Brazil — sweet, mild, versatile.",
     "description": "The classic. Cocoa, roasted hazelnut, mellow body. Great base for blends or drip.",
     "price": 15.00, "weight_grams": 500, "image": "brazil_santos.jpg"},

    {"name": "Ethiopia Yirgacheffe", "category": "coffee", "subcategory": "single-origin",
     "origin_country": "Ethiopia", "origin_region": "Yirgacheffe",
     "short_desc": "Floral, citrus, tea-like — the birthplace of coffee.",
     "description": "Washed heirloom from Yirgacheffe. Jasmine, lemon, bergamot. Brew as pour-over.",
     "price": 22.00, "weight_grams": 250, "image": "ethiopia_yirgacheffe.jpg"},

    # ===== YEMENI HONEY (flagship) =====
    {"name": "Yemeni Sidr Honey — Hadhramaut", "category": "honey", "subcategory": "raw",
     "origin_country": "Yemen", "origin_region": "Hadhramaut",
     "short_desc": "World's most prized honey — thick, caramel, medicinal.",
     "description": "From bees foraging on Sidr (jujube) blossoms in Hadhramaut. Unfiltered, unpasteurized. Caramel, butterscotch, faint menthol. Thicker than any supermarket honey.",
     "price": 120.00, "weight_grams": 500, "image": "yemeni_sidr_honey.jpg", "featured": True},

    {"name": "Yemeni Sumar Honey", "category": "honey", "subcategory": "raw",
     "origin_country": "Yemen", "origin_region": "Sana'a Highlands",
     "short_desc": "Acacia-family honey — light, floral, delicate.",
     "description": "From Sumar (acacia) blossoms. Pale gold, floral, mildly sweet with a clean finish.",
     "price": 65.00, "weight_grams": 500, "image": "yemeni_sumar_honey.jpg"},

    {"name": "Yemeni Honeycomb", "category": "honey", "subcategory": "comb",
     "origin_country": "Yemen", "origin_region": "Hadhramaut",
     "short_desc": "Raw comb — chew the wax, taste the terroir.",
     "description": "Whole comb, cut straight from the hive. Serve on a cheese board.",
     "price": 45.00, "weight_grams": 400, "image": "yemeni_honeycomb.jpg"},

    {"name": "Manuka Honey MGO 850+", "category": "honey", "subcategory": "raw",
     "origin_country": "New Zealand", "origin_region": "Northland",
     "short_desc": "Antibacterial powerhouse — medicinal grade.",
     "description": "Certified MGO 850+. Dark, earthy, mineral. Take by the spoonful.",
     "price": 95.00, "weight_grams": 500, "image": "manuka_honey.jpg"},

    {"name": "Wildflower Honey — Provence", "category": "honey", "subcategory": "raw",
     "origin_country": "France", "origin_region": "Provence",
     "short_desc": "Lavender-tinged wildflower — soft, aromatic.",
     "description": "Multi-floral from Provence. Lavender, thyme, rosemary notes.",
     "price": 28.00, "weight_grams": 500, "image": "provence_honey.jpg"},

    # ===== INDIAN SPICES =====
    {"name": "Kashmiri Saffron", "category": "spices", "subcategory": "threads",
     "origin_country": "India", "origin_region": "Kashmir (Pampore)",
     "short_desc": "Deep red threads — honey, hay, floral. A pinch transforms a dish.",
     "description": "Hand-harvested stigmas from Crocus sativus. Bloom in warm milk or water before use. Essential for biryani, kheer, kahwa.",
     "price": 24.00, "weight_grams": 2, "image": "kashmiri_saffron.jpg", "featured": True},

    {"name": "Malabar Black Pepper", "category": "spices", "subcategory": "whole",
     "origin_country": "India", "origin_region": "Kerala (Malabar Coast)",
     "short_desc": "The king of spice — sharp, citrusy, complex.",
     "description": "Vine-ripened, sun-dried Tellicherry-grade peppercorns. Crack fresh over everything.",
     "price": 12.00, "weight_grams": 200, "image": "malabar_pepper.jpg"},

    {"name": "Alleppey Green Cardamom", "category": "spices", "subcategory": "whole",
     "origin_country": "India", "origin_region": "Kerala (Alleppey)",
     "short_desc": "Bold, eucalyptus, mint. Essential for chai and Yemeni coffee.",
     "description": "Bold 8mm pods. Crush into coffee, tea, rice pudding. The aromatic backbone of gahwa.",
     "price": 18.00, "weight_grams": 100, "image": "alleppey_cardamom.jpg", "featured": True},

    {"name": "Ceylon Cinnamon Sticks (True)", "category": "spices", "subcategory": "whole",
     "origin_country": "Sri Lanka", "origin_region": "Ceylon",
     "short_desc": "Delicate, sweet, floral — NOT cassia.",
     "description": "True Ceylon cinnamon. Fragile quills, soft sweetness. Different species entirely from cassia.",
     "price": 14.00, "weight_grams": 100, "image": "ceylon_cinnamon.jpg"},

    {"name": "Star Anise", "category": "spices", "subcategory": "whole",
     "origin_country": "Vietnam", "origin_region": "Lang Son",
     "short_desc": "Licorice, sweet, warming — pho and five-spice essential.",
     "description": "Whole stars, high oil content. Drop into broths, braises, chai.",
     "price": 9.00, "weight_grams": 100, "image": "star_anise.jpg"},

    {"name": "Cloves — Zanzibar", "category": "spices", "subcategory": "whole",
     "origin_country": "Tanzania", "origin_region": "Zanzibar",
     "short_desc": "Intense, numbing, sweet. Use sparingly.",
     "description": "Hand-picked flower buds. Push into an orange for mulled wine, or into a ham.",
     "price": 11.00, "weight_grams": 100, "image": "zanzibar_cloves.jpg"},

    {"name": "Turmeric — Lakadong", "category": "spices", "subcategory": "ground",
     "origin_country": "India", "origin_region": "Meghalaya",
     "short_desc": "Highest curcumin — golden, earthy, bright.",
     "description": "Lakadong turmeric, 7–9% curcumin (most is 2–3%). Deep gold. For golden milk, curries, rice.",
     "price": 13.00, "weight_grams": 200, "image": "lakadong_turmeric.jpg"},

    {"name": "Cumin — Rajasthan", "category": "spices", "subcategory": "whole",
     "origin_country": "India", "origin_region": "Rajasthan",
     "short_desc": "Warm, earthy, essential. Toast before grinding.",
     "description": "Whole cumin seeds. Toast in a dry pan till fragrant, then grind.",
     "price": 8.00, "weight_grams": 200, "image": "rajasthan_cumin.jpg"},

    {"name": "Coriander Seed", "category": "spices", "subcategory": "whole",
     "origin_country": "India", "origin_region": "Rajasthan",
     "short_desc": "Citrusy, floral — pairs with cumin everywhere.",
     "description": "Whole coriander. Toast and grind for garam masala base.",
     "price": 7.00, "weight_grams": 200, "image": "coriander_seed.jpg"},

    # ===== PAKISTANI SPICES =====
    {"name": "Himalayan Pink Salt", "category": "spices", "subcategory": "mineral",
     "origin_country": "Pakistan", "origin_region": "Khewra Mine",
     "short_desc": "Mineral, complex — finish salt.",
     "description": "Hand-mined from Khewra. Coarse grind — finish grilled meats, salads, chocolate.",
     "price": 10.00, "weight_grams": 500, "image": "himalayan_pink_salt.jpg", "featured": True},

    {"name": "Kashmiri Chili Powder", "category": "spices", "subcategory": "ground",
     "origin_country": "Pakistan", "origin_region": "Kashmir border",
     "short_desc": "Deep red color, mild heat — the tandoori trick.",
     "description": "Vibrant red, low Scoville. Gives color without burning. For tandoori, butter chicken, rogan josh.",
     "price": 11.00, "weight_grams": 200, "image": "kashmiri_chili.jpg"},

    {"name": "Ajwain (Carom Seed)", "category": "spices", "subcategory": "whole",
     "origin_country": "Pakistan", "origin_region": "Punjab",
     "short_desc": "Thyme-like, pungent — for breads and legumes.",
     "description": "Sharp, thymol-rich. Sprinkle on naan, temper lentils.",
     "price": 9.00, "weight_grams": 100, "image": "ajwain.jpg"},

    {"name": "Fenugreek Seed (Methi)", "category": "spices", "subcategory": "whole",
     "origin_country": "Pakistan", "origin_region": "Punjab",
     "short_desc": "Maple-sweet, bitter edge — curry essential.",
     "description": "Whole seeds, soak or dry-toast before use. Maple aroma when toasted.",
     "price": 7.00, "weight_grams": 200, "image": "fenugreek.jpg"},

    {"name": "Black Cardamom", "category": "spices", "subcategory": "whole",
     "origin_country": "Pakistan", "origin_region": "Northern Areas",
     "short_desc": "Smoky, camphor, resinous — for braises and rice.",
     "description": "Smoke-dried pods. Use whole in biryani, nihari, slow braises. Distinct from green cardamom.",
     "price": 16.00, "weight_grams": 100, "image": "black_cardamom.jpg"},

    # ===== MIDDLE EASTERN SPICES =====
    {"name": "Za'atar Blend", "category": "spices", "subcategory": "blend",
     "origin_country": "Jordan", "origin_region": "Levant",
     "short_desc": "Thyme, sesame, sumac — the Levantine table staple.",
     "description": "Wild thyme, toasted sesame, sumac, salt. Mix with olive oil for bread dip.",
     "price": 12.00, "weight_grams": 150, "image": "zaatar.jpg", "featured": True},

    {"name": "Sumac", "category": "spices", "subcategory": "ground",
     "origin_country": "Turkey", "origin_region": "Anatolia",
     "short_desc": "Tangy, lemony, deep red — finish salads and grilled meats.",
     "description": "Dried, ground sumac berries. Bright tartness. Sprinkle on fattoush, kebabs.",
     "price": 10.00, "weight_grams": 150, "image": "sumac.jpg"},

    {"name": "Ras el Hanout", "category": "spices", "subcategory": "blend",
     "origin_country": "Morocco", "origin_region": "Marrakech",
     "short_desc": "20+ spice Moroccan blend — warm, floral, complex.",
     "description": "Rose petal, cardamom, clove, cinnamon, nutmeg, mace, and more. Tagines, lamb, couscous.",
     "price": 15.00, "weight_grams": 150, "image": "ras_el_hanout.jpg"},

    {"name": "Baharat", "category": "spices", "subcategory": "blend",
     "origin_country": "Lebanon", "origin_region": "Levant",
     "short_desc": "Allspice-forward Gulf spice mix.",
     "description": "Allspice, black pepper, cinnamon, clove, nutmeg. Essential for kibbeh, lamb.",
     "price": 13.00, "weight_grams": 150, "image": "baharat.jpg"},

    # ===== ASIAN SPICES =====
    {"name": "Sichuan Peppercorn", "category": "spices", "subcategory": "whole",
     "origin_country": "China", "origin_region": "Sichuan",
     "short_desc": "Numbing, citrus, tingle — ma la essential.",
     "description": "Not a pepper — a citrus rind. Creates the numbing ma la sensation. Toast and grind for mapo tofu.",
     "price": 14.00, "weight_grams": 100, "image": "sichuan_peppercorn.jpg"},

    {"name": "Galangal", "category": "spices", "subcategory": "whole",
     "origin_country": "Thailand", "origin_region": "Chiang Mai",
     "short_desc": "Piney, sharp ginger cousin — Thai curry base.",
     "description": "Dried slices. Sharper and more pine-resin than ginger. Tom kha, green curry.",
     "price": 10.00, "weight_grams": 100, "image": "galangal.jpg"},

    {"name": "Lemongrass", "category": "herbs", "subcategory": "dried",
     "origin_country": "Thailand", "origin_region": "Isan",
     "short_desc": "Bright citrus — teas, curries, broths.",
     "description": "Dried stalks, cut. Bruise before use to release oils.",
     "price": 8.00, "weight_grams": 100, "image": "lemongrass.jpg"},

    {"name": "Kaffir Lime Leaves", "category": "herbs", "subcategory": "dried",
     "origin_country": "Thailand", "origin_region": "South",
     "short_desc": "Intense lime aroma — Thai curry signature.",
     "description": "Dried leaves. Tear, don't chop. Remove before serving.",
     "price": 9.00, "weight_grams": 50, "image": "kaffir_lime.jpg"},

    # ===== GLOBAL HERBS =====
    {"name": "Dried Mint — Yemeni", "category": "herbs", "subcategory": "dried",
     "origin_country": "Yemen", "origin_region": "Highlands",
     "short_desc": "Intense dried mint — crush into tea and yogurt.",
     "description": "Sun-dried highland mint. Sharper than fresh. Essential for Yemeni tea.",
     "price": 9.00, "weight_grams": 80, "image": "yemeni_mint.jpg"},

    {"name": "Oregano — Greek", "category": "herbs", "subcategory": "dried",
     "origin_country": "Greece", "origin_region": "Mount Olympus",
     "short_desc": "Peppery, floral — pizza, salads, lamb.",
     "description": "Wild Greek oregano, high in thymol. Different animal from supermarket oregano.",
     "price": 10.00, "weight_grams": 80, "image": "greek_oregano.jpg"},

    {"name": "Culinary Lavender", "category": "herbs", "subcategory": "dried",
     "origin_country": "France", "origin_region": "Provence",
     "short_desc": "Floral, sweet — honey, shortbread, tea.",
     "description": "Culinary-grade lavender buds. Infuse in honey or cream.",
     "price": 12.00, "weight_grams": 50, "image": "provence_lavender.jpg"},

    {"name": "Herbes de Provence", "category": "herbs", "subcategory": "blend",
     "origin_country": "France", "origin_region": "Provence",
     "short_desc": "Thyme, savory, rosemary, marjoram, lavender.",
     "description": "Classic Southern French blend. Rub on chicken, roast vegetables.",
     "price": 11.00, "weight_grams": 100, "image": "herbes_provence.jpg"},

    {"name": "Rooibos", "category": "tea", "subcategory": "herbal",
     "origin_country": "South Africa", "origin_region": "Cederberg",
     "short_desc": "Caffeine-free, honey-sweet, reddish brew.",
     "description": "Fermented rooibos. Naturally sweet, no caffeine. Great with milk and honey.",
     "price": 12.00, "weight_grams": 200, "image": "rooibos.jpg"},

    {"name": "Darjeeling First Flush", "category": "tea", "subcategory": "black",
     "origin_country": "India", "origin_region": "Darjeeling",
     "short_desc": "Muscatel, floral — the champagne of teas.",
     "description": "First-flush spring leaves. Delicate, muscatel grape, astringent finish.",
     "price": 25.00, "weight_grams": 100, "image": "darjeeling.jpg"},

    {"name": "Assam Black", "category": "tea", "subcategory": "black",
     "origin_country": "India", "origin_region": "Assam",
     "short_desc": "Malty, bold, breakfast-grade.",
     "description": "Full-bodied, brisk Assam. Perfect with milk. English breakfast backbone.",
     "price": 14.00, "weight_grams": 200, "image": "assam.jpg"},

    {"name": "Ceylon Black", "category": "tea", "subcategory": "black",
     "origin_country": "Sri Lanka", "origin_region": "Nuwara Eliya",
     "short_desc": "Crisp, bright, citrusy.",
     "description": "High-grown Ceylon. Crisp and bright. Beautiful iced.",
     "price": 13.00, "weight_grams": 200, "image": "ceylon_tea.jpg"},
]
