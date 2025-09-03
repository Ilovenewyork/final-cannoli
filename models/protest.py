from datetime import datetime
from extensions import db

class Protest(db.Model):
    __tablename__ = 'protest'
    
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    cycle_number = db.Column(db.Integer, nullable=False)  # The cycle number being protested
    message = db.Column(db.Text, nullable=False)  # The protest message
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending, reviewed, resolved
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('reader.id'), nullable=False)  # Who submitted the protest
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey('admin.id'), nullable=True)  # Which admin resolved it
    resolution_notes = db.Column(db.Text, nullable=True)
    
    # Relationships
    tournament = db.relationship('Tournament', backref=db.backref('protests', lazy=True))
    game = db.relationship('Game', backref=db.backref('protests', lazy=True))
    submitter = db.relationship('Reader', foreign_keys=[created_by], backref=db.backref('protests_submitted', lazy=True))
    resolver = db.relationship('Admin', foreign_keys=[resolved_by], backref=db.backref('protests_resolved', lazy=True))
    
    def __repr__(self):
        return f'<Protest for cycle {self.cycle_number} in game {self.game_id}>'
