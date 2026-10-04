from flask import render_template, request, abort
from app.blog import bp
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

    return render_template("blog/index.html",
                           articles=articles, categories=categories,
                           featured=featured,
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
                           article=article, related=related, sponsored=sponsored)
