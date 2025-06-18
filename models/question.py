from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey
from extensions import db

class Question(db.Model):
    __tablename__ = 'question'
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True)
    question_type = Column(String(10), nullable=False)  # 'tossup' or 'bonus'
    question_text = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    question_number = Column(Integer, nullable=False)
    round = Column(Integer, nullable=False)
    stage = Column(String(50), nullable=False)
    tournament_id = Column(Integer, ForeignKey('tournament.id', name='fk_question_tournament'), nullable=False)
    game_id = Column(Integer, ForeignKey('game.id', name='fk_question_game'))
    order = Column(Integer, nullable=False)
    
    # Bonus-specific fields
    is_bonus = Column(db.Boolean, default=False, nullable=False)
    bonus_part = Column(Integer)  # 1, 2, or 3 for bonus parts, null for tossups
    parts = Column(JSON)  # For bonuses: [part1, part2, part3]
    answers = Column(JSON)  # For bonuses: [answer1, answer2, answer3]
    
    # Category information
    category = Column(String(100))
    subcategory = Column(String(100))
    alternate_subcategory = Column(String(100))
    
    # Relationships
    tournament_rel = db.relationship('Tournament', back_populates='questions', foreign_keys=[tournament_id])
    game_rel = db.relationship('Game', back_populates='questions', foreign_keys=[game_id])
