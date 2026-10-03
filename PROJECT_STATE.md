# PROJECT_STATE.md — Yemeni Coffee, Tea, Herbs, Spices & Honey Shop

> **Purpose:** Any AI session given this file + a repo snapshot should be able
> to continue work immediately. Read §1–§3 for context, §13 for roadmap.

---

## 1. Project Overview

Production-oriented Flask e-commerce site selling Yemeni specialty coffee,
tea, herbs, spices, and honey (Sidr, honeycomb, rare varietals). Includes
admin dashboard, AI-agent product explainer, social post composer, image
optimization pipeline.

- **Owner / GitHub:** Aflathoon — https://github.com/Aflathoon
- **Status:** Local dev. Not deployed. Port: 5003 (auto-picked).
- **Working dir:** ~/yemeni-coffee-shop

---

## 2. Environment

- OS: Ubuntu 26.04
- Python: 3.14
- Venv: .venv/ (source .venv/bin/activate)
- Flask: 3.1.2
- DB: SQLite at instance/shop.db
- Port: from .env → FLASK_PORT and FLASK_RUN_PORT
- Standalone: NOT behind Nginx/Apache (user has other services there).

### Other projects on this machine — DO NOT TOUCH
- zippyMesh — gunicorn on 9004
- prediction_market — gunicorn (config in its own dir)
- polyclone — gunicorn gthread on 8787

---

## 3. File Tree

yemeni-coffee-shop/
├── .env                     # secrets, FLASK_PORT, UNSPLASH_ACCESS_KEY
├── .gitignore
├── PROJECT_STATE.md
├── README.md                # (not yet written)
├── requirements.txt
├── run.py                   # entry: `python run.py`
├── find_port.py             # writes FLASK_PORT + FLASK_RUN_PORT to .env
├── create_admin.py          # idempotent seed + admin user
├── fetch_images.py          # Unsplash downloader
├── app/
│   ├── __init__.py          # create_app, blueprint reg, seeding
│   ├── models.py            # User, Product, Order, Post
│   ├── agent.py             # KNOWLEDGE dict + explain_product()
│   ├── main/
│   │   ├── __init__.py
│   │   └── routes.py        # /, /product/<id>, /api/explain/<id>
│   ├── admin/
│   │   ├── __init__.py
│   │   └── routes.py        # /admin/login, /dashboard, /post/new
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── product.html
│   │   └── admin/{login,dashboard,editor}.html
│   └── static/
│       ├── css/  (empty — Tailwind via CDN)
│       ├── js/   (empty)
│       └── images/          # populated by fetch_images.py
└── instance/
    └── shop.db              # SQLite (gitignored)

---

## 4. Cold Start

cd ~/yemeni-coffee-shop
source .venv/bin/activate
python find_port.py        # writes port to .env
python create_admin.py     # idempotent
python run.py              # serves on http://127.0.0.1:<FLASK_PORT>

Admin: admin@example.com / changeme123  (change in prod)

Do NOT rely on `flask --app run run` alone — it needs FLASK_RUN_PORT in
.env (find_port.py writes it) OR use `python run.py` which is authoritative.

---

## 5. Dependencies

Flask==3.1.2, Flask-SQLAlchemy, Flask-Login, Flask-WTF, Flask-Migrate,
Pillow, python-dotenv, requests, gunicorn.

---

## 6. Data Model (app/models.py)

- User: email (unique), password_hash, is_admin, created_at
- Product: name, category, description, price, image, stock, origin,
  recommended_use
- Order: user_id, status, total, created_at  (not yet wired to cart)
- Post: title, body (HTML), image, published, created_at

Seeding: create_app() → _seed_products() inserts 9 samples if empty.

---

## 7. AI Agent (app/agent.py)

Current: deterministic keyword match over KNOWLEDGE dict. Returns
origin / recommended_use / flavor_notes.

Upgrade path: add OPENAI_API_KEY (or Anthropic) to .env; replace body of
explain_product() with API call keeping the same response shape.

---

## 8. Admin Dashboard

Routes under /admin, wrapped by @admin_required:
- GET/POST /admin/login
- GET /admin/dashboard — stats: products, orders, users, posts, revenue
- GET/POST /admin/post/new — HTML textarea editor
- GET /admin/post/<id>/publish — marks published (social APIs stubbed)

Editor is NOT a WYSIWYG. Upgrade: TinyMCE CDN or TipTap.
Social posting: stubbed. Telegram Bot API is easiest first target.

---

## 9. Styling

- Tailwind via CDN (script tag in base.html)
- Hero gradient in base.html inline <style>
- Palette: stone/amber/cream
- Prod TODO: compile Tailwind locally, drop CDN warning.

---

## 10. Images

- Fetched via fetch_images.py from Unsplash (needs UNSPLASH_ACCESS_KEY)
- Location: app/static/images/
- Naming: <product>_<n>.jpg
- Fallback: templates use onerror → placeholder service
- TODO: optimize_images.py (JPEG→WebP, 800px max, q85)

---

## 11. Ports / Networking

- Never bind 80/443. Nginx/Apache owned by other projects.
- find_port.py scans 5003–5099, skips RESERVED + LISTEN + known others.
- Writes FLASK_PORT and FLASK_RUN_PORT.

---

## 12. Git

- Remote: https://github.com/Aflathoon/yemeni-coffee-shop.git
- Ignored: .venv, .env, instance/, app/static/images/, __pycache__
- First push pending.
- Backup strategy: commit + push at each session end.

---

## 13. TODO / NEXT (priority order)

1. Run `python fetch_images.py` (needs UNSPLASH_ACCESS_KEY).
2. optimize_images.py — Pillow JPEG→WebP; update templates to prefer WebP.
3. Cart + checkout: OrderItem model, session cart, /checkout route.
4. Customer auth: /register, /login, /account (reuse User model).
5. Real LLM in agent.py.
6. Telegram bot integration (first social channel).
7. Tailwind local build.
8. WYSIWYG editor for Post composer (TinyMCE CDN).
9. Flask-Migrate: `flask db init && flask db migrate -m init && flask db upgrade`.
10. Production: gunicorn + systemd unit; Postgres migration.
11. First `git push -u origin main`.

---

## 14. Gotchas

- `flask --app run run` ignores FLASK_PORT — use FLASK_RUN_PORT or python run.py.
- Always `mkdir -p app/main app/admin` before heredoc'ing into them.
- Every POST form must include csrf_token.
- SECRET_KEY in .env is placeholder — rotate before deploy.
- Seed admin creds: admin@example.com / changeme123.

---

## 15. Session Handoff Checklist

1. Paste this file first.
2. Paste `git log --oneline -10`.
3. Paste `pip freeze`.
4. Name the TODO item (§13) to work on.
5. If touching images, confirm UNSPLASH_ACCESS_KEY is set.
