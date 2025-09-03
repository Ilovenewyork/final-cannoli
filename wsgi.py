from app import app, db

if __name__ == "__main__":
    app.run()

# Add this block to auto-create DB
with app.app_context():
    db.create_all()
