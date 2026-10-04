from flask import render_template, request, abort
from app.blog import bp
from app import db
from app.models import Article, Product


@bp.route("/")
def index():
    category = request.args.get("category")
    tag = request.args.get("tag")
    q = Article.query.filter_by(published=True)

    if category:
        q = q.filter_by(category=category)
    if tag:
        q = q.filter(Article.tags.ilike(f"%{tag}%"))

    articles = q.order_by(Article.created_at.desc()).all()

    # Distinct categories (published only)
    rows = (Article.query
            .filter_by(published=True)
            .with_entities(Article.category)
            .distinct().all())
    categories = sorted({c for (c,) in rows if c})

    featured = (Article.query
                .filter_by(published=True, featured=True)
                .order_by(Article.created_at.desc())
                .first())

    # Shop sidebar fallback (base.html expects `featured` and `categories`)
    from app.models import Product, Product as _P
    from sqlalchemy import func as _f
    shop_featured = Product.query.filter_by(featured=True).limit(5).all()
    shop_categories_rows = (
        db.session.query(Product.category, _f.count(Product.id))
        .filter(Product.active == True)
        .group_by(Product.category).order_by(Product.category).all()
    )
    shop_categories = [{"name": c, "count": n} for c, n in shop_categories_rows]
    shop_countries_rows = (
        db.session.query(Product.origin_country, _f.count(Product.id))
        .filter(Product.active == True, Product.origin_country.isnot(None))
        .group_by(Product.origin_country).order_by(Product.origin_country).all()
    )
    shop_countries = [{"name": c, "count": n} for c, n in shop_countries_rows]

    return render_template("blog/index.html",
                           articles=articles or [], categories=categories or [],
                           featured=featured,
                           # shop sidebar for base.html
                           shop_featured=shop_featured,
                           shop_categories=shop_categories,
                           shop_countries=shop_countries,
                           active_category=category, active_tag=tag)


@bp.route("/<slug>")
def detail(slug):
    article = Article.query.filter_by(slug=slug, published=True).first_or_404()

    # Related: same category, different article
    related = (Article.query
               .filter(Article.published == True,
                       Article.category == article.category,
                       Article.id != article.id)
               .order_by(Article.created_at.desc())
               .limit(3).all())

    # Sponsored products: match on tags
    sponsored = []
    if article.tags:
        for tag in [t.strip() for t in article.tags.split(",") if t.strip()]:
            sponsored.extend(Product.query
                             .filter(Product.active == True,
                                     Product.tags.ilike(f"%{tag}%"))
                             .limit(4).all())
    sponsored = list({p.id: p for p in sponsored}.values())[:4]

    return render_template("blog/detail.html",
                           article=article, related=related or [], sponsored=sponsored or [])
