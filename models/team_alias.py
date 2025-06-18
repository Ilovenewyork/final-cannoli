from sqlalchemy import Column, Integer, String, ForeignKey
from extensions import db

class TeamAlias(db.Model):
    __tablename__ = 'team_alias'
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True)
    team_name = Column(String(100), nullable=False)
    team_id = Column(String(10), nullable=False)  # The actual team ID from prelims
    stage_id = Column(Integer, nullable=False)  # The stage this alias is for
    tournament_id = Column(Integer, ForeignKey('tournament.id', name='fk_team_alias_tournament'), nullable=False)
    placeholder = Column(String(10))  # e.g., T1, T2, etc. for playoff seeding
    
    # Relationships
    tournament = db.relationship('Tournament', back_populates='team_aliases')
    players = db.relationship('Player', back_populates='alias_rel', lazy=True, foreign_keys='Player.alias_id')
    
    def __repr__(self):
        return f'<TeamAlias {self.team_name} ({self.team_id}) for Tournament ID {self.tournament_id} (Stage {self.stage_id})>'
