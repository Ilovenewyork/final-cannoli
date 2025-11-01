from sqlalchemy import Column, Integer, String, ForeignKey
from extensions import db

class RoomAlias(db.Model):
    __tablename__ = 'room_alias'
    
    id = Column(Integer, primary_key=True)
    room_name = Column(String(100), nullable=False)
    room_number = Column(Integer, nullable=False)  # The actual room number
    tournament_id = Column(Integer, ForeignKey('tournament.id', name='fk_room_alias_tournament'), nullable=False)
    
    # Relationships
    tournament = db.relationship('Tournament', back_populates='room_aliases')
    
    def __repr__(self):
        return f'<RoomAlias {self.room_name} (Room {self.room_number}) for Tournament ID {self.tournament_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'room_name': self.room_name,
            'room_number': self.room_number,
            'tournament_id': self.tournament_id
        }
