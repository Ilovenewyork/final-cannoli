from datetime import datetime
import random
import string
import json

from extensions import db

class Tournament(db.Model):
    __tablename__ = 'tournament'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(100))
    password = db.Column(db.String(10), nullable=False)
    format_json = db.Column(db.Text, nullable=False, default='{}')  # JSON format with default value
    status = db.Column(db.String(20), default='planning')  # planning, registration, active, completed
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
    
    # Relationships - using string-based references to avoid circular imports
    games = db.relationship('Game', back_populates='tournament', lazy=True, cascade='all, delete-orphan')
    questions = db.relationship('Question', back_populates='tournament_rel', lazy=True, foreign_keys='Question.tournament_id')
    team_aliases = db.relationship('TeamAlias', back_populates='tournament', lazy=True, cascade='all, delete-orphan')

    def __init__(self, name, date, location, format_json='{}', **kwargs):
        super(Tournament, self).__init__(**kwargs)
        self.name = name
        self.date = date
        self.location = location
        self.password = self.generate_password()
        self.format_json = format_json
        
    @property
    def format(self):
        return json.loads(self.format_json)
        
    @format.setter
    def format(self, value):
        if isinstance(value, str):
            self.format_json = value
        else:
            self.format_json = json.dumps(value)

    def generate_password(self):
        # Generate a secure random password
        characters = string.ascii_letters + string.digits
        return ''.join(random.choices(characters, k=10))

    def __repr__(self):
        return f'<Tournament {self.name} ({self.date})>'
