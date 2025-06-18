from sqlalchemy import Column, Integer, String, ForeignKey, or_
from extensions import db
from sqlalchemy.orm import object_session

class Player(db.Model):
    __tablename__ = 'player'
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    team_id = Column(String(10), nullable=False)  # The team ID from prelims
    alias_id = Column(Integer, ForeignKey('team_alias.id', name='fk_player_alias'), nullable=True)  # Current stage alias
    
    # Relationships
    alias_rel = db.relationship('TeamAlias', back_populates='players', foreign_keys=[alias_id])
    
    def get_team_name(self, stage_id=None):
        """Get the team name for a specific stage"""
        if not stage_id and self.alias_rel:
            return self.alias_rel.team_name
            
        from models.team_alias import TeamAlias
        alias = TeamAlias.query.filter_by(
            tournament_id=self.alias_rel.tournament_id if self.alias_rel else None,
            team_id=self.team_id,
            stage_id=stage_id if stage_id else (self.alias_rel.stage_id if self.alias_rel else None)
        ).first()
        
        return alias.team_name if alias else f"Team {self.team_id}"
    
    @classmethod
    def get_players_for_team(cls, team_id, tournament_id):
        """Get all players for a team across all stages"""
        return cls.query.filter_by(team_id=team_id).all()
    
    def __repr__(self):
        return f'<Player {self.name} (Team: {self.team_id}, Alias ID: {self.alias_id})>'
