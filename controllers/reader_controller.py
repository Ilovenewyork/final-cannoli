import json
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
import re
from sqlalchemy import and_, or_
from models.tournament import Tournament
from models.game import Game
from models.team_alias import TeamAlias
from models.player import Player
from models.team_alias import TeamAlias
from models.question import Question
from flask_login import login_required
from extensions import db

def format_reference(ref):
    """Convert reference like 'S2R1M4' to 'Stage 2 Round 1 Match 4'"""
    try:
        # Handle both full references (W(S2R1M4)) and just the code (S2R1M4)
        if ref.startswith(('W(', 'L(')) and ref.endswith(')'):
            ref = ref[2:-1]  # Remove W( or L( and )
            
        # Parse the reference
        stage = int(ref[1])
        round_num = int(ref[3])
        match_num = int(ref[5:]) if 'M' in ref else int(ref[ref.index('M')+1:])
        return f"Stage {stage} Round {round_num} Match {match_num}"
    except (IndexError, ValueError, AttributeError):
        return ref  # Return original if format is unexpected

reader_bp = Blueprint('reader', __name__, template_folder='../templates/reader')

@reader_bp.route('/', methods=['GET', 'POST'])
def select_tournament():
    if request.method == 'POST':
        tournament_id = request.form.get('tournament_id')
        password = request.form.get('password')
        tournament = Tournament.query.get(tournament_id)
        if not tournament:
            flash("Tournament not found", "danger")
            return redirect(url_for('reader.select_tournament'))
        if tournament.password != password:
            flash("Invalid tournament password", "danger")
            return redirect(url_for('reader.select_tournament'))
        return redirect(url_for('reader.tournament_games', tournament_id=tournament.id))
    tournaments = Tournament.query.all()
    return render_template('select_tournament.html', tournaments=tournaments)

@reader_bp.route('/tournament/<int:tournament_id>')
def tournament_games(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    # Get all games for this tournament
    games = Game.query.filter_by(tournament_id=tournament.id).all()
    
    # Create a dictionary to store team display names
    team_display_names = {}
    
    # Process each game to get display names
    processed_games = []
    for game in games:
        def get_team_alias(team_id, stage_id):
            if not team_id:
                return None
                
            # Debug log
            print(f"Looking up alias for team_id: {team_id}, stage_id: {stage_id}")
                
            # First try to find an exact match for team_id and stage_id
            alias = TeamAlias.query.filter(
                TeamAlias.tournament_id == tournament.id,
                TeamAlias.team_id == team_id,
                TeamAlias.stage_id == stage_id
            ).first()
            
            # Debug log result
            if alias:
                print(f"Found exact alias: {alias.team_name} (ID: {alias.id})")
            
            # If not found, try to find any previous alias for this team
            if not alias:
                print("No exact alias found, looking for any previous alias...")
                alias = TeamAlias.query.filter(
                    TeamAlias.tournament_id == tournament.id,
                    (TeamAlias.team_id == team_id) | (TeamAlias.team_name == team_id)
                ).order_by(TeamAlias.stage_id.desc()).first()
                
                if alias:
                    print(f"Found previous alias: {alias.team_name} (ID: {alias.id}) from stage {alias.stage_id}")
                else:
                    print(f"No alias found for team_id: {team_id}")
                    
            return alias
        
        # Get stage ID, defaulting to 1 if not set
        stage_id = getattr(game, 'stage_id', 1)
        # Ensure stage_id is an integer
        stage_id = int(stage_id) if stage_id is not None else 1
        
        # Debug log game info
        print(f"Processing game {game.id}: {game.team1} vs {game.team2} (Stage {stage_id})")
        
        # Get aliases for both teams
        team1_alias = get_team_alias(game.team1, stage_id) if game.team1 else None
        team2_alias = get_team_alias(game.team2, stage_id) if game.team2 else None
        
        # Function to process team name with dynamic references
        def process_team_name(team_id, team_alias):
            if not team_id:
                return 'TBD', False, None
                
            # Check if this is a dynamic reference (e.g., W(S1R1M1) or L(S1R1M1))
            if isinstance(team_id, str) and ((team_id.startswith('W(') or team_id.startswith('L(')) and team_id.endswith(')')):
                ref_type = 'Winner' if team_id.startswith('W(') else 'Loser'
                # Try to resolve the reference
                resolved_id, resolved_name, pending_info = resolve_team_reference(tournament.id, team_id)
                
                if resolved_id and resolved_name:
                    # If we have a resolved team, get its alias for display
                    alias = TeamAlias.query.filter_by(
                        tournament_id=tournament.id,
                        team_id=resolved_id
                    ).first()
                    display_name = alias.team_name if alias else resolved_name
                    return display_name, False, None
                elif pending_info:
                    # If pending, show what we're waiting for in a more readable format
                    ref_str = format_reference(team_id)
                    return f"{ref_type} of {ref_str}", True, pending_info
                
            # Default to alias or raw ID
            if team_alias and hasattr(team_alias, 'team_name'):
                return team_alias.team_name, False, None
            return team_id or 'TBD', False, None
        
        # Process both teams
        team1_name, team1_pending, team1_info = process_team_name(game.team1, team1_alias)
        team2_name, team2_pending, team2_info = process_team_name(game.team2, team2_alias)
        
        # Create a dictionary with the game data and display names
        game_data = {
            'id': game.id,
            'team1': team1_name,
            'team2': team2_name,
            'team1_pending': team1_pending,
            'team2_pending': team2_pending,
            'team1_info': team1_info,
            'team2_info': team2_info,
            'round_number': game.round_number,
            'stage_id': stage_id,
            'room': getattr(game, 'room', ''),
            'moderator': getattr(game, 'moderator', ''),
            'result': getattr(game, 'result', None),
            'scorecard': getattr(game, 'scorecard', None)
        }
        processed_games.append(game_data)
    
    # Debug: Print the first few games to verify data
    print("\n=== DEBUG: Processed Games ===")
    for i, g in enumerate(processed_games[:5]):  # Print first 5 games
        print(f"Game {i+1} - ID: {g['id']}, Result: {g.get('result')}, Team1: {g['team1']}, Team2: {g['team2']}")
    
    return render_template('tournament_games.html', 
                         tournament=tournament, 
                         games=processed_games)

def resolve_team_reference(tournament_id, team_ref, depth=0, max_depth=5):
    """
    Resolve a team reference like 'W(S2R1M1)' to an actual team ID.
    
    Args:
        tournament_id: ID of the tournament
        team_ref: The team reference to resolve (e.g., 'W(S2R1M1)')
        depth: Current recursion depth (used internally)
        max_depth: Maximum allowed recursion depth to prevent infinite loops
        
    Returns:
        tuple: (team_id, team_name, pending_info) where:
            - If resolved: (team_id, team_name, None)
            - If pending: (None, None, {'ref': team_ref, 'game': game_details, 'team1': team1_name, 'team2': team2_name})
            - If error: (None, None, None)
    """
    print(f"Resolving reference: {team_ref} (depth: {depth})")  # Debug log
    if depth > max_depth:
        print(f"Maximum recursion depth ({max_depth}) exceeded resolving reference: {team_ref}")
        return None, None, None
        
    if not team_ref or not isinstance(team_ref, str):
        return None, None, None
        
    # Check if it's a dynamic reference (W for winner or L for loser)
    is_winner_ref = team_ref.startswith('W(') and team_ref.endswith(')')
    is_loser_ref = team_ref.startswith('L(') and team_ref.endswith(')')
    
    if not (is_winner_ref or is_loser_ref):
        # Not a dynamic reference, check if it's a team ID that might need alias lookup
        if team_ref and not team_ref.startswith('T'):  # Assuming team IDs start with T
            alias = TeamAlias.query.filter_by(
                tournament_id=tournament_id,
                team_id=team_ref
            ).first()
            if alias:
                return team_ref, alias.team_name, None
        return team_ref, team_ref, None  # Return as is if not a dynamic reference
    
    try:
        # Extract the reference inside W() or L()
        ref = team_ref[2:-1]  # Remove 'W(' or 'L(' and ')'
        ref_type = team_ref[0]  # 'W' or 'L'
        
        # Parse stage and round numbers
        # Format: S{stage}R{round}M{match}
        match = re.match(r'^S(\d+)R(\d+)M(\d+)$', ref)
        if not match:
            print(f"Invalid team reference format: {team_ref}")
            return None, None, None
            
        stage_num, round_num, match_num = map(int, match.groups())
        
        # Find the referenced game using stage, round, and match numbers
        # First try to find by match number if the column exists
        ref_game = None
        try:
            # Check if match_num column exists in the Game model
            if hasattr(Game, 'match_num'):
                ref_game = Game.query.filter(
                    Game.tournament_id == tournament_id,
                    Game.stage_id == stage_num,
                    Game.round_number == round_num,
                    Game.match_num == match_num
                ).first()
            
            # If not found or no match_num column, try to get by position in the round
            if not ref_game:
                # Get all games for this stage and round
                games_in_round = Game.query.filter(
                    Game.tournament_id == tournament_id,
                    Game.stage_id == stage_num,
                    Game.round_number == round_num
                ).order_by(Game.id).all()
                
                # Use match_num as 1-based index into the games list
                if 0 < match_num <= len(games_in_round):
                    ref_game = games_in_round[match_num - 1]
                elif games_in_round:  # If only one game in round, use it
                    ref_game = games_in_round[0]
                    
                print(f"Found game {ref_game.id if ref_game else 'None'} for {team_ref} (position {match_num} of {len(games_in_round)} games in round)")
            else:
                print(f"Found game {ref_game.id} for {team_ref} by match_num")
        except Exception as e:
            print(f"Error finding game for {team_ref}: {str(e)}")
        
        if not ref_game:
            print(f"Referenced game not found: {team_ref} (S{stage_num}R{round_num}M{match_num})")
            return None, None, None
            
        print(f"Resolving {team_ref} (S{stage_num}R{round_num}M{match_num}) - Game ID: {ref_game.id}")
        print(f"  Teams: {ref_game.team1} vs {ref_game.team2}, Result: {ref_game.result}")
            
        # Get team names for the pending game
        team1_name = None
        team2_name = None
        
        # Try to get team names from aliases
        if hasattr(ref_game, 'team1') and ref_game.team1:
            alias = TeamAlias.query.filter_by(
                tournament_id=tournament_id,
                team_id=ref_game.team1
            ).first()
            team1_name = alias.team_name if alias else ref_game.team1
            
        if hasattr(ref_game, 'team2') and ref_game.team2:
            alias = TeamAlias.query.filter_by(
                tournament_id=tournament_id,
                team_id=ref_game.team2
            ).first()
            team2_name = alias.team_name if alias else ref_game.team2
        
        # Create pending info with more details about the referenced game
        game_info = {
            'ref': team_ref,
            'game': {
                'id': ref_game.id,
                'stage_id': stage_num,
                'round_number': round_num,
                'match_number': match_num,
                'team1': getattr(ref_game, 'team1', None),
                'team2': getattr(ref_game, 'team2', None),
                'result': ref_game.result
            },
            'team1': team1_name or 'TBD',
            'team2': team2_name or 'TBD',
            'formatted_ref': format_reference(team_ref)
        }
        
        if ref_game.result is None:
            print(f"Referenced game {team_ref} has no result yet")
            return None, None, game_info
            
        # Get the winning/losing team based on reference type
        if ref_game.result == 1:  # Team 1 won
            team_id = ref_game.team1 if ref_type == 'W' else ref_game.team2
        elif ref_game.result == -1:  # Team 2 won
            team_id = ref_game.team2 if ref_type == 'W' else ref_game.team1
        else:
            print(f"Referenced game {team_ref} ended in a tie")
            game_info['is_tie'] = True
            return None, None, game_info
            
        # Determine the winning team ID based on the game result and reference type
        if ref_game.result == 1:  # Team 1 won
            winner_id = ref_game.team1 if ref_type in ['W', 'T'] else ref_game.team2
        elif ref_game.result == -1:  # Team 2 won
            winner_id = ref_game.team2 if ref_type in ['W', 'T'] else ref_game.team1
        else:  # Tie or no result
            print(f"Referenced game {team_ref} ended in a tie or has no result")
            game_info['is_tie'] = True
            return None, None, game_info
            
        # Check if the winner is itself a dynamic reference
        if isinstance(winner_id, str) and (winner_id.startswith('W(') or winner_id.startswith('L(') or winner_id.startswith('T(')):
            print(f"Winner is another dynamic reference: {winner_id}, resolving recursively...")
            if depth < max_depth:
                return resolve_team_reference(tournament_id, winner_id, depth + 1, max_depth)
            else:
                print(f"Max recursion depth reached for reference: {winner_id}")
                return None, None, game_info
        
        # Get the team name from aliases
        team_alias = TeamAlias.query.filter_by(
            tournament_id=tournament_id,
            team_id=winner_id,
            stage_id=ref_game.stage_id  # Make sure to get the alias for the correct stage
        ).order_by(TeamAlias.id.desc()).first()  # Get the most recent alias if multiple exist
        
        if not team_alias:
            print(f"No alias found for team ID: {winner_id} in stage {ref_game.stage_id}")
            # If no alias, try to find by team name as a fallback
            if isinstance(winner_id, str) and (winner_id.startswith('T') or winner_id.isdigit()):
                return winner_id, f"Team {winner_id}", None
            return None, None, game_info
            
        print(f"Resolved {team_ref} -> {winner_id} ({team_alias.team_name})")
        return winner_id, team_alias.team_name, None
        
    except Exception as e:
        print(f"Error resolving team reference {team_ref}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None, None, None

@reader_bp.route('/game/<int:game_id>', methods=['GET', 'POST'])
def submit_game(game_id):
    print(f"\n=== DEBUG: Starting submit_game for game_id: {game_id} ===")
    game = Game.query.get_or_404(game_id)
    
    # Get the tournament for this game
    tournament = Tournament.query.get(game.tournament_id)
    
    if not tournament:
        flash("Tournament not found", "danger")
        return redirect(url_for('reader.select_tournament'))
        
    print(f"Found tournament: {tournament.name} (ID: {tournament.id})")
    
    # Check if game is already completed (result is not None and not -2)
    if game.result is not None and game.result != -2:
        # Verify all identifiers to ensure we have the correct game
        existing_game = Game.query.filter_by(
            id=game.id,
            tournament_id=tournament.id,
            round_number=game.round_number,
            stage_id=game.stage_id if hasattr(game, 'stage_id') else 1,
            result=game.result
        ).first()
        
        if existing_game and existing_game.result != -2:
            flash("This game has already been completed and cannot be modified.", "warning")
            return redirect(url_for('reader.tournament_games', tournament_id=tournament.id))
    
    # Get team names from the game, resolving any dynamic references
    team1_id = game.team1
    team1_display_name = game.team1
    team2_id = game.team2
    team2_display_name = game.team2
    pending_team1_info = None
    pending_team2_info = None
    
    # Resolve team 1 reference if it's dynamic
    if team1_id and str(team1_id).startswith('W('):
        resolved_id, resolved_name, pending_info = resolve_team_reference(tournament.id, team1_id)
        if resolved_id and resolved_name:
            team1_id = resolved_id
            team1_display_name = resolved_name
            print(f"Resolved team1 reference: {game.team1} -> {team1_id} ({team1_display_name})")
        elif pending_info:
            pending_team1_info = pending_info
            # Include the reference in the display name
            ref_match = re.match(r'W\((S\d+R\d+M\d+)\)', team1_id)
            ref_str = ref_match.group(1) if ref_match else team1_id
            team1_display_name = f"Winner of Game {ref_str}"
            # Store the reference for the template
            pending_team1_info['reference'] = team1_id
        else:
            team1_display_name = f"Winner of {team1_id}"
                
    # Resolve team 2 reference if it's dynamic
    if team2_id and str(team2_id).startswith('W('):
        resolved_id, resolved_name, pending_info = resolve_team_reference(tournament.id, team2_id)
        if resolved_id and resolved_name:
            team2_id = resolved_id
            team2_display_name = resolved_name
            print(f"Resolved team2 reference: {game.team2} -> {team2_id} ({team2_display_name})")
        elif pending_info:
            pending_team2_info = pending_info
            # Include the reference in the display name
            ref_match = re.match(r'W\((S\d+R\d+M\d+)\)', team2_id)
            ref_str = ref_match.group(1) if ref_match else team2_id
            team2_display_name = f"Winner of Game {ref_str}"
            # Store the reference for the template
            pending_team2_info['reference'] = team2_id
        else:
            team2_display_name = f"Winner of {team2_id}"
    
    # If not resolved, try to get team names from aliases
    if team1_display_name == team1_id and team1_id:  # Only try to resolve if display name is still the raw ID
        alias = TeamAlias.query.filter_by(
            tournament_id=tournament.id,
            team_id=team1_id
        ).first()
        if alias:
            team1_display_name = alias.team_name
            
    if team2_display_name == team2_id and team2_id:  # Only try to resolve if display name is still the raw ID
        alias = TeamAlias.query.filter_by(
            tournament_id=tournament.id,
            team_id=team2_id
        ).first()
        if alias:
            team2_display_name = alias.team_name
    
    # Debug info
    print(f"\n=== DEBUG: Looking up team aliases ===")
    print(f"Tournament ID: {tournament.id}")
    print(f"Team 1 ID: {team1_id}, Name: {team1_display_name}")
    print(f"Team 2 ID: {team2_id}, Name: {team2_display_name}")
    
    # Get team aliases using the resolved team IDs
    team1_alias = TeamAlias.query.filter_by(
        tournament_id=tournament.id,
        team_id=team1_id
    ).first() if team1_id else None
    
    team2_alias = TeamAlias.query.filter_by(
        tournament_id=tournament.id,
        team_id=team2_id
    ).first() if team2_id else None
    
    # If we couldn't find aliases by ID, try by display_name (for backward compatibility)
    if not team1_alias and team1_display_name and team1_display_name != 'Team 1':
        team1_alias = TeamAlias.query.filter_by(
            tournament_id=tournament.id,
            team_name=team1_display_name
        ).first()
    
    if not team2_alias and team2_display_name and team2_display_name != 'Team 2':
        team2_alias = TeamAlias.query.filter_by(
            tournament_id=tournament.id,
            team_name=team2_display_name
        ).first()
    
    # Debug the found aliases
    print(f"Team 1 Alias: {team1_alias.team_name if team1_alias else 'Not found'}")
    print(f"Team 2 Alias: {team2_alias.team_name if team2_alias else 'Not found'}")
    
    # Team display names should already be set from earlier resolution
    
    # Get players for each team using team_id
    from models.player import Player
    
    def get_players_for_team(team_id, team_name, team_number):
        if not team_id:
            print(f"No team_id provided for team {team_number}")
            return []
            
        print(f"\n=== DEBUG: Looking up players for team {team_number} ===")
        print(f"Team ID: {team_id}, Name: {team_name}")
        
        players = []
        
        # First, try to find players through team aliases
        aliases = TeamAlias.query.filter_by(
            tournament_id=tournament.id,
            team_id=team_id
        ).all()
        
        print(f"Found {len(aliases)} aliases for team {team_id}:")
        for alias in aliases:
            print(f"  - Alias ID: {alias.id}, Name: {alias.team_name}, Stage: {alias.stage_id}")
            
            # Get players associated with this alias
            alias_players = Player.query.filter_by(
                alias_id=alias.id
            ).all()
            
            for p in alias_players:
                print(f"    - Player: {p.name} (ID: {p.id}, Alias ID: {p.alias_id})")
                players.append(p.name)
        
        # If no players found through aliases, try direct team_id match
        if not players:
            print("No players found through aliases, trying direct team_id match...")
            direct_players = Player.query.filter_by(
                team_id=team_id
            ).all()
            
            print(f"Found {len(direct_players)} players by direct team_id match")
            for p in direct_players:
                print(f"  - {p.name} (ID: {p.id}, Team ID: {p.team_id})")
                players.append(p.name)
        
        # If still no players, try matching by team name as a last resort
        if not players and team_name and team_name != f"Team {team_number}":
            print(f"No players found by ID, trying to find by team name: {team_name}")
            
            # Find aliases with this team name in this tournament
            name_aliases = TeamAlias.query.filter(
                TeamAlias.tournament_id == tournament.id,
                TeamAlias.team_name == team_name
            ).all()
            
            for alias in name_aliases:
                alias_players = Player.query.filter_by(
                    alias_id=alias.id
                ).all()
                
                for p in alias_players:
                    print(f"  - {p.name} (ID: {p.id}, Team: {alias.team_name})")
                    players.append(p.name)
        
        return list(dict.fromkeys(players))  # Remove duplicates while preserving order
    
    # Get players for both teams
    players_team1 = get_players_for_team(team1_id, team1_display_name, 1) if team1_id else []
    players_team2 = get_players_for_team(team2_id, team2_display_name, 2) if team2_id else []
    
    print(f"\n=== Final Player Counts ===")
    print(f"Team 1 ({team1_display_name}): {len(players_team1)} players")
    print(f"Team 2 ({team2_display_name}): {len(players_team2)} players")
    
    # Team 2 players are now handled by the get_players_for_team function
    
    # Get questions and bonuses for this game
    print("\n=== DEBUG: Fetching questions ===")
    questions = Question.query.filter(
        Question.tournament_id == tournament.id,
        Question.stage == str(game.stage_id) if hasattr(game, 'stage_id') else True,
        Question.round == game.round_number,
        Question.is_bonus == False
    ).order_by(Question.question_number).all()
    
    print(f"Found {len(questions)} questions for tournament {tournament.id}, round {game.round_number}")
    for i, q in enumerate(questions[:3]):  # Print first 3 questions as sample
        print(f"  Q{i+1}: ID={q.id}, Number={q.question_number}, Text: {q.question_text[:50]}...")
    
    print("\n=== DEBUG: Fetching bonuses ===")
    bonuses = Question.query.filter(
        Question.tournament_id == tournament.id,
        Question.stage == str(game.stage_id) if hasattr(game, 'stage_id') else True,
        Question.round == game.round_number,
        Question.is_bonus == True
    ).order_by(Question.question_number).all()
    
    print(f"Found {len(bonuses)} bonus questions from DB")
    
    # Format bonuses for the frontend
    formatted_bonuses = []
    for bonus in bonuses:
        formatted_bonus = {
            'question_number': bonus.question_number,
            'question_text': bonus.question_text,  # This is the leadin
            'parts': bonus.parts or [],            # JSON list of parts
            'answers': bonus.answers or []         # JSON list of answers
        }
        formatted_bonuses.append(formatted_bonus)
    
    print(f"Formatted {len(formatted_bonuses)} bonuses for template. Sample: {formatted_bonuses[0] if formatted_bonuses else 'None'}")
    
    # For GET request, render the game view
    if request.method == 'GET':
        print("\n=== DEBUG: Processing GET request ===")
        print(f"Game ID: {game.id}, Round: {game.round_number}, Stage: {getattr(game, 'stage_id', 'N/A')}")
        
        # Initialize scorecard if it doesn't exist
        if not game.scorecard:
            print("Initializing new scorecard")
            # Create a new scorecard with 20 empty cycles
            empty_cycle = {
                'tossup': {'points': 0, 'team': None, 'player': None},
                'bonus': [0, 0, 0],
                'team1Players': [1] * len(players_team1) if players_team1 else [],  # 1 = active, 0 = inactive
                'team2Players': [1] * len(players_team2) if players_team2 else []
            }
            scorecard = [empty_cycle.copy() for _ in range(20)]
            game.scorecard = json.dumps(scorecard)
            db.session.commit()
        else:
            try:
                scorecard = json.loads(game.scorecard)
                # Convert old format to new format if needed
                if isinstance(scorecard, dict) and 'cycles' in scorecard:
                    # Already in the new format
                    pass
                else:
                    # Convert from old format to new format
                    new_scorecard = []
                    for cycle in scorecard if isinstance(scorecard, list) else []:
                        new_cycle = {
                            'tossup': {'points': 0, 'team': None, 'player': None},
                            'bonus': [0, 0, 0],
                            'team1Players': [1] * len(players_team1) if players_team1 else [],
                            'team2Players': [1] * len(players_team2) if players_team2 else []
                        }
                        # Map old format to new format if possible
                        if len(cycle) >= 4:
                            # Old format: [t1_players, t1_bonus, t2_players, t2_bonus]
                            t1_players, t1_bonus, t2_players, t2_bonus = cycle
                            # Try to determine which team got the tossup
                            if any(p > 0 for p in t1_players):
                                new_cycle['tossup'] = {
                                    'points': max(t1_players) if t1_players else 0,
                                    'team': 1,
                                    'player': players_team1[t1_players.index(max(t1_players))] if t1_players and max(t1_players) > 0 else None
                                }
                                new_cycle['bonus'] = [1 if i < t1_bonus else 0 for i in range(3)]
                            elif any(p > 0 for p in t2_players):
                                new_cycle['tossup'] = {
                                    'points': max(t2_players) if t2_players else 0,
                                    'team': 2,
                                    'player': players_team2[t2_players.index(max(t2_players))] if t2_players and max(t2_players) > 0 else None
                                }
                                new_cycle['bonus'] = [1 if i < t2_bonus else 0 for i in range(3)]
                        new_scorecard.append(new_cycle)
                    
                    # Ensure we have exactly 20 cycles
                    while len(new_scorecard) < 20:
                        new_scorecard.append({
                            'tossup': {'points': 0, 'team': None, 'player': None},
                            'bonus': [0, 0, 0],
                            'team1Players': [1] * len(players_team1) if players_team1 else [],
                            'team2Players': [1] * len(players_team2) if players_team2 else []
                        })
                    
                    scorecard = new_scorecard[:20]
                    game.scorecard = json.dumps(scorecard)
                    db.session.commit()
            except (json.JSONDecodeError, TypeError):
                # If there's an error, initialize a new scorecard
                empty_cycle = {
                    'tossup': {'points': 0, 'team': None, 'player': None},
                    'bonus': [0, 0, 0],
                    'team1Players': [1] * len(players_team1) if players_team1 else [],
                    'team2Players': [1] * len(players_team2) if players_team2 else []
                }
                scorecard = [empty_cycle.copy() for _ in range(20)]
                game.scorecard = json.dumps(scorecard)
                db.session.commit()
        
        # Convert game object to dictionary for JSON serialization
        game_dict = {
            'id': game.id,
            'team1': team1_display_name,  # Use display name
            'team2': team2_display_name,  # Use display name
            'team1_id': str(team1_id) if team1_id else None,  # Include resolved team ID
            'team2_id': str(team2_id) if team2_id else None,  # Include resolved team ID
            'original_team1': game.team1,  # Keep original reference (e.g., 'W(S2R1M1)')
            'original_team2': game.team2,  # Keep original reference
            'round_number': game.round_number,
            'stage_id': game.stage_id if hasattr(game, 'stage_id') else 1,
            'tournament_name': tournament.name,
            'is_resolved': all([
                not isinstance(team1_id, str) or not team1_id.startswith('W(') or team1_id == team1_display_name,
                not isinstance(team2_id, str) or not team2_id.startswith('W(') or team2_id == team2_display_name
            ]),  # True if all team references are resolved
            'pending_teams': {
                'team1': pending_team1_info,
                'team2': pending_team2_info
            }
        }
        
        # Prepare tournament data
        tournament_dict = {
            'id': tournament.id,
            'name': tournament.name,
            'location': getattr(tournament, 'location', ''),
            'date': getattr(tournament, 'date', '').isoformat() if hasattr(tournament, 'date') else ''
        }
        
        # Convert questions to dictionaries for JSON serialization
        print("\n=== DEBUG: Formatting questions for JSON ===")
        formatted_questions = [
            {
                'id': q.id,
                'question_text': q.question_text,
                'answer': q.answer,
                'question_number': q.question_number,
                'bonus_part': q.bonus_part if hasattr(q, 'bonus_part') else None,
                'is_bonus': q.is_bonus,
                'round': q.round,
                'stage': q.stage,
                'tournament_id': q.tournament_id
            }
            for q in questions[:20]  # Only take the first 20 questions
        ]
        
        print(f"Formatted {len(formatted_questions)} questions for JSON")
        print("Sample question:", formatted_questions[0] if formatted_questions else "No questions")
        
        return render_template(
            'reader/match_view.html',
            game=game_dict,
            tournament=tournament_dict,
            players_team1=players_team1,
            players_team2=players_team2,
            questions=formatted_questions,
            bonuses=formatted_bonuses[:20],  # Only take the first 20 bonuses
            scorecard=json.loads(game.scorecard) if game.scorecard else []
        )
    
    # Handle POST request (form submission)
    elif request.method == 'POST':
        try:
            data = request.get_json()
            
            # Validate the scorecard data
            if 'scorecard' not in data or not isinstance(data['scorecard'], list):
                return jsonify({'error': 'Invalid scorecard data'}), 400
            
            # Update the game's scorecard
            game.scorecard = json.dumps(data['scorecard'])
            
            # Calculate total scores
            team1_score = 0
            team2_score = 0
            
            for cycle in data['scorecard']:
                # Tossup points
                if cycle['tossup']['team'] == 1:
                    team1_score += cycle['tossup']['points'] or 0
                elif cycle['tossup']['team'] == 2:
                    team2_score += cycle['tossup']['points'] or 0
                
                # Bonus points (only if a team got the tossup)
                if cycle['tossup']['team']:
                    bonus_points = sum(cycle['bonus'])
                    if cycle['tossup']['team'] == 1:
                        team1_score += bonus_points
                    else:
                        team2_score += bonus_points
            
            # Update game result
            game.team1_score = team1_score
            game.team2_score = team2_score
            
            if team1_score > team2_score:
                game.result = 1  # Team 1 wins
            elif team2_score > team1_score:
                game.result = -1  # Team 2 wins
            else:
                game.result = 0  # Tie
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Game saved successfully',
                'team1_score': team1_score,
                'team2_score': team2_score
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Error saving game: {str(e)}'}), 500
    
    return jsonify({'error': 'Invalid request method'}), 405

@reader_bp.route('/game/<int:game_id>/questions')
def get_game_questions(game_id):
    game = Game.query.get_or_404(game_id)
    tournament = Tournament.query.get(game.tournament_id)
    
    if not tournament:
        return jsonify({'error': 'Tournament not found'}), 404
    
    # Get tossups (non-bonus questions) ordered by ID
    tossups = Question.query.filter(
        Question.tournament_id == tournament.id,
        Question.stage_id == game.stage_id,
        Question.round == game.round_number,
        Question.is_bonus == False
    ).order_by(Question.id).all()
    
    # Get bonuses ordered by ID
    bonuses = Question.query.filter(
        Question.tournament_id == tournament.id,
        Question.stage_id == game.stage_id,
        Question.round == game.round_number,
        Question.is_bonus == True
    ).order_by(Question.id).all()
    
    return render_template(
        'questions.html',
        questions=tossups,
        bonuses=bonuses
    )

# @reader_bp.route('/game/<int:game_id>')
# def game_questions(game_id):
#     game = Game.query.get_or_404(game_id)
#     questions = Question.query.filter_by(game_id=game_id).order_by(Question.id).all()
#     return render_template('questions.html', questions=questions)
