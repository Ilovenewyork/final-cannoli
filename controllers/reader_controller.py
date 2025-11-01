import json
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, validators
import re
from sqlalchemy import and_, or_
from models.tournament import Tournament
from models.game import Game
from models.team_alias import TeamAlias
from models.player import Player
from models.question import Question
from models.reader import Reader
from extensions import db, login_manager

reader_bp = Blueprint('reader', __name__, template_folder='../templates/reader')

@login_manager.user_loader
def load_reader(reader_id):
    return Reader.query.get(int(reader_id))

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

class RegistrationForm(FlaskForm):
    email = StringField('Email', [
        validators.DataRequired(),
        validators.Email(),
        validators.Length(min=6, max=120)
    ])
    password = PasswordField('Password', [
        validators.DataRequired(),
        validators.Length(min=8, message='Password must be at least 8 characters long')
    ])
    confirm_password = PasswordField('Confirm Password', [
        validators.EqualTo('password', message='Passwords must match')
    ])
    submit = SubmitField('Register')


class LoginForm(FlaskForm):
    email = StringField('Email', [
        validators.DataRequired(),
        validators.Email()
    ])
    password = PasswordField('Password', [
        validators.DataRequired()
    ])
    submit = SubmitField('Login')

@reader_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('reader.dashboard'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        
        # Check if email already exists
        if Reader.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return render_template('reader/register.html', form=form)
            
        # Create new reader
        reader = Reader(email=email)
        reader.set_password(password)
        
        db.session.add(reader)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('reader.login'))
        
    return render_template('reader/register.html', form=form)

@reader_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('reader.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        
        reader = Reader.query.filter_by(email=email).first()
        
        if reader and reader.check_password(password):
            login_user(reader)
            reader.update_last_login()
            next_page = request.args.get('next')
            return redirect(next_page or url_for('reader.dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('reader/login.html', form=form)

@reader_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('reader.login'))

@reader_bp.route('/dashboard')
@login_required
def dashboard():
    # Get tournaments assigned to the current reader
    # No need to call .all() on an association proxy, it's already a list-like object
    tournaments = current_user.assigned_tournaments
    return render_template('reader/dashboard.html', tournaments=tournaments)

@reader_bp.route('/tournament/<int:tournament_id>')
@login_required
def view_tournament(tournament_id):
    # Redirect to the tournament_games endpoint which handles room assignments
    return redirect(url_for('reader.tournament_games', tournament_id=tournament_id))

@reader_bp.route('/tournament/<int:tournament_id>/games')
@login_required
def tournament_games(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    
    # Verify reader has access to this tournament and get their room assignment
    assignment = next(
        (ra for ra in tournament.reader_assignments if ra.reader_id == current_user.id),
        None
    )
    
    if not assignment or not assignment.room_number:
        flash('You are not assigned to a room in this tournament', 'danger')
        return redirect(url_for('reader.dashboard'))
    
    room_number = assignment.room_number
    
    # Get all games for this tournament
    all_games = Game.query.filter_by(tournament_id=tournament.id).order_by(
        Game.stage_id, 
        Game.round_number,
        Game.id
    ).all()
    
    # Filter games for the reader's room
    # We'll assume games are assigned to rooms in a round-robin fashion based on their position in the round
    games = []
    games_by_round = {}
    
    # First, group games by stage and round
    for game in all_games:
        key = (game.stage_id or 1, game.round_number or 1)
        if key not in games_by_round:
            games_by_round[key] = []
        games_by_round[key].append(game)
    
    # Then, for each round, assign games to rooms
    for round_games in games_by_round.values():
        # Sort games by ID for consistent ordering
        round_games.sort(key=lambda g: g.id)
        
        # Assign games to rooms in round-robin fashion
        for i, game in enumerate(round_games, 1):
            if i == room_number:
                game.room_number = room_number  # Add room number to game object for display
                games.append(game)
    
    # Sort the final games list by stage, round, and game ID
    games.sort(key=lambda g: ((g.stage_id or 1), (g.round_number or 1), g.id))
    
    # Process each game to get display names
    for game in games:
        # Get team display names with aliases
        team1_name = game.team1
        team2_name = game.team2
        
        # Helper function to get team display name with alias
        def get_team_display(team_name, stage_id):
            if not team_name:
                return "TBD"
                
            # Try to find an alias for this team in the tournament
            # First try to find a team alias by name in the current stage
            alias = TeamAlias.query.filter(
                TeamAlias.team_name == team_name,
                TeamAlias.tournament_id == tournament.id,
                TeamAlias.stage_id == stage_id
            ).first()
            
            # If no exact match, try to find a general alias (stage_id is None)
            if not alias:
                alias = TeamAlias.query.filter(
                    TeamAlias.team_name == team_name,
                    TeamAlias.tournament_id == tournament.id,
                    TeamAlias.stage_id == None
                ).first()
            
            # If we found an alias, use it, otherwise use the team name as is
            return alias.team_name if alias else team_name
        
        # Set display names for the template
        game.team1_display = get_team_display(team1_name, game.stage_id)
        game.team2_display = get_team_display(team2_name, game.stage_id)
        
        # Add stage and round information
        game.stage_name = f"Stage {game.stage_id}" if game.stage_id else "Prelims"
        game.round_name = f"Round {game.round_number}" if game.round_number else "Unknown Round"
    
    # Import the room utility function
    from utils.room_utils import get_room_display_name
    
    # Get room display name with fallback to room number
    room_display_name = get_room_display_name(tournament.id, room_number)
    
    # If no games found for this room, show a message
    if not games:
        flash(f'No games found for {room_display_name}. Please check back later.', 'info')
        return render_template('reader/tournament_games.html', 
                             tournament=tournament, 
                             games=games,
                             room_number=room_number,
                             room_display_name=room_display_name,
                             get_room_display_name=get_room_display_name)
    
    return render_template('reader/tournament_games.html', 
                         tournament=tournament, 
                         games=games,
                         room_number=room_number,
                         room_display_name=room_display_name,
                         get_room_display_name=get_room_display_name)

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
                players.append({'id': p.id, 'name': p.name})
        
        # If no players found through aliases, try direct team_id match
        if not players:
            print("No players found through aliases, trying direct team_id match...")
            direct_players = Player.query.filter_by(
                team_id=team_id
            ).all()
            
            print(f"Found {len(direct_players)} players by direct team_id match")
            for p in direct_players:
                print(f"  - {p.name} (ID: {p.id}, Team ID: {p.team_id})")
                players.append({'id': p.id, 'name': p.name})
        
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
                    players.append({'id': p.id, 'name': p.name})
        
        # Convert list of names to list of player objects with unique IDs
        unique_players = []
        seen_ids = set()
        
        for player in players:
            if isinstance(player, dict):
                if player['id'] not in seen_ids:
                    seen_ids.add(player['id'])
                    unique_players.append(player)
            else:
                # For backward compatibility with string player names
                player_id = hash(player)  # Generate a simple hash for the ID
                if player_id not in seen_ids:
                    seen_ids.add(player_id)
                    unique_players.append({'id': player_id, 'name': player})
        
        return unique_players
    
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
            'tournament_id': tournament.id,  # Add tournament_id for use in templates
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
            scorecard=json.loads(game.scorecard) if game.scorecard else [],
            team1_display_name=team1_display_name,
            team2_display_name=team2_display_name,
            pending_team1_info=pending_team1_info,
            pending_team2_info=pending_team2_info
        )
    
    # Handle POST request (form submission)
    elif request.method == 'POST':
        try:
            # Ensure the request has JSON data
            if not request.is_json:
                return jsonify({'error': 'Request must be JSON'}), 400
                
            data = request.get_json(silent=True)
            if not data:
                return jsonify({'error': 'Invalid JSON data'}), 400
            
            print(f"Received data: {data}")  # Debug log
            
            # Validate the scorecard data
            if 'scorecard' not in data or not isinstance(data['scorecard'], list):
                print(f"Invalid scorecard data: {data.get('scorecard')}")  # Debug log
                return jsonify({'error': 'Invalid scorecard data'}), 400
            
            # Update the game's scorecard with the raw data
            game.scorecard = json.dumps(data['scorecard'])
            
            # Calculate total scores
            team1_score = 0
            team2_score = 0
            
            # Handle the new scorecard format
            for cycle in data['scorecard']:
                if not isinstance(cycle, dict):
                    continue
                
                # Calculate team scores from player points
                if 'team1' in cycle and isinstance(cycle['team1'], dict):
                    team1_score += sum(int(points) for points in cycle['team1'].values() if str(points).lstrip('-').isdigit())
                
                if 'team2' in cycle and isinstance(cycle['team2'], dict):
                    team2_score += sum(int(points) for points in cycle['team2'].values() if str(points).lstrip('-').isdigit())
                
                # Add bonus points if available
                if 'bonusPoints' in cycle and isinstance(cycle['bonusPoints'], dict):
                    bonus = cycle['bonusPoints']
                    if 'team1' in bonus and isinstance(bonus['team1'], (int, float)):
                        team1_score += int(bonus['team1'])
                    if 'team2' in bonus and isinstance(bonus['team2'], (int, float)):
                        team2_score += int(bonus['team2'])
                
                # Handle tossup results
                if 'tossupResult' in cycle and isinstance(cycle['tossupResult'], dict):
                    tossup = cycle['tossupResult']
                    if 'team' in tossup and 'points' in tossup and isinstance(tossup['points'], (int, float)):
                        if tossup['team'] == 1:
                            team1_score += int(tossup['points'])
                        elif tossup['team'] == 2:
                            team2_score += int(tossup['points'])
                
                # Process all buzzes for additional points (like negs)
                if 'allBuzzes' in cycle and isinstance(cycle['allBuzzes'], list):
                    for buzz in cycle['allBuzzes']:
                        if not isinstance(buzz, dict) or 'team' not in buzz or 'points' not in buzz:
                            continue
                        points = int(buzz['points']) if str(buzz['points']).lstrip('-').isdigit() else 0
                        if buzz['team'] == 1:
                            team1_score += points
                        elif buzz['team'] == 2:
                            team2_score += points
            
            # Log the raw scorecard data for debugging
            print("\n=== RAW SCORECARD DATA ===")
            print(json.dumps(data['scorecard'], indent=2))
            
            # Log detailed score calculation
            print("\n=== DETAILED SCORE CALCULATION ===")
            
            # Reset scores to ensure we're calculating from scratch
            team1_score = 0
            team2_score = 0
            
            # Process each cycle in the scorecard
            for i, cycle in enumerate(data['scorecard'], 1):
                print(f"\n--- Cycle {i} ---")
                print(f"Cycle data: {json.dumps(cycle, indent=2)}")
                
                # Initialize cycle scores
                cycle_team1 = 0
                cycle_team2 = 0
                
                # Process team1 player points (from sample_scorecard.json format)
                if 'team1' in cycle and isinstance(cycle['team1'], dict):
                    for player_id, points in cycle['team1'].items():
                        if isinstance(points, (int, float)) or (isinstance(points, str) and points.lstrip('-').isdigit()):
                            points_int = int(points)
                            cycle_team1 += points_int
                            print(f"  Team 1 Player {player_id}: {points_int} points")
                
                # Process team2 player points (from sample_scorecard.json format)
                if 'team2' in cycle and isinstance(cycle['team2'], dict):
                    for player_id, points in cycle['team2'].items():
                        if isinstance(points, (int, float)) or (isinstance(points, str) and points.lstrip('-').isdigit()):
                            points_int = int(points)
                            cycle_team2 += points_int
                            print(f"  Team 2 Player {player_id}: {points_int} points")
                
                # Process bonus points (from sample_scorecard.json format)
                if 'team1Bonus' in cycle and isinstance(cycle['team1Bonus'], (int, float, str)):
                    bonus = int(cycle['team1Bonus']) if str(cycle['team1Bonus']).lstrip('-').isdigit() else 0
                    cycle_team1 += bonus
                    print(f"  Team 1 Bonus: {bonus} points")
                
                if 'team2Bonus' in cycle and isinstance(cycle['team2Bonus'], (int, float, str)):
                    bonus = int(cycle['team2Bonus']) if str(cycle['team2Bonus']).lstrip('-').isdigit() else 0
                    cycle_team2 += bonus
                    print(f"  Team 2 Bonus: {bonus} points")
                
                # Process buzzes to determine tossup results (from sample_scorecard.json format)
                if 'buzzes' in cycle and isinstance(cycle['buzzes'], dict):
                    # Find the first correct buzz to determine which team got the tossup
                    correct_buzzes = [
                        (float(percent), result) 
                        for percent, result in cycle['buzzes'].items() 
                        if result == 'Correct' and percent.replace('.', '').isdigit()
                    ]
                    
                    if correct_buzzes:
                        # Sort by percentage to find the first correct buzz
                        correct_buzzes.sort()
                        first_correct = correct_buzzes[0][1]
                        
                        # Check which team has the correct answer
                        if cycle_team1 > 0:
                            print(f"  Team 1 got the tossup: {cycle_team1} points")
                        elif cycle_team2 > 0:
                            print(f"  Team 2 got the tossup: {cycle_team2} points")
                    
                    # Process all buzzes for negs
                    for percent, result in cycle['buzzes'].items():
                        if result == 'Incorrect' and percent.replace('.', '').isdigit():
                            # Find which team made the incorrect buzz
                            if cycle_team1 < 0:
                                print(f"  Team 1 incorrect buzz: {cycle_team1} points")
                            elif cycle_team2 < 0:
                                print(f"  Team 2 incorrect buzz: {cycle_team2} points")
                
                # Add cycle scores to totals
                team1_score += cycle_team1
                team2_score += cycle_team2
                print(f"Cycle {i} totals - Team 1: {cycle_team1}, Team 2: {cycle_team2}")
            
            # Update game scores with calculated values
            game.team1_score = team1_score
            game.team2_score = team2_score
            
            # Log final scores and result determination
            print("\n=== FINAL SCORE CALCULATION ===")
            print(f"Team 1 Total Score: {team1_score}")
            print(f"Team 2 Total Score: {team2_score}")
            
            # Determine the game result with detailed logging
            if team1_score > team2_score:
                game.result = 1  # Team 1 (first team in DB) wins
                print("RESULT: Team 1 wins (result = 1)")
            elif team2_score > team1_score:
                game.result = -1  # Team 2 (second team in DB) wins
                print("RESULT: Team 2 wins (result = -1)")
            else:
                # Check if all questions have been used (tie with no tiebreakers left)
                total_questions = len(questions) if questions else 0
                questions_used = len([cycle for cycle in data['scorecard'] 
                                   if cycle.get('tossupResult', {}).get('team') is not None])
                
                print(f"Tie detected. Questions used: {questions_used}/{total_questions}")
                
                if questions_used >= total_questions:
                    # All questions used and still a tie
                    game.result = 0  # Declare a tie
                    print("RESULT: All questions used - declaring a tie (result = 0)")
                else:
                    # Not all questions used, but we have a tie - this shouldn't normally happen
                    game.result = 0  # Declare a tie as a fallback
                    print("RESULT: Tie detected before all questions used - declaring a tie (result = 0)")
                    print(f"WARNING: Unexpected tie after {questions_used} questions with {total_questions} total questions")
            
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

@reader_bp.route('/api/teams/add_player', methods=['POST'])
@login_required
def add_player_to_team():
    """
    API endpoint to add a player to a team during a game.
    Expected JSON payload:
    {
        'game_id': int,
        'team_num': int (1 or 2),
        'player_name': str,
        'player_number': int (optional)
    }
    """
    current_app.logger.info('\n=== START add_player_to_team ===')
    
    try:
        # Log request details
        current_app.logger.info(f"Request from user: {current_user.email if current_user.is_authenticated else 'Not authenticated'}")
        current_app.logger.info(f"Request headers: {dict(request.headers)}")
        current_app.logger.info(f"Request data: {request.get_data()}")
        
        # Get JSON data from request
        data = request.get_json()
        if not data:
            current_app.logger.error('No JSON data received')
            return jsonify({'success': False, 'error': 'No data provided'}), 400
            
        current_app.logger.info(f"Received data: {data}")
            
        # Validate required fields
        required_fields = ['game_id', 'team_num', 'player_name']
        for field in required_fields:
            if field not in data:
                current_app.logger.error(f'Missing required field: {field}')
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        game_id = data['game_id']
        team_num = data['team_num']
        player_name = data['player_name'].strip()
        player_number = data.get('player_number')
        
        current_app.logger.info(f'Attempting to add player to game {game_id}, team {team_num}')
        current_app.logger.info(f'Player details - Name: "{player_name}", Number: {player_number}')
        
        # Validate team number
        if team_num not in [1, 2]:
            current_app.logger.error(f'Invalid team number: {team_num} (must be 1 or 2)')
            return jsonify({'success': False, 'error': 'Team number must be 1 or 2'}), 400
        
        # Get the game
        current_app.logger.info(f'Looking up game with ID: {game_id}')
        game = Game.query.get(game_id)
        if not game:
            current_app.logger.error(f'Game not found: {game_id}')
            return jsonify({'success': False, 'error': 'Game not found'}), 404
        
        current_app.logger.info(f'Found game: ID={game.id}, Team1={game.team1}, Team2={game.team2}')
        
        # Get the team name based on team number
        team_name = game.team1 if team_num == 1 else game.team2
        current_app.logger.info(f'Adding player to team {team_num} ({team_name})')
        
        # Format team ID as 'T1' or 'T2'
        formatted_team_id = f"T{team_num}"
        
        # Find an existing player on the same team to get their alias_id
        team_players = Player.query.filter(
            Player.team_id == formatted_team_id
        ).all()
        
        # Get alias_id from first teammate if available
        alias_id = team_players[0].alias_id if team_players else None
        
        # Check for existing players with same name (case insensitive)
        existing_players = Player.query.filter(
            Player.team_id == formatted_team_id,
            db.func.lower(Player.name) == player_name.lower()
        ).all()
        
        if existing_players:
            current_app.logger.warning(f'Player with name "{player_name}" already exists in team {team_num}')
            return jsonify({
                'success': False, 
                'error': f'A player with the name "{player_name}" already exists in this team',
                'existing_players': [p.id for p in existing_players]
            }), 400
        
        # Create new player with same alias_id as teammates if available
        current_app.logger.info('Creating new player record...')
        new_player = Player(
            name=player_name,
            team_id=formatted_team_id,  # Store as 'T1' or 'T2'
            alias_id=alias_id  # Use the same alias_id as other team members
        )
        current_app.logger.info(f'New player will use alias_id: {alias_id}')
        
        # Only set number if provided
        if player_number is not None:
            new_player.number = player_number
        
        current_app.logger.info(f'New player object: {new_player.__dict__}')
        
        db.session.add(new_player)
        db.session.commit()
        
        current_app.logger.info(f'Successfully created player with ID: {new_player.id}')

        return jsonify({
            'success': True,
            'player_id': new_player.id,
            'player_name': new_player.name,
            'team_id': formatted_team_id,
            'team_name': team_name
        })

    except Exception as e:
        current_app.logger.error(f'Error in add_player_to_team: {str(e)}', exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        current_app.logger.info('=== END add_player_to_team ===')

@reader_bp.route('/api/game/<int:game_id>/players')
@login_required
def get_game_players(game_id):
    """
    API endpoint to get the list of players for both teams in a game.
    Returns a JSON object with two arrays: team1 and team2.
    """
    current_app.logger.info(f"=== GET /api/game/{game_id}/players ===")
    current_app.logger.info(f"Current user: {current_user.email if current_user.is_authenticated else 'Not authenticated'}")
    
    try:
        current_app.logger.info(f"Looking up game with ID: {game_id}")
        game = Game.query.get_or_404(game_id)
        current_app.logger.info(f"Found game: {game.id} - Team1: {game.team1}, Team2: {game.team2}")
        
        # Get players for team 1
        current_app.logger.info("Querying players for Team 1...")
        players_team1 = Player.query.filter_by(
            game_id=game_id,
            team_num=1
        ).order_by(Player.name).all()
        current_app.logger.info(f"Found {len(players_team1)} players for Team 1")
        
        # Get players for team 2
        current_app.logger.info("Querying players for Team 2...")
        players_team2 = Player.query.filter_by(
            game_id=game_id,
            team_num=2
        ).order_by(Player.name).all()
        current_app.logger.info(f"Found {len(players_team2)} players for Team 2")
        
        # Log player details for debugging
        for i, player in enumerate(players_team1, 1):
            current_app.logger.debug(f"Team 1 Player {i}: ID={player.id}, Name={player.name}, Number={player.number}")
            
        for i, player in enumerate(players_team2, 1):
            current_app.logger.debug(f"Team 2 Player {i}: ID={player.id}, Name={player.name}, Number={player.number}")
        
        # Convert to list of dicts for JSON serialization
        team1_players = [{
            'id': p.id,
            'name': p.name,
            'number': p.number
        } for p in players_team1]
        
        team2_players = [{
            'id': p.id,
            'name': p.name,
            'number': p.number
        } for p in players_team2]
        
        response_data = {
            'success': True,
            'team1': team1_players,
            'team2': team2_players,
            'debug': {
                'game_id': game_id,
                'team1_count': len(team1_players),
                'team2_count': len(team2_players)
            }
        }
        
        current_app.logger.info(f"Returning {len(team1_players)} team1 players and {len(team2_players)} team2 players")
        return jsonify(response_data)
        
    except Exception as e:
        current_app.logger.error(f"Error in get_game_players: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Failed to fetch players',
            'details': str(e)
        }), 500

# @reader_bp.route('/game/<int:game_id>')
# def game_questions(game_id):
#     game = Game.query.get_or_404(game_id)
#     questions = Question.query.filter_by(game_id=game_id).order_by(Question.id).all()
#     return render_template('questions.html', questions=questions)
