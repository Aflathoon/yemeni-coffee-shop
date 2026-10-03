from app import create_app, db
from app.models import User

app = create_app()
with app.app_context():
    if not User.query.filter_by(email="admin@example.com").first():
        admin = User(email="admin@example.com", is_admin=True)
        admin.set_password("changeme123")
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin created: admin@example.com / changeme123")
    else:
        print("Admin already exists")
