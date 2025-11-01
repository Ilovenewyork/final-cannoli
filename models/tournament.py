from datetime import datetime
import random
import string
import json

from extensions import db
from sqlalchemy.ext.associationproxy import association_proxy

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
    room_aliases = db.relationship('RoomAlias', back_populates='tournament', lazy=True, cascade='all, delete-orphan')
    
    # Reader assignments with room numbers
    reader_assignments = db.relationship(
        'ReaderTournament',
        back_populates='tournament',
        cascade='all, delete-orphan',
        single_parent=True
    )
    
    # Association proxy to get readers
    readers = association_proxy(
        'reader_assignments', 'reader',
        creator=lambda r: ReaderTournament(reader=r)
    )

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

    def get_max_rooms(self):
        """
        Calculate the maximum number of rooms needed based on the tournament format.
        This is determined by the maximum number of pairings in any round.
        """
        print(f"\n=== DEBUG: get_max_rooms() called ===")
        print(f"Tournament ID: {self.id}, Name: {self.name}")
        print(f"Format JSON: {self.format_json}")
        
        if not self.format_json:
            print("DEBUG: No format_json found, returning 0")
            return 0
            
        max_rooms = 0
        try:
            format_data = self.format
            print(f"Parsed format data: {format_data}")
            
            # Check if we have the tournament_format object with stages
            if 'tournament_format' not in format_data:
                print("DEBUG: No 'tournament_format' key in format_data")
                return 0
                
            tournament_format = format_data['tournament_format']
            
            if 'stages' not in tournament_format:
                print("DEBUG: No 'stages' key in tournament_format")
                return 0
                
            print(f"Found {len(tournament_format['stages'])} stages")
            
            for stage_idx, stage in enumerate(tournament_format['stages'], 1):
                print(f"\nStage {stage_idx}:")
                print(f"Stage data: {stage}")
                
                if 'rounds' not in stage:
                    print(f"  No 'rounds' in stage {stage_idx}")
                    continue
                    
                print(f"  Found {len(stage['rounds'])} rounds")
                
                for round_idx, round_data in enumerate(stage['rounds'], 1):
                    print(f"  Round {round_idx}:")
                    print(f"  Round data: {round_data}")
                    
                    # Look for 'pairings' instead of 'games'
                    if 'pairings' in round_data:
                        num_games = len(round_data['pairings'])
                        print(f"    Found {num_games} pairings in this round")
                        if num_games > max_rooms:
                            max_rooms = num_games
                            print(f"    New max_rooms: {max_rooms}")
                    else:
                        print("    No 'pairings' key in round data")
                        
        except json.JSONDecodeError as e:
            print(f"ERROR: Failed to parse format_json: {e}")
            return 0
        except Exception as e:
            print(f"ERROR in get_max_rooms: {str(e)}")
            import traceback
            traceback.print_exc()
            return 0
            
        print(f"\nFinal max_rooms: {max_rooms}")
        print("=== END DEBUG ===\n")
        return max_rooms
    
    def get_readers_by_room(self, room_number):
        """Get all readers assigned to a specific room number in this tournament"""
        return [ra.reader for ra in self.reader_assignments if ra.room_number == room_number]
    
    def get_reader_room(self, reader_id):
        """Get the room number for a specific reader in this tournament"""
        for assignment in self.reader_assignments:
            if assignment.reader_id == reader_id:
                return assignment.room_number
        return None
    
    def __repr__(self):
        return f'<Tournament {self.name} ({self.date})>'
