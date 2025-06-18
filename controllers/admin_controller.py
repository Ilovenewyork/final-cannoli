from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from extensions import db
from models import Tournament, TeamAlias, Game, Player, Question, Admin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
from sqlalchemy import text, inspect
import subprocess
import shutil
import tempfile
import json
import os
import sys
from pathlib import Path

admin_bp = Blueprint('admin', __name__, template_folder='../templates/admin')

# Create default admin user if not exists
def create_dummy_admin():
    try:
        admin = Admin.query.filter_by(username='admin').first()
        if not admin:
            admin = Admin(username='admin')
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()
    except Exception as e:
        print(f"Error creating admin user: {str(e)}")
        db.session.rollback()

# Decorator to ensure admin is logged in
def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please provide both username and password', 'danger')
            return render_template('login.html')
            
        try:
            admin = Admin.query.filter_by(username=username).first()
            if admin and admin.check_password(password):
                session['admin_id'] = admin.id
                session.permanent = True  # Make the session persistent
                flash('Login successful!', 'success')
                return redirect(url_for('admin.dashboard'))
            else:
                flash('Invalid username or password', 'danger')
        except Exception as e:
            print(f"Login error: {str(e)}")
            db.session.rollback()
            flash('An error occurred during login. Please try again.', 'danger')
    
    # If GET request or login failed, show login page
    return render_template('login.html')

@admin_bp.route('/dashboard', methods=['GET', 'POST'], endpoint='dashboard')
@admin_login_required
def dashboard():
    try:
        # Get tournaments and formats
        tournaments = Tournament.query.order_by(Tournament.date.desc()).all()
        
        # Get available formats from the formats directory
        formats_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'formats')
        formats = []
        if os.path.exists(formats_dir):
            formats = [f.split('.')[0] for f in os.listdir(formats_dir) if f.endswith('.json')]
        
        if request.method == 'POST':
            try:
                # Get form data
                name = request.form.get('name')
                date_str = request.form.get('date')
                location = request.form.get('location')
                format_name = request.form.get('format')
                
                # Validate required fields
                if not all([name, date_str, location, format_name]):
                    flash('All fields are required', 'danger')
                    return redirect(url_for('admin.dashboard'))
                
                # Parse date
                try:
                    date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid date format. Please use YYYY-MM-DD', 'danger')
                    return redirect(url_for('admin.dashboard'))
                
                # Load format JSON
                format_path = os.path.join(formats_dir, f'{format_name}.json')
                if not os.path.exists(format_path):
                    flash('Selected format not found', 'danger')
                    return redirect(url_for('admin.dashboard'))
                
                with open(format_path, 'r') as f:
                    format_json = json.dumps(json.load(f))  # Convert to string for storage
                
                # Create and save tournament
                new_tournament = Tournament(
                    name=name,
                    date=date,
                    location=location,
                    format_json=format_json
                )
                
                db.session.add(new_tournament)
                db.session.commit()
                
                flash(f'Tournament "{name}" created successfully!', 'success')
                return redirect(url_for('admin.dashboard'))
                
            except Exception as e:
                db.session.rollback()
                print(f"Error creating tournament: {str(e)}")
                flash('An error occurred while creating the tournament', 'danger')
        
        # For GET request or if there was an error
        return render_template('admin/dashboard.html', 
                            tournaments=tournaments, 
                            formats=formats,
                            current_date=datetime.now().strftime('%Y-%m-%d'))
                            
    except Exception as e:
        db.session.rollback()
        print(f"Error in dashboard: {str(e)}")
        flash(f'An error occurred while loading the dashboard: {str(e)}', 'danger')
        return render_template('admin/dashboard.html', 
                            tournaments=[], 
                            formats=[],
                            current_date=datetime.now().strftime('%Y-%m-%d'))

@admin_bp.route('/tournament/create', methods=['POST'])
@admin_login_required
def create_tournament():
    """
    Create a new tournament with the given details.
    This endpoint is called when submitting the tournament creation form.
    """
    try:
        # Log the incoming request
        print("\n=== Tournament Creation Request ===")
        print(f"Request form data: {request.form}")
        
        # Extract form data
        name = request.form['name']
        date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        location = request.form['location']
        format_name = request.form['format']
        
        # Log the extracted data
        print(f"Creating tournament with:")
        print(f"Name: {name}")
        print(f"Date: {date}")
        print(f"Location: {location}")
        print(f"Format: {format_name}")
        
        # Load format file
        format_path = os.path.join('formats', f'{format_name}.json')
        print(f"Loading format from: {format_path}")
        
        with open(format_path, 'r') as f:
            format_json = json.load(f)
            print(f"Loaded format JSON: {json.dumps(format_json, indent=2)}")
        
        # Create tournament
        print("\nCreating Tournament object...")
        new_tournament = Tournament(
            name=name,
            date=date,
            location=location,
            format_json=json.dumps(format_json)  # Changed from format= to format_json=
        )
        
        # Log the created tournament
        print(f"Created Tournament: {new_tournament}")
        
        # Add to database
        print("Adding tournament to session...")
        db.session.add(new_tournament)
        
        # Commit transaction
        print("Committing transaction...")
        db.session.commit()
        
        print("Tournament creation successful!")
        return redirect(url_for('admin.dashboard'))
        
    except KeyError as e:
        print(f"Missing form field: {str(e)}")
        flash(f'Missing required field: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))
        
    except ValueError as e:
        print(f"Invalid date format: {str(e)}")
        flash('Invalid date format. Please use YYYY-MM-DD.', 'error')
        return redirect(url_for('admin.dashboard'))
        
    except Exception as e:
        print(f"=== Unexpected Error ===")
        print(f"Error type: {type(e)}")
        print(f"Error message: {str(e)}")
        import traceback
        print("Full traceback:")
        print(traceback.format_exc())
        
        flash(f'Error creating tournament: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/tournament/<int:tournament_id>', methods=['GET', 'POST'])
@admin_login_required
def tournament_details(tournament_id):
    try:
        tournament = Tournament.query.get_or_404(tournament_id)
        
        # Handle POST request for team assignment
        if request.method == 'POST':
            current_app.logger.info(f"Received POST request with form data: {request.form}")
            
            team_name = request.form.get('team_name')
            team_id = request.form.get('team_id')
            players_str = request.form.get('players', '').strip()
            stage_id = 1  # Default to preliminary stage for team assignment
            
            current_app.logger.info(f"Processing team assignment - Team ID: {team_id}, Name: {team_name}, Players: {players_str}")
            
            if not all([team_name, team_id]):
                error_msg = f"Missing required fields - Team ID: {team_id}, Team Name: {team_name}"
                current_app.logger.error(error_msg)
                flash('Team name and ID are required', 'error')
                return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
            
            # Check if alias exists
            current_app.logger.info(f"Checking if team alias exists - Team ID: {team_id}, Tournament ID: {tournament.id}, Stage ID: {stage_id}")
            alias_exists = TeamAlias.query.filter_by(
                team_id=team_id, 
                tournament_id=tournament.id, 
                stage_id=stage_id
            ).first()
            current_app.logger.info(f"Alias exists check result: {alias_exists is not None}")
            
            if not alias_exists:
                current_app.logger.info("Creating new team alias")
                try:
                    # Assign team name
                    team_alias = TeamAlias(
                        team_name=team_name,
                        team_id=team_id,
                        stage_id=1,  # Always use stage 1 for initial assignments
                        tournament_id=tournament.id
                    )
                    db.session.add(team_alias)
                    db.session.flush()  # Get the team_alias ID for player assignment
                    
                    # Add players if provided
                    if players_str:
                        player_names = [name.strip() for name in players_str.split(',') if name.strip()]
                        for name in player_names:
                            player = Player(
                                name=name,
                                team_id=team_id,
                                alias_id=team_alias.id
                            )
                            db.session.add(player)
                    
                    db.session.commit()
                    success_msg = f'Successfully assigned team name "{team_name}" to {team_id} with {len(player_names) if players_str else 0} players'
                    current_app.logger.info(success_msg)
                    flash(success_msg, 'success')
                except Exception as e:
                    error_msg = f'Error adding team alias: {str(e)}'
                    current_app.logger.error(error_msg, exc_info=True)
                    db.session.rollback()
                    flash(error_msg, 'error')
            else:
                flash('Team alias already exists', 'danger')
            
            return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
        # Load tournament format data
        format_data = json.loads(tournament.format_json)
        if not isinstance(format_data, dict):
            flash('Invalid tournament format data', 'error')
            return redirect(url_for('admin.dashboard'))
        
        # Get all games for this tournament
        games = Game.query.filter_by(tournament_id=tournament.id).all()
        
        # Track completed stages
        completed_stages = set()
        stage_games = {}
        
        # Group games by stage
        for game in games:
            stage_id = str(game.stage_id) if game.stage_id else '1'  # Default to stage 1 if not set
            if stage_id not in stage_games:
                stage_games[stage_id] = []
            stage_games[stage_id].append(game)
        
        # Check which stages are completed (all games have a result)
        for stage_id, stage_games_list in stage_games.items():
            if all(game.result is not None and game.result != -2 for game in stage_games_list):
                completed_stages.add(stage_id)
        
        # Get all team aliases for this tournament
        team_aliases = TeamAlias.query.filter_by(tournament_id=tournament.id).order_by(TeamAlias.stage_id).all()
        
        # Get all players for this tournament
        players = Player.query.join(
            TeamAlias, Player.alias_id == TeamAlias.id
        ).filter(
            TeamAlias.tournament_id == tournament.id
        ).all()
        
        # Organize players by team_id
        team_players = {}
        for player in players:
            if player.team_id not in team_players:
                team_players[player.team_id] = []
            team_players[player.team_id].append(player)
        
        # Create a mapping of team_id to team_name for assigned teams
        # First, get all preliminary aliases (stage 1) to maintain consistent display names
        prelim_teams = {alias.team_id: alias.team_name 
                       for alias in team_aliases 
                       if alias.stage_id == 1}
        
        # Create a mapping of stage_id to dict of {placeholder: team_info}
        stage_seeded_teams = {}
        assigned_teams = {}
        
        # Include players in the team data
        for team_id, team_name in prelim_teams.items():
            assigned_teams[team_id] = {
                'name': team_name,
                'players': [p.name for p in team_players.get(team_id, [])]
            }
        
        # Process all aliases to build the stage_seeded_teams structure
        for alias in team_aliases:
            # For non-prelim stages, organize by stage and placeholder
            if alias.stage_id > 1:
                if alias.stage_id not in stage_seeded_teams:
                    stage_seeded_teams[alias.stage_id] = {}
                
                # Always use the team name from prelims if available
                team_name = prelim_teams.get(alias.team_id, alias.team_name)
                stage_seeded_teams[alias.stage_id][alias.placeholder or alias.team_id] = {
                    'id': alias.team_id,
                    'name': team_name
                }
            
        # Get seeded teams for all stages
        seeded_teams = {}
        for game in games:
            if game.stage_id and game.stage_id > 1:  # Non-prelim stages
                if game.team1 and game.team1 not in seeded_teams:
                    seeded_teams[game.team1] = assigned_teams.get(game.team1, game.team1)
                if game.team2 and game.team2 not in seeded_teams:
                    seeded_teams[game.team2] = assigned_teams.get(game.team2, game.team2)
        
        # Get team IDs from the format data for each stage
        stage_teams = {}
        for stage in format_data.get('tournament_format', {}).get('stages', []):
            stage_id = stage.get('stage_id')
            if stage_id not in stage_teams:
                stage_teams[stage_id] = set()
                
            for rnd in stage.get('rounds', []):
                for pairing in rnd.get('pairings', []):
                    for team in pairing.get('teams', []):
                        if team:  # Only add non-empty team IDs
                            stage_teams[stage_id].add(team)
        
        # For prelims, use the teams directly from the format
        prelim_teams = sorted(stage_teams.get(1, set()))
        unassigned_teams = [t for t in prelim_teams if t not in assigned_teams]
        
        # For other stages, generate placeholders based on the format
        stage_placeholders = {}
        for stage_id, teams in stage_teams.items():
            if stage_id == 1:  # Skip prelims
                continue
                
            # Get unique team placeholders (like T1, T2, etc.)
            team_placeholders = set()
            for team in teams:
                # Extract team placeholders (e.g., 'T1' from 'W1' or 'L1')
                if team.startswith(('W', 'L')) and team[1:].isdigit():
                    team_placeholders.add(f"T{team[1:]}")
                elif team.startswith('T') and team[1:].isdigit():
                    team_placeholders.add(team)
            
            stage_placeholders[stage_id] = sorted(team_placeholders)
        
        # Check if preliminary games exist and are complete
        prelim_games = [g for g in games if g.stage_id == 1]
        prelims_done = len(prelim_games) > 0 and all(
            game.result is not None and game.result != -2 
            for game in prelim_games
        )
        
        # Get question counts for each round
        question_counts = {}
        questions = Question.query.filter_by(tournament_id=tournament_id).all()
        for q in questions:
            key = (q.stage, q.round)
            question_counts[key] = question_counts.get(key, 0) + 1
        
        return render_template('admin/tournament_details.html',
                           tournament=tournament,
                           format_data=format_data,
                           prelims_done=prelims_done,
                           completed_stages=completed_stages,
                           assigned_teams=assigned_teams,
                           unassigned_teams=unassigned_teams,
                           seeded_teams=seeded_teams,
                           stage_placeholders=stage_placeholders,
                           team_aliases=team_aliases,
                           stage_seeded_teams=stage_seeded_teams,
                           question_counts=question_counts)
                           
    except Exception as e:
        db.session.rollback()
        print(f"Error in tournament_details: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('An error occurred while loading tournament details', 'danger')
        return redirect(url_for('admin.dashboard'))

def test_route():
    print("=== test_route was called ===")
    return "Test route is working!"

@admin_bp.route('/create_games/<int:tournament_id>/<int:stage_id>', methods=['GET', 'POST'])
@admin_login_required
def create_games(tournament_id, stage_id):
    print("\n" + "="*80)
    print(f"=== START: create_games for tournament_id: {tournament_id}, stage_id: {stage_id} ===")
    print(f"Request method: {request.method}")
    print(f"Request form data: {request.form}")
    
    try:
        print(f"\n1. Looking up tournament with ID: {tournament_id}")
        tournament = Tournament.query.get_or_404(tournament_id)
        print(f"   Found tournament: {tournament.name} (ID: {tournament.id})")
        
        # Check if previous stage is completed (if not stage 1)
        if stage_id > 1:
            prev_stage_id = stage_id - 1
            prev_stage_games = Game.query.filter_by(
                tournament_id=tournament.id,
                stage_id=prev_stage_id
            ).all()
            
            if not prev_stage_games:
                flash(f'No games found for previous stage {prev_stage_id}. Please create them first.', 'error')
                return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
                
            # Check if all games in previous stage are completed
            if not all(game.result is not None and game.result != -2 for game in prev_stage_games):
                flash(f'Please complete all games in stage {prev_stage_id} before creating games for stage {stage_id}.', 'error')
                return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
        print("\n2. Getting tournament format data...")
        format_data = json.loads(tournament.format_json)
        print(f"   Format data type: {type(format_data)}")
        print(f"   Format data keys: {format_data.keys() if hasattr(format_data, 'keys') else 'N/A'}")
        
        # Find the requested stage
        print(f"\n3. Looking for stage with ID: {stage_id}...")
        stages = format_data.get('tournament_format', {}).get('stages', [])
        print(f"   Found {len(stages)} total stages")
        print(f"   Stage IDs: {[s.get('stage_id') for s in stages]}")
        
        current_stage = next(
            (s for s in stages if s.get('stage_id') == stage_id),
            None
        )
        print(f"   Stage {stage_id} found: {current_stage is not None}")
        
        if not current_stage:
            error_msg = f"Stage {stage_id} not found in the tournament format."
            print(f"   ERROR: {error_msg}")
            flash(error_msg, "danger")
            return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
        # Get team aliases for this tournament and stage
        print(f"\n4. Fetching team aliases for stage {stage_id}...")
        team_aliases = TeamAlias.query.filter_by(
            tournament_id=tournament.id, 
            stage_id=stage_id
        ).all()
        
        # For stages after 1, check if we have seeding from previous stage
        if stage_id > 1:
            # Get winners from previous stage
            prev_stage_winners = set()
            for game in prev_stage_games:
                if game.result == 1 and game.team1:
                    prev_stage_winners.add(game.team1)
                elif game.result == 2 and game.team2:
                    prev_stage_winners.add(game.team2)
            
            # If no team aliases exist for this stage, create them from previous stage winners
            if not team_aliases and prev_stage_winners:
                print(f"   Creating new team aliases for stage {stage_id} from previous stage winners")
                for team_id in prev_stage_winners:
                    # Get team name from previous stage alias or use team_id as fallback
                    prev_alias = TeamAlias.query.filter_by(
                        tournament_name=tournament.name,
                        team_id=team_id,
                        stage_id=stage_id-1
                    ).first()
                    
                    team_name = prev_alias.team_name if prev_alias else f"Team {team_id}"
                    
                    new_alias = TeamAlias(
                        team_name=team_name,
                        team_id=team_id,
                        stage_id=stage_id,
                        tournament_name=tournament.name
                    )
                    db.session.add(new_alias)
                
                try:
                    db.session.commit()
                    # Refresh the team_aliases list
                    team_aliases = TeamAlias.query.filter_by(
                        tournament_name=tournament.name, 
                        stage_id=stage_id
                    ).all()
                    print(f"   Created {len(team_aliases)} new team aliases for stage {stage_id}")
                except Exception as e:
                    db.session.rollback()
                    print(f"   Error creating team aliases: {str(e)}")
                    flash(f"Error creating team aliases: {str(e)}", "error")
                    return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
        aliases = {alias.team_id: alias.team_name for alias in team_aliases}
        print(f"   Found {len(aliases)} team aliases for stage {stage_id}")
        if aliases:
            print(f"   Team aliases: {aliases}")
        
        games_created = 0
        
        # Process each round and pairing in the stage
        rounds = current_stage.get('rounds', [])
        print(f"\n5. Processing {len(rounds)} rounds in stage {stage_id}")
        
        for rnd in rounds:
            round_num = rnd.get('round_in_stage')
            if round_num is None:
                print("   WARNING: round_in_stage not found, defaulting to 1")
                round_num = 1
            pairings = rnd.get('pairings', [])
            print(f"   Processing round {round_num} with {len(pairings)} pairings")
            
            for i, pairing in enumerate(pairings, 1):
                teams = pairing.get('teams', [])
                if len(teams) != 2:
                    print(f"      [{i}] Skipping invalid pairing with {len(teams)} teams: {teams}")
                    continue  # Skip invalid pairings
                
                team1_id, team2_id = teams
                team1_name = aliases.get(team1_id, f"Team {team1_id}")
                team2_name = aliases.get(team2_id, f"Team {team2_id}")
                
                print(f"      [{i}] Processing match: {team1_name} ({team1_id}) vs {team2_name} ({team2_id})")
                
                # Check if game already exists (in either order)
                # Check if game already exists for this stage and round
                existing = Game.query.filter(
                    (Game.tournament_id == tournament.id) &
                    (Game.stage_id == stage_id) &
                    (Game.round_number == round_num) &
                    (
                        ((Game.team1 == team1_id) & (Game.team2 == team2_id)) |
                        ((Game.team1 == team2_id) & (Game.team2 == team1_id))
                    )
                ).first()
                
                if existing:
                    print(f"         Game already exists (ID: {existing.id}), skipping")
                    continue
                    
                print(f"         Creating new game for stage {stage_id}, round {round_num}...")
                try:
                    new_game = Game(
                        team1=team1_id,
                        team2=team2_id,
                        tournament_id=tournament.id,
                        round_number=round_num,
                        stage_id=stage_id,
                        result=-2  # -2 indicates game not started
                    )
                    
                    db.session.add(new_game)
                    db.session.flush()  # Flush to get the game ID
                    
                    # Create game directory if it doesn't exist
                    game_dir = os.path.join(
                        current_app.config['UPLOAD_FOLDER'],
                        str(tournament.id),
                        str(stage_id),
                        str(round_num),
                        str(new_game.id)
                    )
                    os.makedirs(game_dir, exist_ok=True)
                    
                    games_created += 1
                    print(f"         Created game ID: {new_game.id} in stage {stage_id}, round {round_num}")
                    
                except Exception as e:
                    db.session.rollback()
                    print(f"         Error creating game: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    continue  # Continue with next game even if one fails
        
        print(f"\n6. Finalizing stage {stage_id}...")
        success = False
        
        if games_created > 0:
            try:
                print(f"   Committing {games_created} new games to the database...")
                db.session.commit()
                msg = f'Successfully created {games_created} games for stage {stage_id}!'
                print(f"   {msg}")
                flash(msg, 'success')
                success = True
                
                # If this is a playoff stage, update the tournament status
                if stage_id > 1:
                    try:
                        # Get the tournament format data
                        format_data = json.loads(tournament.format_json)
                        if 'stages' in format_data.get('tournament_format', {}):
                            stages = format_data['tournament_format']['stages']
                            # Find the current stage and mark it as created
                            for stage in stages:
                                if stage.get('stage_id') == stage_id:
                                    stage['games_created'] = True
                                    break
                            
                            # Save the updated format data
                            tournament.format_json = json.dumps(format_data, indent=2)
                            db.session.commit()
                            print(f"   Updated tournament format to mark stage {stage_id} as created")
                            
                    except Exception as update_error:
                        print(f"   Warning: Could not update tournament status: {str(update_error)}")
                        # Don't fail the whole operation if we can't update the status
                        
            except Exception as commit_error:
                db.session.rollback()
                error_msg = f'Database commit error: {str(commit_error)}'
                print(f"   ERROR: {error_msg}")
                import traceback
                traceback.print_exc()
                flash(error_msg, 'danger')
        else:
            msg = f'No new games were created for stage {stage_id} (they may already exist).'
            print(f"   {msg}")
            flash(msg, 'info')
            success = True  # Not an error if no new games were needed
            
    except Exception as e:
        print("\n!!! UNEXPECTED ERROR !!!")
        error_msg = f'Error creating games for stage {stage_id}: {str(e)}'
        print(error_msg)
        import traceback
        traceback.print_exc()
        db.session.rollback()
        flash(error_msg, 'danger')
    
    print("\n" + "="*80)
    print(f"=== END: create_games for tournament_id: {tournament_id}, stage_id: {stage_id} ===\n\n")
    
    return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))

def auto_assign_playoff_seeding(tournament):
    """
    Automatically assign playoff seeding based on preliminary round results.
    Teams are ranked by number of wins in the preliminary stage.
    """
    try:
        # Get all preliminary aliases and games for this tournament
        prelim_aliases = TeamAlias.query.filter_by(
            tournament_id=tournament.id, 
            stage_id=1  # Preliminary stage
        ).all()
        
        if not prelim_aliases:
            return False, "No preliminary teams found. Please assign teams to the preliminary stage first."
        
        prelim_games = Game.query.filter_by(
            tournament_id=tournament.id, 
            stage_id=1  # Preliminary stage
        ).all()
        
        # Initialize win counts (using team_name as key)
        standings = {alias.team_name: 0 for alias in prelim_aliases}
        
        # Calculate wins for each team
        for game in prelim_games:
            if game.scorecard is not None and game.result != -2:  # -2 means not played
                if game.result == 1:  # team1 won
                    standings[game.team1] = standings.get(game.team1, 0) + 1
                elif game.result == -1:  # team2 won
                    standings[game.team2] = standings.get(game.team2, 0) + 1
        
        # Sort teams by wins (descending)
        sorted_teams = sorted(standings.items(), key=lambda x: (-x[1], x[0]))
        
        try:
            # Start a transaction
            db.session.begin()
            
            # Remove any existing playoff aliases (stage_id=2)
            TeamAlias.query.filter_by(
                tournament_id=tournament.id, 
                stage_id=2  # Playoff stage
            ).delete()
            
            # Create new playoff aliases with seeds "T1", "T2", ...
            aliases_created = []
            for idx, (team_name, wins) in enumerate(sorted_teams, start=1):
                seed = f"T{idx}"
                new_alias = TeamAlias(
                    team_name=team_name,
                    team_id=team_name,  # Store the original team name as team_id
                    stage_id=2,  # Playoff stage
                    tournament_id=tournament.id,
                    placeholder=seed  # Store the seed as the placeholder
                )
                db.session.add(new_alias)
                aliases_created.append((team_name, seed))
            
            db.session.commit()
            return True, f"Successfully created {len(aliases_created)} playoff seeds."
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error in auto_assign_playoff_seeding: {str(e)}")
            return False, f"Failed to assign playoff seeding: {str(e)}"
            
    except Exception as e:
        current_app.logger.error(f"Error in auto_assign_playoff_seeding (outer): {str(e)}")
        return False, f"An error occurred: {str(e)}"

@admin_bp.route('/create_playoff_games/<int:tournament_id>')
@admin_login_required
def create_playoff_games(tournament_id):
    """
    Create playoff games based on the tournament format and preliminary results.
    This function ensures all preliminary games are complete and creates the first round of playoff games.
    """
    current_app.logger.info(f"Starting create_playoff_games for tournament {tournament_id}")
    
    try:
        tournament = Tournament.query.get_or_404(tournament_id)
        current_app.logger.info(f"Found tournament: {tournament.name}")
        
        format_data = tournament.format  # Using the @property
        current_app.logger.info(f"Format data: {json.dumps(format_data, indent=2)}")
        
        # Find playoff stages (all stages except the preliminary stage)
        playoff_stages = [
            stage for stage in format_data['tournament_format']['stages'] 
            if stage.get('stage_id') != 1  # Exclude preliminary stage
        ]
        
        current_app.logger.info(f"Found {len(playoff_stages)} playoff stages")
        
        if not playoff_stages:
            error_msg = "No playoff stages are defined in the tournament format."
            current_app.logger.error(error_msg)
            flash(error_msg, "danger")
            return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
        # Check if preliminary games are complete
        prelim_stage = next(
            (stage for stage in format_data['tournament_format']['stages'] 
             if stage.get('stage_id') == 1),  # Preliminary stage
            None
        )
        
        if not prelim_stage:
            flash("Preliminary stage not found in the tournament format.", "danger")
            return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
        # Calculate expected number of preliminary games
        expected_prelim_games = sum(
            len(round_data.get('pairings', [])) 
            for round_data in prelim_stage.get('rounds', [])
        )
        
        current_app.logger.info(f"Expected {expected_prelim_games} preliminary games")
        
        # Get all preliminary games
        prelim_games = Game.query.filter_by(
            tournament_id=tournament.id,
            stage_id=1  # Preliminary stage
        ).all()
        
        current_app.logger.info(f"Found {len(prelim_games)} preliminary games in the database")
        
        # Check if all preliminary games have been created
        if len(prelim_games) != expected_prelim_games:
            error_msg = f"Preliminary games have not been created yet. Expected {expected_prelim_games}, found {len(prelim_games)}."
            current_app.logger.error(error_msg)
            flash(error_msg, "danger")
            return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
        # Check if all preliminary games are complete
        incomplete_prelims = [
            game for game in prelim_games 
            if game.scorecard is None or game.result == -2
        ]
        
        if incomplete_prelims:
            error_msg = f"Not all preliminary games are complete. Found {len(incomplete_prelims)} incomplete games."
            current_app.logger.error(error_msg)
            flash(error_msg, "danger")
            return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
        # Ensure playoff seeding aliases exist, auto-assign if missing
        current_app.logger.info("Checking for playoff aliases...")
        playoff_aliases = TeamAlias.query.filter_by(
            tournament_id=tournament.id,
            stage_id=2  # Playoff stage
        ).all()
        
        current_app.logger.info(f"Found {len(playoff_aliases)} playoff aliases")
        
        if not playoff_aliases:
            current_app.logger.info("No playoff aliases found, attempting to auto-assign")
            success, message = auto_assign_playoff_seeding(tournament)
            if not success:
                error_msg = f"Failed to auto-assign playoff seeding: {message}"
                current_app.logger.error(error_msg)
                flash(error_msg, "danger")
                return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
            
            # Commit any changes from auto_assign_playoff_seeding
            db.session.commit()
            
            playoff_aliases = TeamAlias.query.filter_by(
                tournament_id=tournament.id,
                stage_id=2  # Playoff stage
            ).all()
            
            current_app.logger.info(f"After auto-assign, found {len(playoff_aliases)} playoff aliases")
            
            if not playoff_aliases:
                error_msg = "Failed to create playoff seedings. Please try again."
                current_app.logger.error(error_msg)
                flash(error_msg, "danger")
                return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
        # Create a mapping of team IDs to their display names for the playoff stage
        aliases = {alias.placeholder or alias.team_id: alias.team_name for alias in playoff_aliases}
        current_app.logger.info(f"Alias mapping: {aliases}")
        
        # Also create a reverse mapping from team name to placeholder for lookup
        team_to_placeholder = {alias.team_id: alias.placeholder for alias in playoff_aliases if alias.placeholder}
        
        playoff_created = False
        games_created = 0
        
        current_app.logger.info(f"Processing {len(playoff_stages)} playoff stages")
        
        for stage_idx, stage in enumerate(playoff_stages, 1):
            stage_id = stage.get('stage_id')
            current_app.logger.info(f"Processing stage {stage_id} ({stage_idx}/{len(playoff_stages)})")
            
            for rnd in stage.get('rounds', []):
                round_num = rnd.get('round_in_stage')
                current_app.logger.info(f"  Processing round {round_num}")
                
                for pair_idx, pairing in enumerate(rnd.get('pairings', []), 1):
                    teams = pairing.get('teams', [])
                    if len(teams) != 2:
                        current_app.logger.warning(f"    Invalid pairing {pair_idx}: expected 2 teams, got {len(teams)}")
                        continue
                        
                    team1_orig, team2_orig = teams
                    
                    # Check if game already exists in this stage and round
                    existing = Game.query.filter(
                        Game.tournament_id == tournament.id,
                        Game.stage_id == stage_id,
                        Game.round_number == round_num,
                        ((Game.team1 == team1_orig) & (Game.team2 == team2_orig)) |
                        ((Game.team1 == team2_orig) & (Game.team2 == team1_orig))
                    ).first()
                    
                    if existing:
                        current_app.logger.info(f"    Game {team1_orig} vs {team2_orig} already exists (ID: {existing.id})")
                        continue
                    
                    # Resolve team names using aliases
                    team1_name = aliases.get(team1_orig, team1_orig)
                    team2_name = aliases.get(team2_orig, team2_orig)
                    
                    # If this is a winner/loser bracket reference, keep it as is
                    if team1_orig.startswith(('W(', 'L(')):
                        team1_name = team1_orig
                    if team2_orig.startswith(('W(', 'L(')):
                        team2_name = team2_orig
                    
                    current_app.logger.info(f"    Creating game: {team1_name} vs {team2_name} (Stage {stage_id}, Round {round_num})")
                    
                    game = Game(
                        team1=team1_name,
                        team2=team2_name,
                        result=-2,
                        tournament_id=tournament.id,
                        round_number=round_num,
                        stage_id=stage_id,
                        scorecard=None
                    )
                    
                    db.session.add(game)
                    games_created += 1
                    playoff_created = True
        
        print(f"\n6. Finalizing...")
        success = False
        try:
            if games_created > 0:
                db.session.commit()
                print(f"Successfully created {games_created} new games for stage {stage_id}")
                flash(f'Successfully created {games_created} new games for stage {stage_id}', 'success')
                success = True
            else:
                print("No new games were created")
                flash('No new games were created - all games already exist', 'info')
                success = True
                
        except Exception as e:
            db.session.rollback()
            print(f"Error committing games: {str(e)}")
            import traceback
            traceback.print_exc()
            flash('An error occurred while creating games', 'error')
        
        # If we're creating playoff games (stage 2+), we might need to update the tournament status
        if success and games_created > 0 and stage_id > 1:
            try:
                # Update tournament status to indicate this stage's games have been created
                # You might want to add a field to track which stages have been created
                current_app.logger.info(f"Successfully created {games_created} games for stage {stage_id}")
            except Exception as e:
                current_app.logger.warning(f"Could not update tournament status: {str(e)}")
        
        return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
    except Exception as e:
        db.session.rollback()
        print(f"Error in create_games: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'An error occurred while creating games: {str(e)}', 'error')
        return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))

@admin_bp.route('/assign_playoff_seeding/<int:tournament_id>', methods=['POST'])
@admin_login_required
def assign_playoff_seeding(tournament_id):
    current_app.logger.info(f"Starting assign_playoff_seeding for tournament {tournament_id}")
    tournament = Tournament.query.get_or_404(tournament_id)
    
    try:
        # Log all form data for debugging
        form_data = dict(request.form)
        current_app.logger.info(f"Form data received: {form_data}")
        
        # Get the team_id and seed from the form
        team_id = request.form.get('team_select')
        seed = request.form.get('seed')
        
        if not team_id or not seed:
            error_msg = f"Missing required fields. Team ID: {team_id}, Seed: {seed}"
            current_app.logger.error(error_msg)
            flash("Missing required fields. Please select both a team and a seed.", "danger")
            return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
        # Get the team's actual name from the assigned teams
        assigned_teams = {}
        for alias in TeamAlias.query.filter_by(tournament_id=tournament_id, stage_id=1).all():
            assigned_teams[alias.team_id] = alias.team_name
        
        team_name = assigned_teams.get(team_id)
        if not team_name:
            error_msg = f"Could not find team with ID: {team_id}"
            current_app.logger.error(error_msg)
            flash("Invalid team selected. Please try again.", "danger")
            return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
        current_app.logger.info(f"Processing - Team: {team_name}, ID: {team_id}, Seed: {seed}")
        
        # Check if this team is already seeded for playoffs
        existing_playoff_alias = TeamAlias.query.filter(
            TeamAlias.tournament_id == tournament_id,
            TeamAlias.stage_id == 2,
            TeamAlias.team_id == team_id
        ).first()
        
        if existing_playoff_alias:
            warning_msg = f"{team_name} (ID: {team_id}) has already been seeded as {existing_playoff_alias.team_id}"
            current_app.logger.warning(warning_msg)
            flash(warning_msg, "warning")
            return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
        # Check if this seed is already taken
        existing_seed = TeamAlias.query.filter(
            TeamAlias.tournament_id == tournament_id,
            TeamAlias.stage_id == 2,
            TeamAlias.team_id == seed
        ).first()
        
        if existing_seed:
            warning_msg = f"Seed {seed} is already assigned to {existing_seed.team_name}"
            current_app.logger.warning(warning_msg)
            flash(warning_msg, "warning")
            return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
        # Create new playoff alias (stage_id=2 for playoffs)
        playoff_alias = TeamAlias(
            team_name=team_name,
            team_id=seed,  # Using seed as team_id for playoff seeding
            stage_id=2,    # Playoff stage
            tournament_id=tournament_id
        )
        
        db.session.add(playoff_alias)
        db.session.commit()
        
        success_msg = f"Successfully assigned {team_name} (ID: {team_id}) as {seed} for playoffs"
        current_app.logger.info(success_msg)
        flash(success_msg, "success")
        
    except Exception as e:
        error_msg = f"Error assigning playoff seed: {str(e)}"
        current_app.logger.error(error_msg, exc_info=True)
        db.session.rollback()
        flash(f"An error occurred: {str(e)}", "danger")
    
    return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))

@admin_bp.route('/upload_round_file/<int:tournament_id>/<stage_id>/<int:round_number>', methods=['GET', 'POST'])
@admin_login_required
def upload_round_file(tournament_id, stage_id, round_number):
    from extensions import db  # Import db at function level to avoid circular imports
    
    if request.method == 'POST':
        if 'packet_file' not in request.files:
            flash('No file part in the request', 'danger')
            return redirect(request.url)
            
        file = request.files['packet_file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
            
        import os
        import subprocess
        import json
        import shutil
        import traceback
        from pathlib import Path

        try:
            # Define paths - use the project root directory
            base_dir = Path(current_app.root_path)
            parser_dir = base_dir / 'packet-parser-main'
            
            # For debugging - show the full path we're using
            print(f"Project root: {base_dir}")
            print(f"Looking for parser in: {parser_dir}")
            print(f"Directory exists: {parser_dir.exists()}")
            
            print(f"\n=== Starting file upload process ===")
            print(f"Base directory: {base_dir}")
            print(f"Parser directory: {parser_dir}")
            
            # Check if packet-parser-main directory exists
            if not parser_dir.exists():
                error_msg = f"Packet parser directory not found at: {parser_dir}"
                print(f"ERROR: {error_msg}")
                print(f"Current working directory: {Path.cwd()}")
                print(f"Directory contents of {base_dir}:")
                try:
                    for f in base_dir.iterdir():
                        print(f"  - {f.name} (dir: {f.is_dir()})")
                except Exception as e:
                    print(f"Could not list directory contents: {e}")
                raise FileNotFoundError(error_msg)
            
            # Check for required files and directories
            required_paths = [
                ('to-txt.sh', 'file'),
                ('modules/docx-to-txt.py', 'file'),
                ('modules', 'dir'),
                'p-docx',
                'output'
            ]
            
            missing_paths = []
            for path_spec in required_paths:
                if isinstance(path_spec, tuple):
                    path, path_type = path_spec
                else:
                    path, path_type = path_spec, 'any'
                    
                full_path = parser_dir / path
                
                if path_type == 'file' and not full_path.is_file():
                    missing_paths.append(f"File not found: {path}")
                    print(f"MISSING: {full_path} (expected file)")
                elif path_type == 'dir' and not full_path.is_dir():
                    missing_paths.append(f"Directory not found: {path}")
                    print(f"MISSING: {full_path} (expected directory)")
                elif path_type == 'any' and not full_path.exists():
                    missing_paths.append(f"Path not found: {path}")
                    print(f"MISSING: {full_path}")
            
            if missing_paths:
                error_msg = f"Required paths not found in {parser_dir}:\n  " + "\n  ".join(missing_paths)
                print(f"\n{error_msg}")
                print(f"\nFiles in {parser_dir}:")
                try:
                    for f in sorted(parser_dir.iterdir()):
                        type_str = "dir" if f.is_dir() else "file"
                        print(f"  - {f.name} ({type_str})")
                        
                    # Also show modules directory if it exists
                    modules_dir = parser_dir / 'modules'
                    if modules_dir.exists():
                        print(f"\nFiles in {modules_dir}:")
                        for f in sorted(modules_dir.iterdir()):
                            type_str = "dir" if f.is_dir() else "file"
                            print(f"  - {f.name} ({type_str})")
                            
                except Exception as e:
                    print(f"Could not list directory contents: {e}")
                raise FileNotFoundError(error_msg)
                    
            p_docx_dir = parser_dir / 'p-docx'
            output_dir = parser_dir / 'output'
            
            print(f"\n=== Directory structure validated ===")
            print(f"p_docx_dir: {p_docx_dir}")
            print(f"output_dir: {output_dir}")
            
            # Create directories if they don't exist
            print(f"\n=== Creating/cleaning directories ===")
            p_docx_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created/validated directories")
            
            # Clear any existing files in the directories
            print(f"\n=== Cleaning up old files ===")
            print(f"Cleaning {p_docx_dir}:")
            for f in p_docx_dir.glob('*'):
                print(f"  - Deleting {f}")
                f.unlink()
                
            print(f"\nCleaning {output_dir}:")
            for f in output_dir.glob('*'):
                print(f"  - Deleting {f}")
                f.unlink()
            
            # Save the uploaded file to p-docx immediately
            if not file or not hasattr(file, 'filename') or not file.filename:
                raise ValueError("No file was uploaded or file has no filename")
                
            # Ensure we have a safe filename
            filename = os.path.basename(file.filename)
            if not filename:
                raise ValueError("Invalid filename")
                
            file_path = p_docx_dir / filename
            print(f"\n=== Saving uploaded file ===")
            print(f"Saving to: {file_path}")
            
            try:
                # Ensure the directory exists
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Save the file content
                file.save(str(file_path))
                print(f"File saved successfully: {file_path}")
                
                # Verify the file was saved
                if not file_path.exists() or file_path.stat().st_size == 0:
                    raise IOError(f"Failed to save file or file is empty: {file_path}")
                    
            except Exception as e:
                print(f"Error saving file: {e}")
                raise
            
            # Set up the environment for the script
            env = os.environ.copy()
            env['PYTHONPATH'] = str(parser_dir)  # Add parser_dir to Python path
            
            # Create packets directory if it doesn't exist
            packets_dir = parser_dir / 'packets'
            packets_dir.mkdir(exist_ok=True)
            
            # Clean up any existing files in the packets directory
            print(f"\nCleaning {packets_dir}:")
            for f in packets_dir.glob('*'):
                print(f"  - Deleting {f}")
                try:
                    f.unlink()
                except Exception as e:
                    print(f"    Failed to delete {f}: {e}")
            
            # Run the docx-to-txt.py script directly
            docx_to_txt_script = parser_dir / 'modules' / 'docx-to-txt.py'
            
            # Run the docx-to-txt.py script directly
            print(f"\n=== Running docx-to-txt.py ===")
            print(f"Script path: {docx_to_txt_script}")
            print(f"Input file: {file_path}")
            print(f"Output dir: {packets_dir}")
            
            # Prepare the output filename
            output_file = packets_dir / f"{file_path.stem}.txt"
            
            # Run the script
            process = subprocess.Popen(
                ['python', str(docx_to_txt_script), str(file_path), str(output_file)],
                cwd=str(parser_dir),  # Set working directory to parser_dir
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True,  # Required for Windows to find python
                env=env      # Pass the environment with PYTHONPATH
            )
            
            # Wait for completion
            stdout, stderr = process.communicate()
            
            print(f"\ndocx-to-txt.py stdout:\n{stdout}")
            if stderr:
                print(f"\ndocx-to-txt.py stderr:\n{stderr}")
            print(f"docx-to-txt.py return code: {process.returncode}")
            
            if process.returncode != 0:
                error_msg = f"docx-to-txt.py failed with return code {process.returncode}: {stderr}"
                print(f"ERROR: {error_msg}")
                raise Exception(error_msg)
                
            # Verify the output file was created
            if not output_file.exists() or output_file.stat().st_size == 0:
                raise Exception(f"Output file was not created or is empty: {output_file}")
                
            print(f"Successfully processed document. Output: {output_file}")
            
            # Run packet_parser.py with -f flag and answer prompts
            parser_script = parser_dir / 'packet_parser.py'
            
            # Make sure the file exists and is accessible
            if not parser_script.exists():
                raise FileNotFoundError(f"packet_parser.py not found at {parser_script}")
            
            # Make sure the input file exists
            if not file_path.exists():
                raise FileNotFoundError(f"Input file not found at {file_path}")
                
            print(f"Input file exists: {file_path.exists()}, size: {file_path.stat().st_size} bytes")
            print(f"\n=== Running packet_parser.py ===")
            print(f"Script path: {parser_script}")
            print(f"Working directory: {parser_dir}")
            
            process = subprocess.Popen(
                ['python', str(parser_script), '-f'],
                cwd=str(parser_dir),  # Convert to string for Windows compatibility
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True  # Required for Windows to find python
            )
            
            # Answer the prompts
            has_q_nums = 'y' if request.form.get('has_question_numbers') == 'y' else 'n'
            has_cats = 'y' if request.form.get('has_category_tags') == 'y' else 'n'
            
            print(f"Sending answers to prompts: question_numbers={has_q_nums}, category_tags={has_cats}")
            stdout, stderr = process.communicate(input=f"{has_q_nums}\n{has_cats}\n")
            
            print(f"\npacket_parser.py stdout:\n{stdout}")
            if stderr:
                print(f"\npacket_parser.py stderr:\n{stderr}")
            print(f"packet_parser.py return code: {process.returncode}")
            
            if process.returncode != 0:
                error_msg = f"packet_parser.py failed with return code {process.returncode}: {stderr}"
                print(f"ERROR: {error_msg}")
                raise Exception(error_msg)
            
            if process.returncode != 0:
                raise Exception(f"packet_parser.py failed: {stderr}")
            
            # Find the output JSON file
            print(f"\n=== Looking for output JSON ===")
            output_files = list(output_dir.glob('*.json'))
            print(f"Found {len(output_files)} JSON files in {output_dir}:")
            for f in output_files:
                print(f"  - {f}")
                
            if not output_files:
                error_msg = f"No JSON output file found in {output_dir}"
                print(f"ERROR: {error_msg}")
                print(f"Contents of {output_dir}:")
                try:
                    for f in output_dir.iterdir():
                        print(f"  - {f.name} (size: {f.stat().st_size} bytes)")
                except Exception as e:
                    print(f"Could not list output directory: {e}")
                raise Exception(error_msg)
                
            # Read and process the JSON
            output_file = output_files[0]
            print(f"\n=== Processing JSON file: {output_file} ===")
            print(f"File size: {output_file.stat().st_size} bytes")
            
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"Successfully loaded JSON with {len(data.get('tossups', []))} tossups and {len(data.get('bonuses', []))} bonuses")
            except json.JSONDecodeError as e:
                print(f"ERROR: Failed to parse JSON: {e}")
                print("File content (first 500 chars):")
                with open(output_file, 'r', encoding='utf-8', errors='replace') as f:
                    print(f.read(500) + ("..." if len(f.read(501)) > 500 else ""))
                raise
            
            # First, collect all questions to determine correct ordering
            all_questions = []
            
            # Process tossups
            for tossup in data.get('tossups', []):
                question_number = int(tossup.get('number', 0)) or 0
                all_questions.append({
                    'type': 'tossup',
                    'number': question_number,
                    'data': tossup
                })
            
            # Process bonuses
            for bonus in data.get('bonuses', []):
                bonus_number = int(bonus.get('number', 0)) or 0
                all_questions.append({
                    'type': 'bonus',
                    'number': bonus_number,
                    'data': bonus
                })
            
            # Sort all questions by their question number
            all_questions.sort(key=lambda x: x['number'])
            
            # Now process them in order
            tossups_added = 0
            bonuses_added = 0
            
            for q in all_questions:
                if q['type'] == 'tossup':
                    tossup = q['data']
                    question_number = q['number']
                    question = Question(
                        question_type='tossup',
                        question_text=tossup.get('question', ''),
                        answer=tossup.get('answer', ''),
                        question_number=question_number,
                        round=round_number,
                        stage=stage_id,
                        tournament_id=tournament_id,
                        order=question_number,
                        is_bonus=False,
                        category=tossup.get('category', ''),
                        subcategory=tossup.get('subcategory', ''),
                        alternate_subcategory=tossup.get('alternate_subcategory', '')
                    )
                    db.session.add(question)
                    tossups_added += 1
                else:
                    bonus = q['data']
                    bonus_number = q['number']
                    
                    # Get parts and answers, ensuring they are lists
                    parts = bonus.get('parts', [])
                    answers = bonus.get('answers', [])
                    
                    # If parts/answers are strings, try to parse them as JSON
                    if isinstance(parts, str):
                        try:
                            parts = json.loads(parts)
                        except (json.JSONDecodeError, TypeError):
                            parts = [parts]  # Fallback to single part
                    
                    if isinstance(answers, str):
                        try:
                            answers = json.loads(answers)
                        except (json.JSONDecodeError, TypeError):
                            answers = [answers]  # Fallback to single answer
                    
                    # Ensure parts and answers are lists and have the same length
                    if not isinstance(parts, list):
                        parts = [str(parts)]
                    if not isinstance(answers, list):
                        answers = [str(answers)]
                    
                    # Pad or truncate to ensure at least 3 parts/answers
                    while len(parts) < 3:
                        parts.append('')
                    while len(answers) < 3:
                        answers.append('')
                    parts = parts[:3]
                    answers = answers[:3]
                    
                    # Create a single bonus question with all parts
                    question = Question(
                        question_type='bonus',
                        question_text=bonus.get('leadin', ''),
                        answer='',  # Answers are stored in the answers JSON field
                        question_number=bonus_number,
                        round=round_number,
                        stage=stage_id,
                        tournament_id=tournament_id,
                        order=bonus_number,  # Use the bonus number as the order
                        is_bonus=True,
                        bonus_part=0,  # 0 indicates this is the main bonus question
                        parts=parts,
                        answers=answers,
                        category=bonus.get('category', ''),
                        subcategory=bonus.get('subcategory', ''),
                        alternate_subcategory=bonus.get('alternate_subcategory', '')
                    )
                    db.session.add(question)
                    bonuses_added += 1
            
            db.session.commit()
            
            flash(f'Successfully processed {tossups_added} tossups and {bonuses_added} bonuses!', 'success')
            return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
            
        except Exception as e:
            flash(f'Error processing file: {str(e)}', 'danger')
            return redirect(request.url)
            
        finally:
            # Clean up the temporary files
            try:
                # Remove the uploaded file
                if 'file_path' in locals() and file_path and file_path.exists():
                    file_path.unlink()
                
                # Clean up the parser directories
                if 'p_docx_dir' in locals() and p_docx_dir and p_docx_dir.exists():
                    for f in p_docx_dir.glob('*'):
                        try:
                            f.unlink()
                        except Exception as e:
                            current_app.logger.warning(f"Could not remove {f}: {e}")
                
                if 'output_dir' in locals() and output_dir and output_dir.exists():
                    for f in output_dir.glob('*'):
                        try:
                            f.unlink()
                        except Exception as e:
                            current_app.logger.warning(f"Could not remove {f}: {e}")
            except Exception as e:
                current_app.logger.error(f"Error during cleanup: {e}", exc_info=True)
    
    # For GET request, just show the form
    tournament = db.session.get(Tournament, tournament_id)
    if not tournament:
        error_msg = f"Tournament with ID {tournament_id} not found"
        print(f"\n!!! ERROR: {error_msg}")
        flash(error_msg, 'danger')
        return redirect(url_for('admin.dashboard'))
    
    tournament_name = tournament.name
    print(f"\nProcessing packet for tournament: {tournament_name}")

    if request.method == 'GET':
        print("\nRendering upload form")
        print("Serving upload form template")
        return render_template('admin/upload_round_file.html', 
                            tournament_name=tournament_name, 
                            tournament_id=tournament_id,
                            stage_id=stage_id, 
                            round_number=round_number)

    # Handle POST request
    print("\n=== PROCESSING FILE UPLOAD ===")
    print(f"Request files: {request.files}")
    
    # Check if 'packet_file' is in request.files
    if 'packet_file' not in request.files:
        error_msg = "No 'packet_file' part in the request"
        print(f"\n!!! ERROR: {error_msg}")
        print("Available files in request:", list(request.files.keys()))
        flash(error_msg, 'danger')
        return redirect(request.url)
    
    file = request.files['packet_file']
    print(f"File object: {file}")
    print(f"File name: {file.filename}")
    print(f"File content type: {file.content_type}")
    print(f"File headers: {file.headers}")
    
    if file.filename == '':
        error_msg = "No file selected"
        print(f"\n!!! ERROR: {error_msg}")
        flash(error_msg, 'danger')
        return redirect(request.url)
    
    # Validate file extension
    if not file.filename.lower().endswith(('.docx', '.doc')):
        error_msg = "Only .docx or .doc files are allowed"
        print(f"Error: {error_msg}")
        flash(error_msg, 'danger')
        return redirect(request.url)
    
    # Get user input for parser options
    has_question_numbers = request.form.get('has_question_numbers', 'n').lower() == 'y'
    has_category_tags = request.form.get('has_category_tags', 'n').lower() == 'y'
    
    print(f"Parser options - Has question numbers: {has_question_numbers}, Has category tags: {has_category_tags}")

    # Create a temporary directory for processing
    temp_dir = tempfile.mkdtemp()
    print(f"Created temporary directory: {temp_dir}")
    
    # Save the uploaded file with a .docx extension
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in ('.docx', '.doc'):
        file_extension = '.docx'  # Default to .docx if extension is not recognized
    
    file_name = f"packet_{tournament_id}_{stage_id}_{round_number}{file_extension}"
    file_path = os.path.join(temp_dir, file_name)
    file.save(file_path)
    print(f"Saved uploaded file to: {file_path}")
    
    try:
        # Prepare command for the parser
        parser_script = os.path.abspath(os.path.join(
            current_app.root_path, '..', 'packet-parser-main', 'packet_parser.py'
        ))
        
        if not os.path.exists(parser_script):
            raise FileNotFoundError(f"Parser script not found at: {parser_script}")
            
        output_dir = os.path.join(temp_dir, 'output')
        os.makedirs(output_dir, exist_ok=True)
        print(f"Created output directory: {output_dir}")
        
        # Build command with appropriate flags based on user input
        cmd = [sys.executable, parser_script, file_path, '--output-dir', output_dir]
        if has_question_numbers:
            cmd.append('--has-question-numbers')
        if has_category_tags:
            cmd.append('--has-category-tags')
        
        # Run the parser
        print(f"\n=== Running parser command ===")
        print(f"Command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        # Log the output for debugging
        print("\n=== Parser Output ===")
        print(f"Return code: {result.returncode}")
        print(f"Stdout: {result.stdout}")
        if result.stderr:
            print(f"Stderr: {result.stderr}")
        
        if result.returncode != 0:
            raise Exception(f"Parser failed with return code {result.returncode}")
        
        # Process the output
        output_files = [f for f in os.listdir(output_dir) if f.endswith('.json')]
        print(f"\nFound {len(output_files)} JSON output files")
        
        if not output_files:
            raise Exception("No JSON output files found. Parser output: " + (result.stderr or "No error output"))
        
        # Get the first JSON file (should be only one)
        json_file = os.path.join(output_dir, output_files[0])
        print(f"Processing JSON file: {json_file}")
        
        # Read and parse the JSON
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, dict) or 'tossups' not in data:
            raise ValueError("Invalid JSON format. Expected object with 'tossups' key.")
        
        tossup_count = len(data.get('tossups', []))
        bonus_count = len(data.get('bonuses', []))
        print(f"Found {tossup_count} tossups and {bonus_count} bonuses in the packet")
        
        # Insert tossups into database
        for i, tossup in enumerate(data.get('tossups', []), 1):
            question = Question(
                tournament_id=tournament_id,
                stage=stage_id,
                round=round_number,
                question_text=tossup.get('question', ''),
                answerline=tossup.get('answer', ''),
                question_number=tossup.get('number'),
                category=tossup.get('category')
            )
            db.session.add(question)
            if i % 10 == 0 or i == tossup_count:
                print(f"Added {i}/{tossup_count} tossups to database")
        
        # Insert bonuses into database if they exist
        if 'bonuses' in data:
            for i, bonus in enumerate(data['bonuses'], 1):
                if not all(k in bonus for k in ['leadin', 'parts', 'answers']):
                    print(f"Skipping malformed bonus at index {i-1}: {json.dumps(bonus, indent=2)}")
                    continue
                
                # Create a single question entry for the bonus
                bonus_question = Question(
                    tournament_id=tournament_id,
                    stage_id=stage_id,
                    round=round_number,
                    question_type='bonus',
                    question_text=bonus.get('leadin', ''),
                    answer='',  # Main answer is not used for bonuses
                    question_number=bonus.get('number'),
                    is_bonus=True,
                    bonus_part=0,  # Main bonus part
                    parts=bonus.get('parts', []),
                    answers=bonus.get('answers', []),
                    category=bonus.get('category'),
                    subcategory=bonus.get('subcategory'),
                    alternate_subcategory=bonus.get('alternate_subcategory')
                )
                db.session.add(bonus_question)
                
                # Add individual bonus parts as separate questions
                for part_num in range(len(bonus.get('parts', []))):
                    if part_num < len(bonus.get('answers', [])):
                        bonus_part = Question(
                            tournament_id=tournament_id,
                            stage_id=stage_id,
                            round=round_number,
                            question_type='bonus_part',
                            question_text=bonus['parts'][part_num],
                            answer=bonus['answers'][part_num],
                            question_number=bonus.get('number'),
                            is_bonus=True,
                            bonus_part=part_num + 1,  # 1, 2, or 3
                            parts=[bonus['parts'][part_num]],
                            answers=[bonus['answers'][part_num]],
                            category=bonus.get('category'),
                            subcategory=bonus.get('subcategory'),
                            alternate_subcategory=bonus.get('alternate_subcategory')
                        )
                        db.session.add(bonus_part)
                
                if i % 10 == 0 or i == bonus_count:
                    print(f"Added {i}/{bonus_count} bonuses to database")
        
        db.session.commit()
        success_msg = f"Successfully processed packet with {tossup_count} tossups and {bonus_count} bonuses"
        print(success_msg)
        flash(success_msg, 'success')
        
    except subprocess.TimeoutExpired as e:
        error_msg = f"Packet processing timed out after 5 minutes: {str(e)}"
        print(f"Error: {error_msg}")
        flash(error_msg, 'danger')
    except FileNotFoundError as e:
        error_msg = f"Required file not found: {str(e)}"
        print(f"Error: {error_msg}")
        flash(error_msg, 'danger')
    except Exception as e:
        error_msg = f"Error processing packet: {str(e)}"
        print(f"Error: {error_msg}")
        import traceback
        traceback.print_exc()  # Print full traceback
        flash(f'Error: {str(e)}', 'danger')
    finally:
        # Clean up files
        print("\n=== Cleaning up files ===")
        try:
            # Remove the original file
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Removed file: {file_path}")
            
            # Remove the output directory
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir)
                print(f"Removed directory: {output_dir}")
                
            # Remove the temp directory if empty
            if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                os.rmdir(temp_dir)
                print(f"Removed empty directory: {temp_dir}")
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")
    
    print("=== Packet upload process completed ===\n")
    redirect_url = url_for('admin.tournament_details', tournament_id=tournament_id)
    print(f"Redirecting to: {redirect_url}")
    return redirect(redirect_url)

@admin_bp.route('/manual_seed_teams/<int:tournament_id>/<int:stage_id>', methods=['POST'])
@admin_login_required
def manual_seed_teams(tournament_id, stage_id):
    try:
        tournament = Tournament.query.get_or_404(tournament_id)
        
        # Get the format data to validate placeholders
        format_data = json.loads(tournament.format_json)
        stage = next((s for s in format_data.get('tournament_format', {}).get('stages', []) 
                     if s.get('stage_id') == stage_id), None)
        
        if not stage:
            flash(f'Stage {stage_id} not found in tournament format', 'error')
            return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
        # Get all placeholders for this stage
        placeholders = []
        for rnd in stage.get('rounds', []):
            for pairing in rnd.get('pairings', []):
                for team in pairing.get('teams', []):
                    if team and team not in placeholders:
                        placeholders.append(team)
        
        # Get all preliminary team aliases to maintain consistency
        prelim_teams = {
            alias.team_id: alias.team_name
            for alias in TeamAlias.query.filter_by(
                tournament_id=tournament.id,
                stage_id=1  # Preliminary stage
            ).all()
        }
        
        # Process each placeholder from the form
        for placeholder in placeholders:
            team_id = request.form.get(f'team_{placeholder}')
            
            if team_id and team_id in prelim_teams:
                # Always use the team's original name from prelims
                team_name = prelim_teams[team_id]
                
                # Check if this placeholder already has an alias
                existing_alias = TeamAlias.query.filter_by(
                    tournament_id=tournament.id,
                    placeholder=placeholder,
                    stage_id=stage_id
                ).first()
                
                if existing_alias:
                    # Update existing assignment
                    existing_alias.team_name = team_name
                    existing_alias.team_id = team_id
                else:
                    # Create new assignment
                    alias = TeamAlias(
                        team_name=team_name,
                        team_id=team_id,
                        stage_id=stage_id,
                        tournament_id=tournament.id,
                        placeholder=placeholder
                    )
                    db.session.add(alias)
        
        db.session.commit()
        flash(f'Successfully updated team assignments for {stage.get("stage_name", f"Stage {stage_id}")}', 'success')
        return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in manual_seed_teams: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('An error occurred while updating team assignments', 'error')
        return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
    
    return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))

@admin_bp.route('/auto_assign_playoff/<int:tournament_id>')
@admin_login_required
def auto_assign_playoff(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    auto_assign_playoff_seeding(tournament)
    flash("Playoff seeding automatically assigned based on ranking.", "success")
    return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))

@admin_bp.route('/logout')
def logout():
    session.pop('admin_id', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('admin.login'))

# Export the upload_round_file function for CSRF exemption
__all__ = ['admin_bp', 'upload_round_file']
