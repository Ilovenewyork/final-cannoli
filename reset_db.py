from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from models.tournament import db

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quizbowl.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.drop_all()   # wipe existing tables
    db.create_all() # create all tables as defined in the models
    print("Database reset successfully")
