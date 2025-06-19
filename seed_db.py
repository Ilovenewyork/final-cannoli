
import sys
import os
from datetime import datetime, timedelta
from random import randint, choice
import json

# Add the current directory to the path so we can import models
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models.tournament import Tournament
from models.game import Game
from models.player import Player
from models.team_alias import TeamAlias
from models.question import Question
from models.admin import Admin

def create_sample_tournament():
    # Create a sample tournament
    tournament = Tournament(
        name="2025 National Quiz Bowl Championship",
        date=datetime.now().date() + timedelta(days=30),  # One month from now
        location="Washington, DC",
        format_json=json.dumps({
            "format": "round_robin",
            "num_teams": 8,
            "num_rounds": 7,
            "questions_per_round": 20
        })
    )
    db.session.add(tournament)
    
    # Create admin user
    admin = Admin(username="admin", password="admin123")
    db.session.add(admin)
    
    # Create sample teams and players
    team_names = [
        "DC United", "New York Jets", "Boston Celtics", "Philadelphia 76ers",
        "Chicago Bulls", "Los Angeles Lakers", "Golden State Warriors", "Miami Heat"
    ]
    
    teams = []
    for i, name in enumerate(team_names, 1):
        # Create team alias for the tournament
        team = TeamAlias(
            tournament_id=tournament.id,
            team_id=f"T{i:02d}",
            team_name=name,
            stage_id=1  # Preliminary stage
        )
        db.session.add(team)
        teams.append(team)
        
        # Create 4 players per team
        first_names = ["Alex", "Jamie", "Taylor", "Jordan", "Casey", "Riley", "Quinn"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]
        
        for j in range(1, 5):
            player = Player(
                name=f"{choice(first_names)} {choice(last_names)}",
                team_id=team.team_id,
                alias_id=team.id
            )
            db.session.add(player)
    
    # Create sample games (round-robin format)
    rounds = 7
    questions_per_round = 20
    
    for round_num in range(1, rounds + 1):
        # In a real round-robin, you'd have a proper scheduling algorithm
        # Here we'll just create some sample matchups
        for i in range(0, len(teams), 2):
            if i + 1 < len(teams):
                game = Game(
                    team1=teams[i].team_name,
                    team2=teams[i+1].team_name,
                    tournament_id=tournament.id,
                    round_number=round_num,
                    stage_id=1,  # Preliminary stage
                    result=randint(-1, 1)  # Random result: -1 (team2 wins), 0 (tie), 1 (team1 wins)
                )
                db.session.add(game)
                
                # Add sample questions for the game
                for q_num in range(1, questions_per_round + 1):
                    question = Question(
                        question_type="tossup",
                        question_text=f"Sample tossup question {q_num} for {teams[i].team_name} vs {teams[i+1].team_name}?",
                        answer=f"Answer to question {q_num}",
                        question_number=q_num,
                        round=round_num,
                        stage="preliminary",
                        tournament_id=tournament.id,
                        game_id=game.id,
                        category=choice(["History", "Science", "Literature", "Fine Arts"]),
                        subcategory=choice(["American", "European", "World", "Biology", "Chemistry"])
                    )
                    db.session.add(question)
    
    db.session.commit()
    return tournament

def main():
    app = create_app()
    with app.app_context():
        # Clear existing data
        print("Clearing existing data...")
        db.drop_all()
        db.create_all()
        
        # Create sample data
        print("Creating sample tournament...")
        tournament = create_sample_tournament()
        
        print(f"""
        Database seeded successfully!
        
        Tournament: {tournament.name}
        Date: {tournament.date}
        Location: {tournament.location}
        
        Admin credentials:
        Username: admin
        Password: admin123
        
        You can now log in to the admin panel with these credentials.
        """)

if __name__ == "__main__":
    main()
