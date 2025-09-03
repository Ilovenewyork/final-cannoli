from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from sqlalchemy.ext.associationproxy import association_proxy
from extensions import db

class ReaderTournament(db.Model):
    __tablename__ = 'reader_tournament'
    
    reader_id = db.Column(db.Integer, db.ForeignKey('reader.id'), primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), primary_key=True)
    room_number = db.Column(db.Integer, nullable=False)
    
    # Relationships
    reader = db.relationship('Reader', back_populates='tournament_assignments')
    tournament = db.relationship('Tournament', back_populates='reader_assignments')
    
    def __repr__(self):
        return f'<ReaderTournament reader_id={self.reader_id} tournament_id={self.tournament_id} room={self.room_number}>'

class Reader(UserMixin, db.Model):
    __tablename__ = 'reader'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    hashed_password = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    
    # Relationship with ReaderTournament
    tournament_assignments = db.relationship(
        'ReaderTournament',
        back_populates='reader',
        cascade='all, delete-orphan',
        single_parent=True
    )
    
    # Association proxy to get assigned tournaments
    assigned_tournaments = association_proxy(
        'tournament_assignments', 'tournament',
        creator=lambda t: ReaderTournament(tournament=t)
    )
    
    def set_password(self, password):
        self.hashed_password = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.hashed_password, password)
    
    def update_last_login(self):
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    def __repr__(self):
        return f'<Reader {self.email}>'
