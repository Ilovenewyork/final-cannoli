from extensions import db
from sqlalchemy import ForeignKey, Column, Integer, String, Text

class Game(db.Model):
    __tablename__ = 'game'
    __table_args__ = {'extend_existing': True}
    
    id = Column(db.Integer, primary_key=True)
    team1 = Column(String(100), nullable=False)
    team2 = Column(String(100), nullable=False)
    result = Column(Integer, nullable=False, default=-2)  # -2: not played, 1: team1 wins, 0: draw, -1: team2 wins
    tournament_id = Column(Integer, db.ForeignKey('tournament.id', name='fk_game_tournament'), nullable=False)
    round_number = Column(Integer, nullable=False)
    stage_id = Column(Integer, nullable=False)  # 1: preliminary, 2: playoff, etc.
    scorecard = Column(Text, nullable=True)
    
    # Relationships
    tournament = db.relationship('Tournament', back_populates='games')
    questions = db.relationship('Question', back_populates='game_rel', lazy=True, foreign_keys='Question.game_id')
    
    def __repr__(self):
        return f'<Game {self.team1} vs {self.team2} (Round {self.round_number})>'
