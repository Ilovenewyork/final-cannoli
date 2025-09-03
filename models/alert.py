from datetime import datetime
from enum import Enum as PyEnum
from extensions import db
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SQLAlchemyEnum

class AlertLevel(str, PyEnum):
    TD_CALL = 'td_call'       # Regular TD call (non-emergency)
    EMERGENCY = 'emergency'   # Emergency alert (requires immediate attention)

class Alert(db.Model):
    """Model for storing TD calls and emergency alerts"""
    __tablename__ = 'alerts'
    
    id = Column(db.Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey('game.id'), nullable=False)
    room = Column(String(100), nullable=False)  # Room number/identifier
    level = Column(SQLAlchemyEnum(AlertLevel), nullable=False)  # TD call or emergency
    message = Column(String(500), nullable=True)  # Optional message
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved = Column(db.Boolean, default=False, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    
    # Relationship
    game = db.relationship('Game', back_populates='alerts')
    
    def __repr__(self):
        return f'<Alert {self.level} in {self.room} ({self.created_at})>'
    
    def to_dict(self):
        """Convert alert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'game_id': self.game_id,
            'room': self.room,
            'level': self.level.value if hasattr(self.level, 'value') else self.level,
            'message': self.message,
            'created_at': self.created_at.isoformat(),
            'resolved': self.resolved,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None
        }
