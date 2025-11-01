from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from flask_login import login_required, current_user, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, validators
from wtforms.validators import DataRequired
from extensions import db
from models import Tournament, TeamAlias, Game, Player, Question, Admin, Reader, ReaderTournament, Alert, RoomAlias
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
from sqlalchemy import text, inspect, or_
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
            admin.set_password('password')  # Default password
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

class AdminLoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign in')

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in, redirect to dashboard
    if 'admin_id' in session:
        admin = Admin.query.get(session['admin_id'])
        if admin:
            if admin.needs_password_change:
                return redirect(url_for('admin.change_password'))
            return redirect(url_for('admin.dashboard'))
    
    form = AdminLoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        try:
            admin = Admin.query.filter_by(username=username).first()
            if admin and admin.check_password(password):
                login_user(admin)
                session['admin_id'] = admin.id
                session.permanent = True  # Make the session persistent
                
                # Check if password needs to be changed
                if admin.needs_password_change:
                    flash('You must change your password before continuing.', 'warning')
                    return redirect(url_for('admin.change_password'))
                
                flash('Login successful!', 'success')
                
                # Redirect to the dashboard or the originally requested page
                next_page = request.args.get('next')
                return redirect(next_page or url_for('admin.dashboard'))
            else:
                flash('Invalid username or password', 'danger')
        except Exception as e:
            print(f"Login error: {str(e)}")
            db.session.rollback()
            flash('An error occurred during login. Please try again.', 'danger')
    
    return render_template('admin/login.html', form=form)

@admin_bp.route('/dashboard', methods=['GET', 'POST'], endpoint='dashboard')
@admin_login_required
def dashboard():
    form = CreateTournamentForm()
    try:
        # Get tournaments and formats
        tournaments = Tournament.query.order_by(Tournament.date.desc()).all()
        
        # Get available formats from the formats directory
        formats_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'formats')
        formats = []
        if os.path.exists(formats_dir):
            formats = [f.split('.')[0] for f in os.listdir(formats_dir) if f.endswith('.json')]
        
        # Update the format choices in the form
        form.format.choices = [(f, f) for f in formats]
        
        if form.validate_on_submit():
            try:
                # Handle form submission
                format_name = form.format.data
                format_path = os.path.join(formats_dir, f'{format_name}.json')
                
                if not os.path.exists(format_path):
                    flash('Selected format not found', 'danger')
                    return redirect(url_for('admin.dashboard'))
                
                with open(format_path, 'r') as f:
                    format_json = json.dumps(json.load(f))  # Convert to string for storage
                
                # Create and save tournament
                new_tournament = Tournament(
                    name=form.name.data,
                    date=datetime.strptime(form.date.data, '%Y-%m-%d').date(),
                    location=form.location.data,
                    format_json=format_json
                )
                
                db.session.add(new_tournament)
                db.session.commit()
                
                flash(f'Tournament "{form.name.data}" created successfully!', 'success')
                return redirect(url_for('admin.dashboard'))
                
            except Exception as e:
                db.session.rollback()
                print(f"Error creating tournament: {str(e)}")
                flash('An error occurred while creating the tournament', 'danger')
        return render_template('admin/dashboard.html', 
                            tournaments=tournaments, 
                            formats=formats,
                            form=form,
                            current_date=datetime.now().strftime('%Y-%m-%d'))
                            
    except Exception as e:
        db.session.rollback()
        print(f"Error in dashboard: {str(e)}")
        flash(f'An error occurred while loading the dashboard: {str(e)}', 'danger')
        return render_template('admin/dashboard.html', 
                            tournaments=[], 
                            formats=[],
                            form=CreateTournamentForm(),
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
        # Import the room utility function
        from utils.room_utils import get_room_display_name
        
        # Load tournament with reader assignments
        tournament = Tournament.query.options(
            db.joinedload(Tournament.reader_assignments).joinedload(ReaderTournament.reader)
        ).get_or_404(tournament_id)
        
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
                    # success_msg = f'Successfully assigned team name "{team_name}" to {team_id} with {len(player_names) if players_str else 0} players'
                    # current_app.logger.info(success_msg)
                    # flash(success_msg, 'success')
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
        
        # Get question counts for each round (separate tossups and bonuses)
        question_counts = {}
        tossup_counts = {}
        bonus_counts = {}
        questions = Question.query.filter_by(tournament_id=tournament_id).all()
        for q in questions:
            key = (q.stage, q.round)
            question_counts[key] = question_counts.get(key, 0) + 1
            
            # Count tossups and bonuses separately
            if not q.is_bonus:
                tossup_counts[key] = tossup_counts.get(key, 0) + 1
            else:
                bonus_counts[key] = bonus_counts.get(key, 0) + 1
        
        # Get list of assigned room numbers, ensuring it's always a list
        assigned_rooms = [ra.room_number for ra in tournament.reader_assignments] if tournament.reader_assignments else []
        
        # Get room aliases for the tournament
        room_aliases = {}
        for alias in tournament.room_aliases:
            room_aliases[alias.room_number] = alias.room_name
        
        # Import the room utility function
        from utils.room_utils import get_room_display_name
        
        # Render the template with the processed games
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
                           question_counts=question_counts,
                           tossup_counts=tossup_counts,
                           bonus_counts=bonus_counts,
                           assigned_rooms=assigned_rooms,
                           room_aliases=room_aliases,
                           get_room_display_name=get_room_display_name)
                           
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
                # msg = f'Successfully created {games_created} games for stage {stage_id}!'
                print(f"   {msg}")
                # flash(msg, 'success')
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
                # flash(f'Successfully created {games_created} new games for stage {stage_id}', 'success')
                success = True
            else:
                print("No new games were created")
                # flash('No new games were created - all games already exist', 'info')
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
                # current_app.logger.info(f"Successfully created {games_created} games for stage {stage_id}")
                pass  # Added to fix empty try block
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
                ('modules/docx_to_txt.py', 'file'),
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
                
            # Save the uploaded file to p-docx directory
            file_path = p_docx_dir / filename
            print(f"\n=== Saving uploaded file ===")
            print(f"Saving to: {file_path}")
            
            try:
                # Ensure the directory exists with proper permissions
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Set directory permissions (rwxr-xr-x)
                os.chmod(file_path.parent, 0o755)
                
                # Save the file content
                file.save(str(file_path))
                
                # Set file permissions (rw-r--r--)
                os.chmod(file_path, 0o644)
                
                print(f"File saved successfully: {file_path}")
                print(f"File size: {file_path.stat().st_size} bytes")
                print(f"File permissions: {oct(file_path.stat().st_mode)[-3:]}")
                
                # Verify the file was saved
                if not file_path.exists() or file_path.stat().st_size == 0:
                    error_msg = f"Failed to save file or file is empty: {file_path}"
                    print(error_msg)
                    raise IOError(error_msg)
                    
            except Exception as e:
                error_msg = f"Error saving file: {str(e)}"
                print(error_msg)
                print(f"File path: {file_path}")
                print(f"Parent directory exists: {file_path.parent.exists()}")
                if file_path.parent.exists():
                    print(f"Parent directory permissions: {oct(file_path.parent.stat().st_mode)[-3:]}")
                raise Exception(error_msg) from e
            
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
            
            # Import the docx_to_txt module directly
            import sys
            # Add the parent directory of the modules directory to Python path
            sys.path.insert(0, str(parser_dir))
            try:
                from modules.docx_to_txt import main as convert_docx_to_txt
            except ImportError as e:
                print(f"Error importing docx_to_txt: {e}")
                print(f"Current sys.path: {sys.path}")
                print(f"Looking for module in: {parser_dir / 'modules'}")
                raise
            
            # Set the output file path
            output_file = packets_dir / f"{file_path.stem}.txt"
            
            print(f"\n=== Converting {file_path} to text ===")
            print(f"Input file: {file_path}")
            print(f"Output file: {output_file}")
            
            # Create the output directory if it doesn't exist
            os.makedirs(packets_dir, exist_ok=True)
            
            # Run the conversion
            try:
                convert_docx_to_txt(str(file_path), str(output_file))
                print("Conversion completed successfully")
            except Exception as e:
                error_msg = f"Error converting file: {str(e)}"
                print(error_msg)
                raise Exception(error_msg) from e
            
            # Verify the output file was created
            if not output_file.exists() or output_file.stat().st_size == 0:
                raise Exception(f"Output file was not created or is empty: {output_file}")
                
            print(f"Successfully processed document. Output: {output_file}")
            
            # Import the packet_parser module
            import os
            
            # Store the current working directory
            original_cwd = os.getcwd()
            
            try:
                # Change to the parser directory to ensure relative imports work
                os.chdir(str(parser_dir))
                
                # Add the parser directory to the Python path
                sys.path.insert(0, str(parser_dir))
                
                    # Import the Parser class directly
                from packet_parser import Parser, ensure_directories_exist
                
                # Set up input and output directories with absolute paths
                input_dir = os.path.abspath(packets_dir)  # Where we saved the .txt file
                output_dir = os.path.abspath(output_dir)  # Where we want the JSON output
                
                # Get the settings from the form
                has_question_numbers = request.form.get('has_question_numbers') == 'y'
                has_category_tags = request.form.get('has_category_tags') == 'y'
                
                print(f"\n=== Running packet_parser ===")
                print(f"Input directory: {input_dir}")
                print(f"Output directory: {output_dir}")
                print(f"Has question numbers: {has_question_numbers}")
                print(f"Has category tags: {has_category_tags}")
                
                # Verify the input directory exists and has files
                if not os.path.exists(input_dir):
                    raise FileNotFoundError(f"Input directory not found: {input_dir}")
                
                input_files = os.listdir(input_dir)
                print(f"Found {len(input_files)} files in input directory")
                if not input_files:
                    raise FileNotFoundError(f"No files found in input directory: {input_dir}")
                
                # Ensure output directory exists
                os.makedirs(output_dir, exist_ok=True)
                
                # Set up the parser configuration
                bonus_length = 3  # Default value
                always_classify = not has_category_tags  # If no category tags, we'll need to classify
                buzzpoints = False
                classify_unknown = True
                modaq = False
                auto_insert_powermarks = True
                space_powermarks = False
                
                # Create the parser instance
                parser = Parser(
                    has_question_numbers=has_question_numbers,
                    has_category_tags=has_category_tags,
                    bonus_length=bonus_length,
                    buzzpoints=buzzpoints,
                    modaq=modaq,
                    auto_insert_powermarks=auto_insert_powermarks,
                    classify_unknown=classify_unknown,
                    space_powermarks=space_powermarks,
                    always_classify=always_classify,
                    constant_subcategory="",
                    constant_alternate_subcategory=""
                )
                
                # Process each input file
                for filename in sorted(os.listdir(input_dir)):
                    if filename == ".DS_Store":
                        continue
                        
                    input_path = os.path.join(input_dir, filename)
                    output_filename = os.path.splitext(filename)[0] + ".json"
                    output_path = os.path.join(output_dir, output_filename)
                    
                    print(f"Processing {filename} -> {output_filename}")
                    
                    # Read the input file
                    with open(input_path, 'r', encoding='utf-8') as f:
                        packet_text = f.read()
                    
                    # Parse the packet
                    try:
                        packet = parser.parse_packet(packet_text, filename)
                        
                        # Write the output
                        with open(output_path, 'w', encoding='utf-8') as f:
                            json.dump(packet, f, indent=2, ensure_ascii=False)
                        
                        print(f"Successfully processed {filename}")
                    except Exception as e:
                        print(f"Error processing {filename}: {str(e)}")
                        raise
                
                print("Packet parsing completed successfully")
                
            except Exception as e:
                # Restore the original working directory before re-raising
                os.chdir(original_cwd)
                print(f"Error in packet parsing: {str(e)}", file=sys.stderr)
                print(f"Current working directory: {os.getcwd()}", file=sys.stderr)
                print(f"Parser directory: {parser_dir}", file=sys.stderr)
                print(f"Input directory: {packets_dir}", file=sys.stderr)
                print(f"Output directory: {output_dir}", file=sys.stderr)
                raise Exception(f"Packet parsing failed: {str(e)}")
            finally:
                # Always restore the original working directory
                os.chdir(original_cwd)
            
            # Find the output JSON file
            print(f"\n=== Looking for output JSON ===")
            import glob
            
            # Convert output_dir to string for glob
            output_dir_str = str(output_dir)
            output_files = glob.glob(os.path.join(output_dir_str, '*.json'))
            print(f"Found {len(output_files)} JSON files in {output_dir}:")
            for f in output_files:
                print(f"  - {f}")
                
            if not output_files:
                error_msg = f"No JSON output file found in {output_dir}"
                print(f"ERROR: {error_msg}")
                print(f"Contents of {output_dir}:")
                try:
                    for f in os.listdir(output_dir_str):
                        f_path = os.path.join(output_dir_str, f)
                        if os.path.isfile(f_path):
                            print(f"  - {f} (size: {os.path.getsize(f_path)} bytes)")
                except Exception as e:
                    print(f"Could not list output directory: {e}")
                raise Exception(error_msg)
            
            # Process the first JSON file found
            json_file = output_files[0]
            print(f"Processing JSON file: {json_file}")
            
            # Read and parse the JSON file
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"Successfully loaded JSON with {len(data.get('tossups', []))} tossups and {len(data.get('bonuses', []))} bonuses")
                
                # Process the JSON data
                tossups = data.get('tossups', [])
                bonuses = data.get('bonuses', [])
                
                print(f"Found {len(tossups)} tossups and {len(bonuses)} bonuses in the JSON file")
            except json.JSONDecodeError as e:
                print(f"ERROR: Failed to parse JSON: {e}")
                print("File content (first 500 chars):")
                with open(json_file, 'r', encoding='utf-8', errors='replace') as f:
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
                import os
                from pathlib import Path
                
                # Remove the uploaded file
                if 'file_path' in locals() and file_path and os.path.exists(str(file_path)):
                    try:
                        os.unlink(str(file_path))
                    except Exception as e:
                        current_app.logger.warning(f"Could not remove {file_path}: {e}")
                
                # Clean up the parser directories
                if 'p_docx_dir' in locals() and p_docx_dir:
                    p_docx_path = str(p_docx_dir)
                    if os.path.exists(p_docx_path) and os.path.isdir(p_docx_path):
                        try:
                            for f in os.listdir(p_docx_path):
                                try:
                                    file_path = os.path.join(p_docx_path, f)
                                    if os.path.isfile(file_path):
                                        os.unlink(file_path)
                                except Exception as e:
                                    current_app.logger.warning(f"Could not remove {file_path}: {e}")
                        except Exception as e:
                            current_app.logger.warning(f"Could not list directory {p_docx_path}: {e}")
                
                if 'output_dir' in locals() and output_dir:
                    output_path = str(output_dir)
                    if os.path.exists(output_path) and os.path.isdir(output_path):
                        try:
                            for f in os.listdir(output_path):
                                try:
                                    file_path = os.path.join(output_path, f)
                                    if os.path.isfile(file_path) and file_path.endswith('.json'):
                                        # Don't delete JSON files as they may be needed
                                        continue
                                    if os.path.isfile(file_path):
                                        os.unlink(file_path)
                                except Exception as e:
                                    current_app.logger.warning(f"Could not remove {file_path}: {e}")
                        except Exception as e:
                            current_app.logger.warning(f"Could not list directory {output_path}: {e}")
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
        
        # Get current question counts for this round
        current_questions = Question.query.filter_by(
            tournament_id=tournament_id,
            stage=stage_id,
            round=round_number
        ).all()
        
        tossup_count = sum(1 for q in current_questions if not q.is_bonus)
        bonus_count = sum(1 for q in current_questions if q.is_bonus)
        
        return render_template('admin/upload_round_file.html', 
                            tournament_name=tournament_name, 
                            tournament_id=tournament_id,
                            stage_id=stage_id, 
                            round_number=round_number,
                            tossup_count=tossup_count,
                            bonus_count=bonus_count)

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

@admin_bp.route('/tournament/<int:tournament_id>/assign_reader', methods=['POST'])
@admin_login_required
def assign_reader(tournament_id):
    email = request.form.get('email')
    room_number = request.form.get('room_number', type=int)
    
    if not email or room_number is None:
        flash('Email and room number are required', 'danger')
        return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
    
    tournament = Tournament.query.get_or_404(tournament_id)
    max_rooms = tournament.get_max_rooms()
    
    if room_number < 1 or room_number > max_rooms:
        flash(f'Room number must be between 1 and {max_rooms}', 'danger')
        return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
    
    reader = Reader.query.filter_by(email=email).first()
    if not reader:
        flash(f'No reader found with email: {email}', 'danger')
        return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
    
    # Check if reader is already assigned to this tournament
    existing_assignment = next(
        (ra for ra in tournament.reader_assignments if ra.reader_id == reader.id), 
        None
    )
    
    if existing_assignment:
        if existing_assignment.room_number == room_number:
            flash(f'Reader {email} is already assigned to room {room_number}', 'warning')
        else:
            existing_assignment.room_number = room_number
            db.session.commit()
            flash(f'Updated {email} to room {room_number}', 'success')
        return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
    
    try:
        # Create a new ReaderTournament association with room number
        from models.reader import ReaderTournament
        assignment = ReaderTournament(
            reader_id=reader.id,
            tournament_id=tournament_id,
            room_number=room_number
        )
        db.session.add(assignment)
        db.session.commit()
        flash(f'Successfully assigned {email} to room {room_number}', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error assigning reader: {str(e)}')
        flash('An error occurred while assigning the reader', 'danger')
        
    return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))

@admin_bp.route('/tournament/<int:tournament_id>/remove_reader/<int:reader_id>', methods=['POST'])
@admin_login_required
def remove_reader(tournament_id, reader_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    reader = Reader.query.get_or_404(reader_id)
    
    if reader not in tournament.readers:
        flash('Reader is not assigned to this tournament', 'warning')
        return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
    
    try:
        tournament.readers.remove(reader)
        db.session.commit()
        flash(f'Successfully removed {reader.email} from the tournament', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while removing the reader', 'danger')
        
    return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))

@admin_bp.route('/delete_round_questions/<int:tournament_id>/<stage_id>/<int:round_number>', methods=['POST'])
@admin_login_required
def delete_round_questions(tournament_id, stage_id, round_number):
    """Delete all questions for a specific tournament stage and round"""
    try:
        # Delete all questions for this tournament, stage, and round
        deleted_count = Question.query.filter_by(
            tournament_id=tournament_id,
            stage=stage_id,
            round=round_number
        ).delete()
        
        db.session.commit()
        
        flash(f'Successfully deleted {deleted_count} questions for Stage {stage_id}, Round {round_number}', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting questions: {str(e)}', 'danger')
    
    return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))

@admin_bp.route('/logout')
@admin_login_required
def logout():
    session.pop('admin_id', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('admin.login'))

@admin_bp.route('/admin/create', methods=['GET', 'POST'])
@admin_login_required
def create_admin():
    if request.method == 'POST':
        username = request.form.get('username')
        
        if not username:
            flash('Username is required', 'danger')
            return redirect(url_for('admin.create_admin'))
            
        try:
            # Check if admin already exists
            if Admin.query.filter_by(username=username).first():
                flash('An admin with that username already exists', 'danger')
                return redirect(url_for('admin.create_admin'))
                
            # Create new admin with default password
            new_admin = Admin(username=username)
            new_admin.set_password('password')  # Default password
            db.session.add(new_admin)
            db.session.commit()
            
            flash(f'Admin account for {username} created successfully!', 'success')
            return redirect(url_for('admin.list_admins'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error creating admin: {str(e)}")
            flash('An error occurred while creating the admin account', 'danger')
    
    return render_template('admin/create_admin.html')

@admin_bp.route('/admin/list')
@admin_login_required
def list_admins():
    admins = Admin.query.order_by(Admin.username).all()
    return render_template('admin/list_admins.html', admins=admins)

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[
        validators.DataRequired(message='Current password is required')
    ])
    new_password = PasswordField('New Password', validators=[
        validators.DataRequired(message='New password is required'),
        validators.Length(min=8, message='Password must be at least 8 characters long')
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        validators.EqualTo('new_password', message='Passwords must match')
    ])
    submit = SubmitField('Update Password')

class CreateTournamentForm(FlaskForm):
    name = StringField('Tournament Name', validators=[validators.DataRequired()])
    date = StringField('Date', validators=[validators.DataRequired()])
    location = StringField('Location', validators=[validators.DataRequired()])
    format = SelectField('Format', validators=[validators.DataRequired()], choices=[])
    submit = SubmitField('Create Tournament')

@admin_bp.route('/change-password', methods=['GET', 'POST'])
@admin_login_required
def change_password():
    admin = Admin.query.get(session['admin_id'])
    if not admin:
        flash('User not found. Please log in again.', 'danger')
        return redirect(url_for('admin.logout'))
    
    # Check if this is a forced password change
    forced_change = admin.needs_password_change
    
    # Initialize form with fields based on forced change
    form = ChangePasswordForm()
    
    if forced_change:
        # Remove current_password requirement for forced changes
        form.current_password.validators = []
    
    if form.validate_on_submit():
        current_password = form.current_password.data
        new_password = form.new_password.data
        confirm_password = form.confirm_password.data
        
        # For non-forced changes, validate current password
        if not forced_change and not admin.check_password(current_password):
            flash('Current password is incorrect', 'danger')
            return render_template('admin/change_password.html', 
                                 form=form, 
                                 forced_change=forced_change)
            
        # Check if new password is different from current
        if admin.check_password(new_password):
            flash('New password must be different from current password', 'danger')
            return render_template('admin/change_password.html', 
                                 form=form, 
                                 forced_change=forced_change)
            
        try:
            # Update password and reset the needs_password_change flag
            admin.set_password(new_password)
            admin.needs_password_change = False
            db.session.commit()
            
            flash('Password changed successfully!', 'success')
            
            # If this was a forced change, log them in again with the new password
            if forced_change:
                login_user(admin)
                session['admin_id'] = admin.id
                return redirect(url_for('admin.dashboard'))
                
            return redirect(url_for('admin.dashboard'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error changing password: {str(e)}")
            flash('An error occurred while changing your password. Please try again.', 'danger')
    
    return render_template('admin/change_password.html', 
                         form=form, 
                         forced_change=forced_change)

# Add a before_request to check if password needs to be changed
@admin_bp.before_request
def check_password_change():
    # Skip if not logged in or if the endpoint is in the whitelist
    if 'admin_id' not in session or request.endpoint in ['admin.logout', 'admin.change_password', 'static']:
        return
        
    admin = Admin.query.get(session['admin_id'])
    if admin and admin.needs_password_change:
        # Only redirect if not already on the change password page
        if request.endpoint != 'admin.change_password':
            return redirect(url_for('admin.change_password'))

@admin_bp.route('/admin/delete/<int:admin_id>', methods=['POST'])
@admin_login_required
def delete_admin(admin_id):
    # Prevent deleting your own account
    if admin_id == session.get('admin_id'):
        if request.is_json:
            return jsonify({'success': False, 'message': 'You cannot delete your own account while logged in.'}), 400
        flash('You cannot delete your own account while logged in.', 'danger')
        return redirect(url_for('admin.list_admins'))
    
    # Prevent deleting the default admin (ID 1)
    if admin_id == 1:
        if request.is_json:
            return jsonify({'success': False, 'message': 'The default admin account cannot be deleted.'}), 400
        flash('The default admin account cannot be deleted.', 'danger')
        return redirect(url_for('admin.list_admins'))
    
    try:
        admin = Admin.query.get_or_404(admin_id)
        username = admin.username
        db.session.delete(admin)
        db.session.commit()
        
        if request.is_json:
            return jsonify({'success': True, 'message': f'Successfully deleted admin account: {username}'})
            
        flash(f'Successfully deleted admin account: {username}', 'success')
    except Exception as e:
        db.session.rollback()
        error_msg = f'An error occurred while deleting the admin account: {str(e)}'
        print(error_msg)
        
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 500
            
        flash('An error occurred while deleting the admin account.', 'danger')
    
    return redirect(url_for('admin.list_admins'))

@admin_bp.route('/admin/reset-password/<int:admin_id>', methods=['POST'])
@admin_login_required
def reset_admin_password(admin_id):
    try:
        # Get the current admin
        current_admin = Admin.query.get(session['admin_id'])
        if not current_admin:
            return jsonify({'success': False, 'message': 'Session expired. Please log in again.'}), 401
            
        # Get the target admin
        admin = Admin.query.get_or_404(admin_id)
        
        # Prevent resetting your own password this way (use change password instead)
        if admin_id == current_admin.id:
            return jsonify({
                'success': False, 
                'message': 'Please use the Change Password feature to update your own password.'
            }), 400
        
        # Reset the password to 'password' and force change on next login
        admin.set_password('password')
        admin.needs_password_change = True
        
        # Update the updated_at timestamp
        admin.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Password for {admin.username} has been reset. They will be prompted to change it on next login.'
        })
        
    except Exception as e:
        db.session.rollback()
        error_msg = f'Error resetting password: {str(e)}'
        print(error_msg)
        return jsonify({'success': False, 'message': error_msg}), 500

@admin_bp.route('/api/teams/<int:tournament_id>/add_player', methods=['POST'])
@admin_login_required
def add_player_to_team(tournament_id):
    """
    API endpoint to add a player to a team in the admin dashboard.
    Expected JSON payload:
    {
        'team_id': str,  # e.g., 'T1', 'T2', etc.
        'player_name': str,
        'player_number': str (optional)
    }
    """
    current_app.logger.info('\n=== START admin add_player_to_team ===')
    
    try:
        data = request.get_json()
        team_id = data.get('team_id')
        player_name = data.get('player_name')
        player_number = data.get('player_number')
        
        current_app.logger.info(f"Adding player to team - Tournament: {tournament_id}, Team: {team_id}, Player: {player_name}")
        
        if not team_id or not player_name:
            return jsonify({
                'success': False,
                'message': 'Team ID and player name are required'
            }), 400
        
        # Find an existing player on the same team to get their alias_id
        team_players = Player.query.filter(
            Player.team_id == team_id
        ).all()
        
        # Get alias_id from first teammate if available
        alias_id = team_players[0].alias_id if team_players else None
        
        # Check for existing players with same name (case insensitive)
        existing_players = Player.query.filter(
            Player.team_id == team_id,
            db.func.lower(Player.name) == player_name.lower()
        ).all()
        
        if existing_players:
            return jsonify({
                'success': False,
                'message': 'Player with this name already exists on the team',
                'existing_players': [p.id for p in existing_players]
            }), 400
        
        # Create new player with same alias_id as teammates if available
        new_player = Player(
            name=player_name,
            team_id=team_id,
            alias_id=alias_id
        )
        
        if player_number is not None:
            new_player.number = player_number
        
        db.session.add(new_player)
        db.session.commit()
        
        current_app.logger.info(f'Successfully created player with ID: {new_player.id}')
        
        # Get updated player list for the team
        updated_players = [p.name for p in Player.query.filter_by(team_id=team_id).all()]
        
        return jsonify({
            'success': True,
            'player_id': new_player.id,
            'player_name': new_player.name,
            'team_id': team_id,
            'updated_players': updated_players
        })
        
    except Exception as e:
        current_app.logger.error(f'Error in admin add_player_to_team: {str(e)}', exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Failed to add player: {str(e)}'
        }), 500

@admin_bp.route('/api/teams/<int:tournament_id>/delete/<team_id>', methods=['DELETE'])
@admin_login_required
def delete_team(tournament_id, team_id):
    """
    API endpoint to delete a team and all its players from a tournament.
    """
    current_app.logger.info(f'\n=== START delete_team ===\nTournament: {tournament_id}, Team: {team_id}')
    
    try:
        # Verify the tournament exists
        tournament = Tournament.query.get_or_404(tournament_id)
        
        # Get all players in the team
        players = Player.query.filter_by(team_id=team_id).all()
        
        # Get all team aliases for this team in the tournament
        team_aliases = TeamAlias.query.filter_by(
            tournament_id=tournament_id,
            team_id=team_id
        ).all()
        
        # Delete all players in the team
        for player in players:
            db.session.delete(player)
        
        # Delete all team aliases for this team
        for alias in team_aliases:
            db.session.delete(alias)
        
        # Commit the changes
        db.session.commit()
        
        current_app.logger.info(f'Successfully deleted team {team_id}, its players, and aliases')
        
        return jsonify({
            'success': True,
            'message': f'Team {team_id}, its players, and aliases have been deleted',
            'team_id': team_id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error in delete_team: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Failed to delete team: {str(e)}'
        }), 500

@admin_bp.route('/api/teams/<int:tournament_id>/delete_player/<int:player_id>', methods=['DELETE'])
@admin_login_required
def delete_player(tournament_id, player_id):
    """
    API endpoint to delete a player from a team.
    """
    current_app.logger.info(f'\n=== START delete_player ===\nPlayer ID: {player_id}, Tournament: {tournament_id}')
    
    try:
        # Verify the tournament exists
        tournament = Tournament.query.get_or_404(tournament_id)
        
        # Get the player
        player = Player.query.get_or_404(player_id)
        
        # Verify the player belongs to this tournament
        team_alias = TeamAlias.query.get(player.alias_id)
        if not team_alias or team_alias.tournament_id != tournament_id:
            return jsonify({
                'success': False,
                'message': 'Player not found in this tournament'
            }), 404
        
        # Delete the player
        db.session.delete(player)
        db.session.commit()
        
        current_app.logger.info(f'Successfully deleted player {player_id} from team {team_alias.team_id}')
        
        return jsonify({
            'success': True,
            'message': 'Player deleted successfully',
            'player_id': player_id,
            'team_id': team_alias.team_id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error in delete_player: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Failed to delete player: {str(e)}'
        }), 500

@admin_bp.route('/api/teams/<int:tournament_id>/players')
@admin_login_required
def get_team_players(tournament_id):
    """
    API endpoint to get all players for a specific team in a tournament.
    """
    try:
        team_id = request.args.get('team_id')
        if not team_id:
            return jsonify({
                'success': False,
                'message': 'Team ID is required'
            }), 400
            
        # Get all players for this team in the tournament
        players = db.session.query(Player, TeamAlias).join(
            TeamAlias, Player.alias_id == TeamAlias.id
        ).filter(
            TeamAlias.tournament_id == tournament_id,
            Player.team_id == team_id
        ).all()
        
        # Format the response
        players_data = [{
            'id': player.id,
            'name': player.name,
            'team_id': player.team_id,
            'alias_id': player.alias_id
        } for player, _ in players]
        
        return jsonify({
            'success': True,
            'players': players_data
        })
        
    except Exception as e:
        current_app.logger.error(f'Error in get_team_players: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Failed to fetch players: {str(e)}'
        }), 500

@admin_bp.route('/tournament/<int:tournament_id>/game/<int:game_id>/scorecard', methods=['GET', 'POST'])
@admin_login_required
def edit_game_scorecard(tournament_id, game_id):
    """
    View and edit a game's scorecard as an admin.
    """
    game = Game.query.get_or_404(game_id)
    tournament = Tournament.query.get_or_404(tournament_id)
    
    # Verify the game belongs to the tournament
    if game.tournament_id != tournament.id:
        flash("Game does not belong to this tournament", "danger")
        return redirect(url_for('admin.tournament_details', tournament_id=tournament_id))
    
    # Get team names and resolve any dynamic references
    team1_id = game.team1
    team1_display_name = game.team1
    team2_id = game.team2
    team2_display_name = game.team2
    
    # Resolve team references if they are dynamic (e.g., W(S1R1M1))
    if team1_id and str(team1_id).startswith('W('):
        resolved_id, resolved_name, _ = resolve_team_reference(tournament.id, team1_id)
        if resolved_id and resolved_name:
            team1_id = resolved_id
            team1_display_name = resolved_name
    
    if team2_id and str(team2_id).startswith('W('):
        resolved_id, resolved_name, _ = resolve_team_reference(tournament.id, team2_id)
        if resolved_id and resolved_name:
            team2_id = resolved_id
            team2_display_name = resolved_name
    
    # Get all questions for this game
    questions = Question.query.filter_by(game_id=game_id).order_by(Question.id).all()
    
    # Get all players for both teams by joining with TeamAlias
    team1_players = db.session.query(Player).join(
        TeamAlias, Player.alias_id == TeamAlias.id
    ).filter(
        TeamAlias.tournament_id == tournament_id,
        Player.team_id == team1_id
    ).all()
    
    team2_players = db.session.query(Player).join(
        TeamAlias, Player.alias_id == TeamAlias.id
    ).filter(
        TeamAlias.tournament_id == tournament_id,
        Player.team_id == team2_id
    ).all()
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Update game result if provided
            if 'result' in data:
                game.result = data['result']
            
            # Process scorecard data
            if 'scorecard' in data:
                scorecard = data['scorecard']
                
                # Convert the scorecard to JSON string for storage
                game.scorecard = json.dumps(scorecard)
                
                # Update game stats based on scorecard
                team1_score = 0
                team2_score = 0
                
                for tossup in scorecard:
                    # Calculate tossup points
                    for player_id, points in tossup.get('team1', {}).items():
                        team1_score += int(points) if str(points).isdigit() else 0
                    for player_id, points in tossup.get('team2', {}).items():
                        team2_score += int(points) if str(points).isdigit() else 0
                    
                    # Add bonus points
                    team1_score += int(tossup.get('team1Bonus', 0)) if str(tossup.get('team1Bonus', 0)).isdigit() else 0
                    team2_score += int(tossup.get('team2Bonus', 0)) if str(tossup.get('team2Bonus', 0)).isdigit() else 0
                
                # Update game scores
                game.team1_score = team1_score
                game.team2_score = team2_score
                
                # Update result based on scores if not explicitly set
                if 'result' not in data:
                    if team1_score > team2_score:
                        game.result = 1
                    elif team2_score > team1_score:
                        game.result = 2
                    else:
                        game.result = -1  # Tie
            
            db.session.commit()
            return jsonify({
                'status': 'success', 
                'message': 'Scorecard updated successfully',
                'team1_score': game.team1_score,
                'team2_score': game.team2_score,
                'result': game.result
            })
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating scorecard: {str(e)}", exc_info=True)
            return jsonify({'status': 'error', 'message': str(e)}), 400
    
    # For GET request, load the scorecard if it exists
    scorecard = []
    if game.scorecard:
        try:
            scorecard = json.loads(game.scorecard)
        except json.JSONDecodeError:
            current_app.logger.error(f"Invalid scorecard JSON for game {game_id}")
            scorecard = []
    
    # If no scorecard exists, initialize with empty tossups
    if not scorecard:
        # Default to 20 tossups if no questions exist, otherwise use the number of questions
        num_tossups = len(questions) if questions else 20
        scorecard = [{
            'team1': {},
            'team2': {},
            'team1Bonus': 0,
            'team2Bonus': 0,
            'buzzes': {}
        } for _ in range(num_tossups)]
    
    return render_template(
        'admin/scorecard_editor.html',
        tournament=tournament,
        game=game,
        team1_id=team1_id,
        team1_name=team1_display_name,
        team2_id=team2_id,
        team2_name=team2_display_name,
        questions=questions,
        team1_players=team1_players,
        team2_players=team2_players,
        scorecard=scorecard
    )

# Helper function to resolve team references (similar to the one in reader_controller)
def resolve_team_reference(tournament_id, team_ref, depth=0, max_depth=5):
    """
    Resolve a team reference like 'W(S2R1M4)' to an actual team ID.
    
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
    if depth > max_depth:
        return None, None, None
        
    try:
        # Handle both full references (W(S2R1M4)) and just the code (S2R1M4)
        if team_ref.startswith(('W(', 'L(')) and team_ref.endswith(')'):
            ref = team_ref[2:-1]  # Remove W( or L( and )
            is_winner = team_ref.startswith('W')
        else:
            ref = team_ref
            is_winner = True  # Default to winner if not specified
            
        # Parse the reference
        stage = int(ref[1])
        round_num = int(ref[3])
        match_num = int(ref[5:]) if 'M' in ref else int(ref[ref.index('M')+1:])
        
        # Find the game
        game = Game.query.filter_by(
            tournament_id=tournament_id,
            stage_id=stage,
            round_number=round_num,
            match_number=match_num
        ).first()
        
        if not game:
            return None, None, None
            
        # If game is complete, get the winner/loser
        if game.result is not None and game.result > 0:
            winning_team = game.team1 if game.result == 1 else game.team2
            team_name = game.team1_name if game.result == 1 else game.team2_name
            return winning_team, team_name, None
        else:
            # Game is not complete yet, return pending info
            team1_name = game.team1
            team2_name = game.team2
            
            # Resolve team names if they are also references
            if team1_name and str(team1_name).startswith('W('):
                _, resolved_name, _ = resolve_team_reference(tournament_id, team1_name, depth+1, max_depth)
                if resolved_name:
                    team1_name = resolved_name
                    
            if team2_name and str(team2_name).startswith('W('):
                _, resolved_name, _ = resolve_team_reference(tournament_id, team2_name, depth+1, max_depth)
                if resolved_name:
                    team2_name = resolved_name
            
            return None, None, {
                'ref': team_ref,
                'game': game,
                'team1': team1_name,
                'team2': team2_name
            }
            
    except Exception as e:
        current_app.logger.error(f"Error resolving team reference {team_ref}: {str(e)}")
        return None, None, None

@admin_bp.route('/tournament/<int:tournament_id>/games')
@admin_login_required
def list_tournament_games(tournament_id):
    """
    List all games for a tournament with options to edit scorecards.
    """
    tournament = Tournament.query.get_or_404(tournament_id)
    
    # Get all games for this tournament with related data
    games = Game.query.filter_by(tournament_id=tournament_id)\
                     .order_by(Game.stage_id, Game.round_number, Game.id)\
                     .all()
    
    # Get all team aliases for this tournament
    aliases = TeamAlias.query.filter_by(tournament_id=tournament_id).all()
    alias_map = {alias.id: alias.team_name for alias in aliases}
    
    # Organize games by stage and round
    games_by_stage = {}
    for game in games:
        # Ensure the game has all necessary attributes
        if not hasattr(game, 'stage_id') or game.stage_id is None:
            game.stage_id = 1
        if not hasattr(game, 'round_number') or game.round_number is None:
            game.round_number = 1
            
        stage_id = game.stage_id
        round_num = game.round_number
        
        # Initialize the stage and round structures if they don't exist
        if stage_id not in games_by_stage:
            games_by_stage[stage_id] = {}
        if round_num not in games_by_stage[stage_id]:
            games_by_stage[stage_id][round_num] = []
        
        # Add resolved team names to the game object
        def get_team_name(team_ref):
            if not team_ref:
                return None
            if team_ref.startswith(('W(', 'L(')):
                _, name, _ = resolve_team_reference(tournament_id, team_ref)
                return name or team_ref
            # Check if it's a team alias ID
            try:
                alias_id = int(team_ref.replace('T', ''))
                return alias_map.get(alias_id, team_ref)
            except (ValueError, AttributeError):
                return team_ref
        
        game.team1_name = get_team_name(game.team1)
        game.team2_name = get_team_name(game.team2)
        
        # Add the game to the appropriate stage and round
        games_by_stage[stage_id][round_num].append(game)
        
        # Set a match number based on position in the round
        game._match_number = len(games_by_stage[stage_id][round_num])
    
    # Get format data for stage names
    format_data = json.loads(tournament.format_json) if tournament.format_json else {}
    
    return render_template(
        'admin/tournament_games.html',
        tournament=tournament,
        games_by_stage=games_by_stage,
        format_data=format_data
    )

# Export the upload_round_file function for CSRF exemption
@admin_bp.route('/alerts', methods=['GET'])
@login_required
def get_alerts():
    """
    API endpoint to get all active (unresolved) alerts.
    Optional query parameters:
        - tournament_id: Filter alerts by tournament
    """
    try:
        current_app.logger.info('GET /admin/alerts endpoint called')
        tournament_id = request.args.get('tournament_id', type=int)
        
        # Start with base query for unresolved alerts
        query = Alert.query.filter_by(resolved=False)
        
        # If tournament_id is provided, filter by tournament
        if tournament_id:
            query = query.join(Game).filter(Game.tournament_id == tournament_id)
        
        # Order by creation time (newest first)
        alerts = query.order_by(Alert.created_at.desc()).all()
        
        current_app.logger.info(f'Found {len(alerts)} active alerts')
        
        # Convert alerts to dictionary format for JSON serialization
        alerts_data = [alert.to_dict() for alert in alerts]
        
        response_data = {
            'success': True,
            'alerts': alerts_data
        }
        
        current_app.logger.info('Successfully retrieved alerts')
        response = jsonify(response_data)
        response.headers['Content-Type'] = 'application/json'
        return response
        
    except Exception as e:
        current_app.logger.error(f'Error in get_alerts: {str(e)}', exc_info=True)
        response = jsonify({
            'success': False,
            'error': 'Failed to fetch alerts',
            'details': str(e)
        })
        response.status_code = 500
        response.headers['Content-Type'] = 'application/json'
        return response
        return response

@admin_bp.route('/alerts/<int:alert_id>/resolve', methods=['POST'])
@login_required
def resolve_alert(alert_id):
    """
    API endpoint to mark an alert as resolved.
    """
    try:
        alert = Alert.query.get_or_404(alert_id)
        alert.resolved = True
        alert.resolved_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Alert resolved successfully'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error resolving alert {alert_id}: {str(e)}')
        return jsonify({
            'success': False,
            'error': 'Failed to resolve alert'
        }), 500

@admin_bp.route('/tournament/<int:tournament_id>/game/<int:game_id>/simple-scorecard', methods=['GET', 'POST'])
@admin_login_required
def simple_scorecard_editor(tournament_id, game_id):
    """
    Simplified scorecard editor for admins.
    Allows editing all scorecard fields except buzzes.
    """
    tournament = Tournament.query.get_or_404(tournament_id)
    game = Game.query.get_or_404(game_id)
    
    # Get teams and players
    team1_id = game.team1
    team2_id = game.team2
    
    # Get team display names (handle both direct names and references)
    team1_display_name = team1_id
    team2_display_name = team2_id
    
    # Resolve team references if needed (e.g., W(S2R1M4))
    if team1_id and (str(team1_id).startswith('W(') or str(team1_id).startswith('L(')):
        _, resolved_name, _ = resolve_team_reference(tournament_id, team1_id)
        if resolved_name:
            team1_display_name = resolved_name
            
    if team2_id and (str(team2_id).startswith('W(') or str(team2_id).startswith('L(')):
        _, resolved_name, _ = resolve_team_reference(tournament_id, team2_id)
        if resolved_name:
            team2_display_name = resolved_name
    
    # Get players for each team
    team1_players = Player.query.filter_by(tournament_id=tournament_id, team_id=team1_id).all()
    team2_players = Player.query.filter_by(tournament_id=tournament_id, team_id=team2_id).all()
    
    # Get questions for this game (if any)
    questions = Question.query.filter_by(
        tournament_id=tournament_id,
        stage_id=game.stage_id,
        round_number=game.round_number
    ).order_by(Question.id).all()
    
    # Handle POST request to save and finalize the scorecard
    if request.method == 'POST':
        try:
            data = request.get_json()
            scorecard = data.get('scorecard', [])
            result = data.get('result', 0)
            
            # Calculate final scores
            team1_score = 0
            team2_score = 0
            
            for cycle in scorecard:
                # Add up tossup points
                for player_id, points in cycle.get('team1', {}).items():
                    team1_score += int(points) if str(points).lstrip('-').isdigit() else 0
                for player_id, points in cycle.get('team2', {}).items():
                    team2_score += int(points) if str(points).lstrip('-').isdigit() else 0
                
                # Add bonus points
                team1_score += int(cycle.get('team1Bonus', 0))
                team2_score += int(cycle.get('team2Bonus', 0))
            
            # Set the game result based on scores if not explicitly set
            if result == 0:
                if team1_score > team2_score:
                    result = 1
                elif team2_score > team1_score:
                    result = 2
                else:
                    result = -1  # Tie
            
            # Update the game with the final scorecard and result
            game.scorecard = json.dumps(scorecard)
            game.result = result
            game.team1_score = team1_score
            game.team2_score = team2_score
            
            db.session.commit()
            return jsonify({'success': True})
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error finalizing scorecard: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 400
    
    # For GET request, load the scorecard if it exists
    scorecard = []
    if game.scorecard:
        try:
            scorecard = json.loads(game.scorecard)
        except json.JSONDecodeError:
            current_app.logger.error(f"Invalid scorecard JSON for game {game_id}")
            scorecard = []
    
    # If no scorecard exists, initialize with empty cycles
    if not scorecard:
        # Default to 20 tossups if no questions exist, otherwise use the number of questions
        num_tossups = len(questions) if questions else 20
        scorecard = [{
            'team1': {},
            'team2': {},
            'team1Bonus': 0,
            'team2Bonus': 0,
            'buzzes': {}
        } for _ in range(num_tossups)]
    
    return render_template(
        'admin/simple_scorecard_editor.html',
        tournament=tournament,
        game=game,
        team1_id=team1_id,
        team1_name=team1_display_name,
        team2_id=team2_id,
        team2_name=team2_display_name,
        questions=questions,
        team1_players=team1_players,
        team2_players=team2_players,
        scorecard=scorecard
    )

# Room Management Routes

class RoomAliasForm(FlaskForm):
    """Form for creating or updating room aliases."""
    room_number = StringField('Room Number', validators=[DataRequired()])
    room_name = StringField('Room Name', validators=[DataRequired()])
    submit = SubmitField('Save')

@admin_bp.route('/tournament/<int:tournament_id>/rooms', methods=['GET'])
@admin_login_required
def manage_rooms(tournament_id):
    """Manage room aliases for a tournament."""
    tournament = Tournament.query.get_or_404(tournament_id)
    room_aliases = RoomAlias.query.filter_by(tournament_id=tournament_id).all()
    
    # Get all rooms that have readers assigned but no alias yet
    assigned_rooms = db.session.query(
        ReaderTournament.room_number
    ).filter(
        ReaderTournament.tournament_id == tournament_id,
        ReaderTournament.room_number.isnot(None)
    ).distinct().all()
    
    # Convert to a set of room numbers
    assigned_room_numbers = {r.room_number for r in assigned_rooms}
    
    # Find rooms that don't have aliases yet
    rooms_without_aliases = [
        {'room_number': num} 
        for num in assigned_room_numbers 
        if not any(alias.room_number == num for alias in room_aliases)
    ]
    
    form = RoomAliasForm()
    return render_template(
        'admin/room_management.html',
        tournament=tournament,
        room_aliases=room_aliases,
        rooms_without_aliases=rooms_without_aliases,
        form=form
    )

@admin_bp.route('/tournament/<int:tournament_id>/rooms/add', methods=['POST'])
@admin_login_required
def add_room_alias(tournament_id):
    """Add a new room alias."""
    tournament = Tournament.query.get_or_404(tournament_id)
    form = RoomAliasForm()
    
    if form.validate_on_submit():
        try:
            room_number = int(form.room_number.data)
            room_alias = RoomAlias(
                room_number=room_number,
                room_name=form.room_name.data,
                tournament_id=tournament_id
            )
            
            # Check if alias already exists for this room
            existing = RoomAlias.query.filter_by(
                tournament_id=tournament_id,
                room_number=room_number
            ).first()
            
            if existing:
                flash(f'Alias for Room {room_number} already exists', 'warning')
            else:
                db.session.add(room_alias)
                db.session.commit()
                flash(f'Added alias for Room {room_number}', 'success')
                
        except ValueError:
            flash('Room number must be a number', 'danger')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Error adding room alias: {str(e)}')
            flash('An error occurred while adding the room alias', 'danger')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'Error in {field}: {error}', 'danger')
    
    return redirect(url_for('admin.manage_rooms', tournament_id=tournament_id))

@admin_bp.route('/tournament/<int:tournament_id>/rooms/<int:room_number>/delete', methods=['POST'])
@admin_login_required
def delete_room_alias(tournament_id, room_number):
    """Delete a room alias."""
    room_alias = RoomAlias.query.filter_by(
        tournament_id=tournament_id,
        room_number=room_number
    ).first_or_404()
    
    try:
        db.session.delete(room_alias)
        db.session.commit()
        flash(f'Removed alias for Room {room_number}', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error deleting room alias: {str(e)}')
        flash('An error occurred while removing the room alias', 'danger')
    
    return redirect(url_for('admin.manage_rooms', tournament_id=tournament_id))

__all__ = ['admin_bp', 'upload_round_file']
