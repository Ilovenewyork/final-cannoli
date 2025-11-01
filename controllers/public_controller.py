from flask import Blueprint, render_template, abort, current_app
from datetime import datetime
from models import db
from models.tournament import Tournament
from models.team_alias import TeamAlias
from models.player import Player
import json
from models.game import Game
from collections import defaultdict
import logging

public_bp = Blueprint('public', __name__, template_folder='../templates/public')

@public_bp.route('/schedule')
@public_bp.route('/schedule/')
def list_tournaments():
    """Display a list of all tournaments, separated into upcoming and past."""
    now = datetime.now().date()
    
    # Get all tournaments ordered by date (newest first)
    all_tournaments = Tournament.query.order_by(Tournament.date.desc()).all()
    
    # Separate into upcoming and past tournaments
    upcoming_tournaments = [t for t in all_tournaments if t.date >= now]
    past_tournaments = [t for t in all_tournaments if t.date < now]
    
    return render_template('tournaments_list.html',
                         upcoming_tournaments=upcoming_tournaments,
                         past_tournaments=past_tournaments,
                         now=datetime.now())

# Removed old team route (/schedule/<teamname>)
@public_bp.route('/schedule/<int:tournament_id>/<teamname>')
def team_schedule(tournament_id, teamname):
    tournament = Tournament.query.get(tournament_id)
    if not tournament:
        abort(404, description="Tournament not found")
    format_data = tournament.format
    aliases = TeamAlias.query.filter_by(tournament_id=tournament.id, stage_id=1).all()
    alias_dict = {alias.team_id: alias.team_name for alias in aliases}
    
    # Get room aliases for the tournament
    room_aliases = {alias.room_number: alias.room_name for alias in tournament.room_aliases}
    
    # Import the room utility function
    from utils.room_utils import get_room_display_name
    
    schedule_resolved = {}
    stages = format_data['tournament_format']['stages']
    for stage in stages:
        stage_name = stage.get('stage_name')
        rounds = stage.get('rounds', [])
        if stage.get('stage_id') == 1:
            resolved_rounds = []
            for rnd in rounds:
                round_label = rnd.get('round_in_stage')
                pdf = rnd.get('pdf', None)
                matches = []
                for pairing in rnd.get('pairings', []):
                    teams = pairing.get('teams', [])
                    resolved = [alias_dict.get(t, t) for t in teams]
                    if teamname in resolved:
                        opponent = resolved[1] if resolved[0] == teamname else resolved[0]
                        matches.append({'match_number': pairing.get('match_number'), 'opponent': opponent})
                if matches:
                    resolved_rounds.append({'round': round_label, 'matches': matches, 'pdf': pdf})
            schedule_resolved[stage_name] = {'resolved': True, 'rounds': resolved_rounds}
        else:
            schedule_resolved[stage_name] = {'resolved': False, 'round_count': len(rounds)}
    return render_template('schedule.html', 
                         teamname=teamname, 
                         tournament=tournament, 
                         schedule=schedule_resolved,
                         room_aliases=room_aliases,
                         get_room_display_name=get_room_display_name)

@public_bp.route('/schedule/<int:tournament_id>')
def schedule_all(tournament_id):
    tournament = Tournament.query.get(tournament_id)
    if not tournament:
        abort(404, description="No tournament found")
    format_data = tournament.format
    
    # Get all team aliases for this tournament
    aliases = TeamAlias.query.filter_by(tournament_id=tournament.id).all()
    alias_dict = {alias.team_id: alias.team_name for alias in aliases}
    
    # Get room aliases for this tournament
    from models.room_alias import RoomAlias
    room_aliases = {alias.room_number: alias.room_name for alias in RoomAlias.query.filter_by(tournament_id=tournament.id).all()}
    
    # Import the room utility function
    from utils.room_utils import get_room_display_name
    
    # Get all games for this tournament
    games = Game.query.filter_by(tournament_id=tournament.id).order_by(Game.stage_id, Game.round_number).all()
    
    # First pass: organize games by stage and round, and create a lookup dict for game references
    games_by_stage_round = {}
    game_lookup = {}  # Format: {'S{stage}R{round}M{match}': game}
    
    for game in games:
        stage_id = game.stage_id or 1
        round_num = game.round_number or 1
        
        # Add to games_by_stage_round
        if stage_id not in games_by_stage_round:
            games_by_stage_round[stage_id] = {}
        if round_num not in games_by_stage_round[stage_id]:
            games_by_stage_round[stage_id][round_num] = []
        games_by_stage_round[stage_id][round_num].append(game)
        
        # Add to game_lookup
        game_key = f'S{stage_id}R{round_num}M{game.id}'
        game_lookup[game_key] = game
    
    # Function to resolve team name from a game reference
    def resolve_team_name(team_ref, current_stage_id, current_round_num, current_match_num):
        if not team_ref:
            return "TBD"
            
        # If team_ref is not a string, convert to string for consistent handling
        if not isinstance(team_ref, str):
            team_ref = str(team_ref)
            
        # If it's a direct team ID, return the team name
        # First try exact match (in case team_id is a string like '1')
        if team_ref in alias_dict:
            return alias_dict[team_ref]
            
        # Then try converting to int and looking up (for backward compatibility)
        if team_ref.isdigit():
            return alias_dict.get(int(team_ref), f"Team {team_ref}")
            
        # Check if it's a game reference like 'W(S2R1M1)'
        import re
        match = re.match(r'^(W|L|T)\((S\d+R\d+M\d+)\)$', team_ref)
        if match:
            result_type, game_ref = match.groups()
            
            # Find the referenced game
            ref_game = game_lookup.get(game_ref)
            if not ref_game:
                return f"Winner/Loser of {game_ref}"  # More descriptive than just the reference
                
            # Get the winner/loser based on result_type
            if result_type == 'W':
                winning_team = str(ref_game.team1 if ref_game.score1 > ref_game.score2 else ref_game.team2)
                return alias_dict.get(winning_team, f"Team {winning_team}")
            elif result_type == 'L':
                losing_team = str(ref_game.team2 if ref_game.score1 > ref_game.score2 else ref_game.team1)
                return alias_dict.get(losing_team, f"Team {losing_team}")
            else:  # 'T' for tie
                return f"Tie in {game_ref}"
        
        # If it's a string that looks like 't1', 't2', etc., try to convert to int and look up
        if team_ref.startswith('t') and team_ref[1:].isdigit():
            team_id = team_ref[1:]  # Keep as string to match how it's stored
            return alias_dict.get(team_id, f"Team {team_id}")
            
        # If we get here, return the reference as is with a prefix to indicate it's a team
        return f"Team {team_ref}"
    
    schedule_resolved = {}
    stages = format_data['tournament_format']['stages']
    
    for stage in stages:
        stage_id = stage.get('stage_id')
        stage_name = stage.get('stage_name')
        rounds = stage.get('rounds', [])
        
        # For all stages, try to show actual games if they exist
        if stage_id in games_by_stage_round:
            resolved_rounds = []
            for round_num, games_in_round in sorted(games_by_stage_round[stage_id].items()):
                matches = []
                # Sort games by ID to ensure consistent ordering
                sorted_games = sorted(games_in_round, key=lambda g: g.id)
                for match_number, game in enumerate(sorted_games, 1):
                    # Resolve team names, handling game references
                    team1_name = resolve_team_name(game.team1, game.stage_id, game.round_number, match_number)
                    team2_name = "TBD"
                    
                    if game.team2:
                        team2_name = resolve_team_name(game.team2, game.stage_id, game.round_number, match_number)
                    
                    # Initialize default values
                    score1 = 0
                    score2 = 0
                    is_completed = game.result != -2  # -2 means not played
                    
                    # Extract scores from scorecard if available
                    if game.scorecard:
                        try:
                            scorecard_data = json.loads(game.scorecard)
                            if isinstance(scorecard_data, list):
                                for q in scorecard_data:
                                    # Handle both old and new scorecard formats
                                    if 'team1' in q and 'team2' in q:
                                        # New format with team1/team2 structure
                                        score1 += sum(int(p) for p in q['team1'].values() if str(p).lstrip('-').isdigit())
                                        score2 += sum(int(p) for p in q['team2'].values() if str(p).lstrip('-').isdigit())
                                        
                                        # Add bonus points if they exist
                                        if 'team1Bonus' in q and isinstance(q['team1Bonus'], (int, float)):
                                            score1 += int(q['team1Bonus'])
                                        if 'team2Bonus' in q and isinstance(q['team2Bonus'], (int, float)):
                                            score2 += int(q['team2Bonus'])
                                    elif 'scores' in q and len(q['scores']) >= 4:
                                        # Old format with scores array
                                        team1_scores = q['scores'][0]
                                        team2_scores = q['scores'][2]
                                        if isinstance(team1_scores, list):
                                            score1 += sum(s for s in team1_scores if isinstance(s, (int, float)))
                                        if isinstance(team2_scores, list):
                                            score2 += sum(s for s in team2_scores if isinstance(s, (int, float)))
                            
                            # Update the game result based on scores
                            if score1 > score2:
                                game.result = 1  # Team 1 wins
                            elif score2 > score1:
                                game.result = -1  # Team 2 wins
                            else:
                                game.result = 0  # Tie
                            db.session.commit()
                                
                            # Consider game completed if we have non-zero scores
                            is_completed = score1 > 0 or score2 > 0
                            
                        except Exception as e:
                            current_app.logger.error(f"Error parsing scorecard for game {game.id}: {str(e)}")
                            # Fall back to game.result if available
                            if game.result is not None:
                                is_completed = True
                                if game.result == 1:
                                    score1 = 1  # Indicate team 1 won
                                    score2 = 0
                                elif game.result == 2:
                                    score1 = 0
                                    score2 = 1  # Indicate team 2 won
                                else:
                                    score1 = score2 = 0  # Tie
                                
                                # Player names are not being displayed
                        except Exception as e:
                            print(f"Error parsing scorecard: {e}")
                    
                    # Use match number as room number if no room is assigned
                    room_number = getattr(game, 'room_number', match_number)
                    
                    matches.append({
                        'match_number': match_number,
                        'teams': [team1_name, team2_name],
                        'scores': [score1, score2],
                        'completed': is_completed,
                        'room_number': room_number
                    })
                
                resolved_rounds.append({
                    'round': round_num,
                    'round_name': f"Round {round_num}",
                    'matches': matches
                })
            
            schedule_resolved[stage_name] = {
                'resolved': True,
                'rounds': resolved_rounds,
                'is_playoff': stage_id > 1
            }
        else:
            # Fallback to format data if no games exist yet
            if stage_id == 1:  # Prelims
                resolved_rounds = []
                for rnd in rounds:
                    round_label = rnd.get('round_in_stage')
                    matches = []
                    for pairing in rnd.get('pairings', []):
                        teams = pairing.get('teams', [])
                        resolved = [alias_dict.get(t, t) for t in teams]
                        match_num = pairing.get('match_number')
                        matches.append({
                            'match_number': match_num,
                            'teams': resolved,
                            'scores': ["-", "-"],
                            'completed': False,
                            'room_number': pairing.get('room_number', match_num)  # Default to match number if no room specified
                        })
                    resolved_rounds.append({
                        'round': round_label,
                        'round_name': f"Round {round_label}",
                        'matches': matches
                    })
                schedule_resolved[stage_name] = {
                    'resolved': True,
                    'rounds': resolved_rounds,
                    'is_playoff': False
                }
            else:
                schedule_resolved[stage_name] = {
                    'resolved': False,
                    'round_count': len(rounds),
                    'is_playoff': True
                }
    
    return render_template('schedule.html', 
                         teamname=None, 
                         tournament=tournament, 
                         schedule=schedule_resolved,
                         room_aliases=room_aliases,
                         get_room_display_name=get_room_display_name)

class TeamStats:
    def __init__(self):
        self.games_played = 0
        self.wins = 0
        self.losses = 0
        self.ties = 0
        self.points = 0  # Total points across all games
        self.bonus_points = 0
        self.tossup_points = 0
        self.win_percentage = 0.0
        self.cycle_wins = 0  # Number of cycles won
        self.points_per_game = 0.0  # Average points per game
        self.ppb = 0.0  # Points per bonus

class PlayerStats:
    def __init__(self):
        self.tossups_heard = 0
        self.tossup_points = 0
        self.ppth = 0.0  # Points per tossup heard
        self.powers = 0    # 15 point answers
        self.tens = 0      # 10 point answers
        self.negs = 0      # -5 point answers
        self.zeroes = 0    # 0 point answers (active but didn't buzz or got it wrong)

@public_bp.route('/tournament/<int:tournament_id>/leaderboard')
def team_leaderboard(tournament_id):
    current_app.logger.info(f"Generating leaderboard for tournament {tournament_id}")
    tournament = Tournament.query.get_or_404(tournament_id)
    
    # Get all finished games for this tournament that have scorecards
    games = Game.query.filter(
        Game.tournament_id == tournament.id,
        Game.scorecard.isnot(None),
        Game.result != -2  # Only include finished games
    ).all()
    current_app.logger.info(f"Found {len(games)} games with scorecards for tournament {tournament_id}")
    
    # Get all team aliases and players for this tournament
    team_aliases = TeamAlias.query.filter_by(tournament_id=tournament.id).all()
    current_app.logger.info(f"Found {len(team_aliases)} team aliases for tournament {tournament_id}")
    
    players = Player.query.join(TeamAlias, Player.alias_id == TeamAlias.id).filter(TeamAlias.tournament_id == tournament.id).all()
    current_app.logger.info(f"Found {len(players)} players for tournament {tournament_id}")
    
    # Log team aliases for debugging
    for alias in team_aliases:
        current_app.logger.debug(f"Team Alias - ID: {alias.id}, Name: {alias.team_name}, Team ID: {alias.team_id}, Stage: {alias.stage_id}")
    
    # Initialize data structures
    team_stats = {}
    player_stats = {player.id: PlayerStats() for player in players}
    
    # Create mappings for team names and IDs
    team_name_map = {}  # team_name -> team_id
    team_id_to_name = {}  # team_id -> team_name
    
    # First pass: map team names to IDs
    for alias in team_aliases:
        team_name_map[alias.team_name] = alias.team_id
        team_id_to_name[alias.team_id] = alias.team_name
        
        # Also map team_id to itself (for T1, T2, etc.)
        team_name_map[alias.team_id] = alias.team_id
        
        # Log each alias for debugging
        current_app.logger.debug(f"Team Alias - Name: {alias.team_name}, ID: {alias.team_id}, Stage: {alias.stage_id}")
    
    # Log all team aliases for reference
    current_app.logger.info(f"All team aliases: {[(a.team_name, a.team_id) for a in team_aliases]}")
    current_app.logger.info(f"Team name map: {team_name_map}")
    current_app.logger.info(f"Team ID to name map: {team_id_to_name}")
    
    current_app.logger.info(f"Team name map: {team_name_map}")
    current_app.logger.info(f"Team ID to name map: {team_id_to_name}")
    
    # Log placeholder to team mapping if it exists
    if 'placeholder_to_team' in locals():
        current_app.logger.info(f"Placeholder to team map: {placeholder_to_team}")
    else:
        current_app.logger.debug("No placeholder_to_team mapping found")
    
    current_app.logger.debug(f"Team name map: {team_name_map}")
    current_app.logger.debug(f"Team ID to name map: {team_id_to_name}")
    
    def get_team_id(team_name):
        # First try direct lookup by team name (e.g., 'Dogs', 'Cats')
        if team_name in team_name_map:
            return team_name_map[team_name]
            
        # Try to match T1, T2, etc. with team_id
        if team_name.startswith('T'):
            # Try to find a team with team_id matching the full name (e.g., 'T1')
            for alias in team_aliases:
                if alias.team_id == team_name:  # Direct match with team_id
                    current_app.logger.debug(f"Found matching team by ID: {alias.team_name} (ID: {alias.team_id})")
                    return alias.team_id
            
            # If no direct match, try matching with team_name (e.g., 'T1' might be a team name)
            for alias in team_aliases:
                if alias.team_name == team_name:
                    current_app.logger.debug(f"Found matching team by name: {alias.team_name} (ID: {alias.team_id})")
                    return alias.team_id
                    
        # Try to match by team_id if team_name is a team_id (e.g., 'T1' in team_id field)
        for alias in team_aliases:
            if alias.team_id == team_name:
                current_app.logger.debug(f"Found team by team_id: {alias.team_name} (ID: {alias.team_id})")
                return alias.team_id
        
        current_app.logger.warning(f"Could not find team ID for: {team_name}")
        current_app.logger.debug(f"Available team aliases: {[(a.team_name, a.team_id) for a in team_aliases]}")
        return None
    
    # Process each game
    for game in games:
        try:
            current_app.logger.info(f"\n=== Processing game {game.id} ===")
            current_app.logger.info(f"Teams: {game.team1} vs {game.team2}")
            current_app.logger.debug(f"Game scorecard: {game.scorecard}")
            
            # Log team resolution
            team1_id = get_team_id(game.team1)
            team2_id = get_team_id(game.team2)
            current_app.logger.info(f"Resolved teams: {game.team1} -> {team1_id}, {game.team2} -> {team2_id}")
            
            try:
                scorecard = json.loads(game.scorecard) if isinstance(game.scorecard, str) else game.scorecard
                current_app.logger.debug(f"Parsed scorecard: {json.dumps(scorecard, indent=2)}")
            except json.JSONDecodeError as e:
                current_app.logger.error(f"Failed to parse scorecard for game {game.id}: {e}")
                continue
                
            if not isinstance(scorecard, list):
                scorecard = [scorecard]
                
            team1_id = get_team_id(game.team1)
            team2_id = get_team_id(game.team2)
            
            if not team1_id or not team2_id:
                current_app.logger.warning(f"Could not find team IDs for game {game.id}: {game.team1} (resolved: {team1_id}) vs {game.team2} (resolved: {team2_id})")
                current_app.logger.debug(f"Available team aliases: {[(a.team_name, a.team_id) for a in team_aliases]}")
                continue
                
            current_app.logger.info(f"Processing game {game.id}: {game.team1} (ID: {team1_id}) vs {game.team2} (ID: {team2_id})")
            current_app.logger.debug(f"Team1 ID: {team1_id}, Team2 ID: {team2_id}")
                
            # Initialize team stats if needed
            for team_id in [team1_id, team2_id]:
                if team_id not in team_stats:
                    team_stats[team_id] = TeamStats()
            
            # Process each cycle in the scorecard
            for cycle in scorecard:
                if not isinstance(cycle, dict):
                    continue
                
                # Calculate cycle points for cycle wins
                team1_cycle_points = 0
                team2_cycle_points = 0
                
                # Count active players for team1 in this cycle and initialize statline tracking
                team1_players = [p for p in players if p.team_id == team1_id]
                active_team1_players = set()
                
                if 'team1Players' in cycle and isinstance(cycle['team1Players'], list):
                    for i, is_active in enumerate(cycle['team1Players']):
                        if is_active and i < len(team1_players):
                            player_id = team1_players[i].id
                            if player_id in player_stats:
                                player_stats[player_id].tossups_heard += 1
                                active_team1_players.add(player_id)
                
                # Initialize statline for active players who didn't buzz
                for player_id in active_team1_players:
                    player_stats[player_id].zeroes += 1
                
                # Process team1 players and update statline
                if 'team1' in cycle and isinstance(cycle['team1'], dict):
                    for player_id, points in cycle['team1'].items():
                        if player_id.isdigit() and int(player_id) in player_stats:
                            player_id = int(player_id)
                            points = int(points) if str(points).lstrip('-').isdigit() else 0
                            player_stats[player_id].tossup_points += points
                            team_stats[team1_id].tossup_points += points
                            team1_cycle_points += points
                            
                            # Update statline
                            if points == 15:
                                player_stats[player_id].powers += 1
                                player_stats[player_id].zeroes -= 1  # Remove the zero we added earlier
                            elif points == 10:
                                player_stats[player_id].tens += 1
                                player_stats[player_id].zeroes -= 1  # Remove the zero we added earlier
                            elif points == -5:
                                player_stats[player_id].negs += 1
                                player_stats[player_id].zeroes -= 1  # Remove the zero we added earlier
                
                # Count active players for team2 in this cycle and initialize statline tracking
                team2_players = [p for p in players if p.team_id == team2_id]
                active_team2_players = set()
                
                if 'team2Players' in cycle and isinstance(cycle['team2Players'], list):
                    for i, is_active in enumerate(cycle['team2Players']):
                        if is_active and i < len(team2_players):
                            player_id = team2_players[i].id
                            if player_id in player_stats:
                                player_stats[player_id].tossups_heard += 1
                                active_team2_players.add(player_id)
                
                # Initialize statline for active players who didn't buzz
                for player_id in active_team2_players:
                    player_stats[player_id].zeroes += 1
                
                # Process team2 players and update statline
                if 'team2' in cycle and isinstance(cycle['team2'], dict):
                    for player_id, points in cycle['team2'].items():
                        if player_id.isdigit() and int(player_id) in player_stats:
                            player_id = int(player_id)
                            points = int(points) if str(points).lstrip('-').isdigit() else 0
                            player_stats[player_id].tossup_points += points
                            team_stats[team2_id].tossup_points += points
                            team2_cycle_points += points
                            
                            # Update statline
                            if points == 15:
                                player_stats[player_id].powers += 1
                                player_stats[player_id].zeroes -= 1  # Remove the zero we added earlier
                            elif points == 10:
                                player_stats[player_id].tens += 1
                                player_stats[player_id].zeroes -= 1  # Remove the zero we added earlier
                            elif points == -5:
                                player_stats[player_id].negs += 1
                                player_stats[player_id].zeroes -= 1  # Remove the zero we added earlier
                
                # Process bonuses
                for team_key, team_id in [('team1Bonus', team1_id), ('team2Bonus', team2_id)]:
                    if team_key in cycle and team_id in team_stats:
                        bonus = cycle[team_key]
                        if isinstance(bonus, (int, float)) or (isinstance(bonus, str) and bonus.lstrip('-').isdigit()):
                            bonus = int(bonus)
                            team_stats[team_id].bonus_points += bonus
                            if team_id == team1_id:
                                team1_cycle_points += bonus
                            else:
                                team2_cycle_points += bonus
                
                # Track cycle wins for PPB calculation - only count if team scored points in this cycle
                if team1_cycle_points > 0:
                    team_stats[team1_id].cycle_wins += 1
                if team2_cycle_points > 0:
                    team_stats[team2_id].cycle_wins += 1
            
            # Update game results
            team_stats[team1_id].games_played += 1
            team_stats[team2_id].games_played += 1
            
            if game.result == 1:  # Team 1 won
                team_stats[team1_id].wins += 1
                team_stats[team2_id].losses += 1
            elif game.result == -1:  # Team 2 won
                team_stats[team1_id].losses += 1
                team_stats[team2_id].wins += 1
            else:  # Tie
                team_stats[team1_id].ties += 1
                team_stats[team2_id].ties += 1
                
        except Exception as e:
            print(f"Error processing game {game.id}: {e}")
    
    # Calculate derived statistics
    for team_id, stats in team_stats.items():
        # Points per bonus (PPB)
        # Calculate PPB as bonus points per cycle win
        if stats.cycle_wins > 0:
            stats.ppb = round(stats.bonus_points / stats.cycle_wins, 2)
        
        # Win percentage
        if stats.games_played > 0:
            stats.win_percentage = round((stats.wins + (0.5 * stats.ties)) / stats.games_played * 100, 1)
    
    # Calculate player statistics
    for player_id, stats in player_stats.items():
        if stats.tossups_heard > 0:
            stats.ppth = round(stats.tossup_points / stats.tossups_heard, 2)
    
    # Log team stats before sorting
    current_app.logger.info("Team stats before sorting:")
    for team_id, stats in team_stats.items():
        current_app.logger.info(f"Team {team_id} - Games: {stats.games_played}, Wins: {stats.wins}, Losses: {stats.losses}, Ties: {stats.ties}, Points: {stats.tossup_points + stats.bonus_points}")
    
    # Sort teams by wins, then by points
    sorted_teams = sorted(
        team_stats.items(),
        key=lambda x: (-x[1].wins, -x[1].tossup_points - x[1].bonus_points)
    )
    
    # Log player stats before sorting
    current_app.logger.info("Player stats before sorting:")
    for pid, stats in player_stats.items():
        if stats.tossups_heard > 0:
            current_app.logger.info(f"Player {pid} - Tossups: {stats.tossup_points}, Heard: {stats.tossups_heard}, PPTH: {stats.ppth}")
    
    # Sort players by points per tossup heard
    sorted_players = sorted(
        [(pid, stats) for pid, stats in player_stats.items() if stats.tossups_heard > 0],
        key=lambda x: (-x[1].ppth, -x[1].tossup_points)
    )
    
    # Log final team and player counts
    current_app.logger.info(f"Final stats - Teams: {len(sorted_teams)}, Players with stats: {len(sorted_players)}")
    
    # Prepare data for template
    team_data = []
    for team_id, stats in sorted_teams:
        team_data.append({
            'id': team_id,
            'name': team_id_to_name.get(team_id, f"Team {team_id}"),
            'team': team_id_to_name.get(team_id, f"Team {team_id}"),  # Add this line for compatibility
            'wins': stats.wins,
            'losses': stats.losses,
            'ties': stats.ties,
            'win_percentage': stats.win_percentage,
            'points': stats.tossup_points + stats.bonus_points,
            'tossup_points': stats.tossup_points,
            'bonus_points': stats.bonus_points,
            'cycle_wins': stats.cycle_wins,
            'ppb': stats.ppb,
            'games_played': stats.games_played,
            'points_per_game': round((stats.tossup_points + stats.bonus_points) / stats.games_played, 1) if stats.games_played > 0 else 0
        })
    
    player_data = []
    for pid, stats in sorted_players:
        player = next((p for p in players if p.id == pid), None)
        if player:
            player_data.append({
                'id': player.id,
                'name': player.name,
                'team': team_id_to_name.get(player.team_id, f"Team {player.team_id}"),
                'tossup_points': stats.tossup_points,
                'tossups_heard': stats.tossups_heard,
                'ppth': stats.ppth,
                'statline': f"{stats.powers}/{stats.tens}/{stats.zeroes}/{stats.negs}",
                'powers': stats.powers,
                'tens': stats.tens,
                'zeroes': stats.zeroes,
                'negs': stats.negs
            })
    
    # Debug logging
    current_app.logger.info(f"Sending {len(team_data)} teams to template")
    for t in team_data:
        current_app.logger.info(f"Team data: {t}")
        
    return render_template(
        'team_leaderboard.html',
        tournament=tournament,
        teams=team_data,
        players=player_data
    )
    
    # Debug: Print number of games and games with scorecards
    print(f"Found {len(games)} games with scorecards for tournament '{tournament.name}'")
    
    if not games:
        print("No games with scorecards found. This is why no individual stats are showing up.")
    else:
        # Print first scorecard structure for debugging
        try:
            first_scorecard = json.loads(games[0].scorecard)
            print(f"First scorecard structure: {json.dumps(first_scorecard, indent=2)[:500]}...")  # Print first 500 chars
        except Exception as e:
            print(f"Error parsing first scorecard: {e}")

    # Prepare three dictionaries for overall, prelim, and playoffs.
    def init_stats():
        return defaultdict(lambda: {
            "games_played": 0, 
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "points": 0, 
            "bonus_points": 0, 
            "bonus_count": 0,
            "bonus_heard": 0,  # Number of bonuses heard (earned by getting tossup right)
            "tossups_heard": 0,  # Total tossups heard
            "tossups_10": 0,    # Number of 10 point tossups
            "tossups_15": 0,    # Number of 15 point tossups (powers)
            "tossups_neg": 0,   # Number of -5 point tossups (negs)
        })
    overall_stats = init_stats()
    prelim_stats = init_stats()
    playoff_stats = init_stats()

    # Process a single game for a given stats bucket.
    def process_game(stats, game):
        try:
            scorecard = json.loads(game.scorecard)
            if not isinstance(scorecard, list):
                scorecard = [scorecard]  # Ensure we have a list of cycles
        except Exception as e:
            print(f"Error parsing scorecard for game {game.id}: {e}")
            return
            
        # Initialize team names (stored directly in the Game model)
        team1_name = game.team1
        team2_name = game.team2
        
        # Get team IDs from the tournament's team aliases
        team1_alias = TeamAlias.query.filter_by(
            tournament_id=game.tournament_id,
            team_name=team1_name,
            stage_id=game.stage_id
        ).first()
        
        team2_alias = TeamAlias.query.filter_by(
            tournament_id=game.tournament_id,
            team_name=team2_name,
            stage_id=game.stage_id
        ).first()
        
        team1_id = team1_alias.team_id if team1_alias else None
        team2_id = team2_alias.team_id if team2_alias else None
            
        for cycle in scorecard:
            if not isinstance(cycle, dict):
                continue
                
            # Initialize stats for this cycle
            team1_pts = 0
            team2_pts = 0
            team1_bonus_pts = 0
            team2_bonus_pts = 0
            team1_tossups_10 = 0
            team1_tossups_15 = 0
            team1_tossups_neg = 0
            team2_tossups_10 = 0
            team2_tossups_15 = 0
            team2_tossups_neg = 0
            
            # Process team 1 scores from player points
            if 'team1' in cycle and isinstance(cycle['team1'], dict):
                for player_id, points in cycle['team1'].items():
                    if isinstance(points, (int, float)) or (isinstance(points, str) and points.lstrip('-').isdigit()):
                        points = int(points)
                        team1_pts += points
                        
                        # Categorize points
                        if points == 10:
                            team1_tossups_10 += 1
                        elif points == 15:
                            team1_tossups_15 += 1
                        elif points == -5:
                            team1_tossups_neg += 1
            
            # Process team 2 scores from player points
            if 'team2' in cycle and isinstance(cycle['team2'], dict):
                for player_id, points in cycle['team2'].items():
                    if isinstance(points, (int, float)) or (isinstance(points, str) and points.lstrip('-').isdigit()):
                        points = int(points)
                        team2_pts += points
                        
                        # Categorize points
                        if points == 10:
                            team2_tossups_10 += 1
                        elif points == 15:
                            team2_tossups_15 += 1
                        elif points == -5:
                            team2_tossups_neg += 1
            
            # Process bonus points from the new format
            if 'team1Bonus' in cycle:
                bonus = cycle['team1Bonus']
                if isinstance(bonus, (int, float)) or (isinstance(bonus, str) and bonus.lstrip('-').isdigit()):
                    team1_bonus_pts = int(bonus)
                    team1_pts += team1_bonus_pts
            
            if 'team2Bonus' in cycle:
                bonus = cycle['team2Bonus']
                if isinstance(bonus, (int, float)) or (isinstance(bonus, str) and bonus.lstrip('-').isdigit()):
                    team2_bonus_pts = int(bonus)
                    team2_pts += team2_bonus_pts
            
            # Process buzzes to determine which team got the tossup
            if 'buzzes' in cycle and isinstance(cycle['buzzes'], dict):
                # Find first correct buzz to determine which team got the tossup
                correct_buzzes = [
                    (float(percent), result) 
                    for percent, result in cycle['buzzes'].items() 
                    if result == 'Correct' and percent.replace('.', '').isdigit()
                ]
                
                if correct_buzzes:
                    # Sort by percentage to find the first correct buzz
                    correct_buzzes.sort()
                    first_correct_percent, _ = correct_buzzes[0]
                    
                    # Check which team has points in this cycle (the one that got the tossup right)
                    if team1_pts > 0 and team2_pts <= 0:
                        # Team 1 got the tossup
                        if team1_id in stats:
                            stats[team1_id]['bonus_heard'] += 1
                    elif team2_pts > 0 and team1_pts <= 0:
                        # Team 2 got the tossup
                        if team2_id in stats:
                            stats[team2_id]['bonus_heard'] += 1
            
            # Process bonus points
            if 'bonusPoints' in cycle and isinstance(cycle['bonusPoints'], dict):
                bonus = cycle['bonusPoints']
                if 'team1' in bonus and isinstance(bonus['team1'], (int, float)):
                    team1_bonus_pts += int(bonus['team1'])
                if 'team2' in bonus and isinstance(bonus['team2'], (int, float)):
                    team2_bonus_pts += int(bonus['team2'])
            
            # Process tossup results
            if 'tossupResult' in cycle and isinstance(cycle['tossupResult'], dict):
                tossup = cycle['tossupResult']
                if 'team' in tossup and 'points' in tossup and isinstance(tossup['points'], (int, float)):
                    if tossup['team'] == 1:
                        team1_pts += int(tossup['points'])
                    elif tossup['team'] == 2:
                        team2_pts += int(tossup['points'])
            
            # Process all buzzes for additional points (like negs)
            if 'allBuzzes' in cycle and isinstance(cycle['allBuzzes'], list):
                for buzz in cycle['allBuzzes']:
                    if not isinstance(buzz, dict) or 'team' not in buzz or 'points' not in buzz:
                        continue
                    points = int(buzz['points']) if str(buzz['points']).lstrip('-').isdigit() else 0
                    if buzz['team'] == 1:
                        team1_pts += points
                    elif buzz['team'] == 2:
                        team2_pts += points
            
            # Calculate tossups heard (total tossups answered by each team)
            team1_tossups_heard = team1_tossups_10 + team1_tossups_15 + team1_tossups_neg
            team2_tossups_heard = team2_tossups_10 + team2_tossups_15 + team2_tossups_neg
            
            # Determine which team got the tossup (if any)
            team1_got_tossup = team1_pts > 0 and team2_pts <= 0
            team2_got_tossup = team2_pts > 0 and team1_pts <= 0
            
            # Update team 1 stats
            if team1_id is not None and team1_id in stats:
                stats[team1_id]['points'] += team1_pts
                stats[team1_id]['bonus_points'] += team1_bonus_pts
                stats[team1_id]['bonus_count'] += 1 if team1_bonus_pts > 0 else 0
                stats[team1_id]['tossups_heard'] += 1  # Each cycle is a tossup
                stats[team1_id]['tossups_10'] += team1_tossups_10
                stats[team1_id]['tossups_15'] += team1_tossups_15
                stats[team1_id]['tossups_neg'] += team1_tossups_neg
                
                if team1_got_tossup:
                    stats[team1_id]['bonus_heard'] += 1
            
            # Update team 2 stats
            if team2_id is not None and team2_id in stats:
                stats[team2_id]['points'] += team2_pts
                stats[team2_id]['bonus_points'] += team2_bonus_pts
                stats[team2_id]['bonus_count'] += 1 if team2_bonus_pts > 0 else 0
                stats[team2_id]['tossups_heard'] += 1  # Each cycle is a tossup
                stats[team2_id]['tossups_10'] += team2_tossups_10
                stats[team2_id]['tossups_15'] += team2_tossups_15
                stats[team2_id]['tossups_neg'] += team2_tossups_neg
                
                if team2_got_tossup:
                    stats[team2_id]['bonus_heard'] += 1
        
        # Calculate total points for each team from the scorecard
        team1_total = 0
        team2_total = 0
        
        # Sum up points from player scores and bonus points
        for cycle in scorecard:
            if not isinstance(cycle, dict):
                print(f"Warning: Non-dictionary cycle in scorecard: {cycle}")
                continue
                
            # Initialize cycle totals
            team1_cycle_pts = 0
            team2_cycle_pts = 0
            
            # Method 1: Check for scores array (new format)
            if 'scores' in cycle and isinstance(cycle['scores'], list) and len(cycle['scores']) >= 4:
                # Format: [team1_scores, team1_bonus, team2_scores, team2_bonus]
                team1_scores = cycle['scores'][0] if isinstance(cycle['scores'][0], list) else []
                team1_bonus = cycle['scores'][1] if isinstance(cycle['scores'][1], (int, float)) else 0
                team2_scores = cycle['scores'][2] if len(cycle['scores']) > 2 and isinstance(cycle['scores'][2], list) else []
                team2_bonus = cycle['scores'][3] if len(cycle['scores']) > 3 and isinstance(cycle['scores'][3], (int, float)) else 0
                
                team1_cycle_pts = sum(int(s) for s in team1_scores if str(s).lstrip('-').isdigit())
                team2_cycle_pts = sum(int(s) for s in team2_scores if str(s).lstrip('-').isdigit())
                
                team1_total += team1_cycle_pts + int(team1_bonus) if str(team1_bonus).lstrip('-').isdigit() else 0
                team2_total += team2_cycle_pts + int(team2_bonus) if str(team2_bonus).lstrip('-').isdigit() else 0
                
                print(f"  Method 1: team1={team1_cycle_pts} + {team1_bonus} bonus, team2={team2_cycle_pts} + {team2_bonus} bonus")
            
            # Method 2: Check for team1Scores/team2Scores
            elif 'team1Scores' in cycle and 'team2Scores' in cycle:
                team1_scores = cycle['team1Scores'] if isinstance(cycle['team1Scores'], list) else []
                team2_scores = cycle['team2Scores'] if isinstance(cycle['team2Scores'], list) else []
                
                team1_cycle_pts = sum(int(s) for s in team1_scores if str(s).lstrip('-').isdigit())
                team2_cycle_pts = sum(int(s) for s in team2_scores if str(s).lstrip('-').isdigit())
                
                team1_total += team1_cycle_pts
                team2_total += team2_cycle_pts
                
                print(f"  Method 2: team1={team1_cycle_pts}, team2={team2_cycle_pts}")
            
            # Method 3: Check for tossup object (single tossup result)
            elif 'tossup' in cycle and isinstance(cycle['tossup'], dict):
                tossup = cycle['tossup']
                if 'points' in tossup and 'team' in tossup:
                    points = int(tossup['points']) if str(tossup['points']).lstrip('-').isdigit() else 0
                    if tossup['team'] == 1:
                        team1_cycle_pts = points
                        team1_total += points
                    elif tossup['team'] == 2:
                        team2_cycle_pts = points
                        team2_total += points
                    print(f"  Method 3: team{tossup['team']} scored {points} points")
            
            # Method 4: Check for team1/team2 with player points (old format)
            if 'team1' in cycle and isinstance(cycle['team1'], dict):
                team1_player_pts = sum(
                    int(points) if str(points).lstrip('-').isdigit() else 0 
                    for points in cycle['team1'].values()
                )
                team1_cycle_pts = max(team1_cycle_pts, team1_player_pts)
                team1_total += team1_player_pts
                print(f"  Method 4: team1 players scored {team1_player_pts}")
                
            if 'team2' in cycle and isinstance(cycle['team2'], dict):
                team2_player_pts = sum(
                    int(points) if str(points).lstrip('-').isdigit() else 0 
                    for points in cycle['team2'].values()
                )
                team2_cycle_pts = max(team2_cycle_pts, team2_player_pts)
                team2_total += team2_player_pts
                print(f"  Method 4: team2 players scored {team2_player_pts}")
            
            # Process bonus points (check in multiple possible locations)
            bonus = {}
            if 'bonus' in cycle and isinstance(cycle['bonus'], dict):
                bonus = cycle['bonus']
            elif 'bonusPoints' in cycle and isinstance(cycle['bonusPoints'], dict):
                bonus = cycle['bonusPoints']
                
            if bonus:
                if 'team1' in bonus and isinstance(bonus['team1'], (int, float, str)):
                    try:
                        team1_bonus = int(bonus['team1'])
                        team1_total += team1_bonus
                        print(f"  Team1 bonus: {team1_bonus}")
                    except (ValueError, TypeError) as e:
                        print(f"  Warning: Invalid bonus value for team1: {bonus['team1']}")
                if 'team2' in bonus and isinstance(bonus['team2'], (int, float, str)):
                    try:
                        team2_bonus = int(bonus['team2'])
                        team2_total += team2_bonus
                        print(f"  Team2 bonus: {team2_bonus}")
                    except (ValueError, TypeError) as e:
                        print(f"  Warning: Invalid bonus value for team2: {bonus['team2']}")
            
            print(f"  Cycle totals - team1: {team1_cycle_pts}, team2: {team2_cycle_pts}")
            print(f"  Running totals - team1: {team1_total}, team2: {team2_total}")
        
        # Determine the winner based on total points
        if team1_total > team2_total:
            stats[game.team1]["wins"] += 1
            stats[game.team2]["losses"] += 1
        elif team2_total > team1_total:
            stats[game.team2]["wins"] += 1
            stats[game.team1]["losses"] += 1
        else:  # It's a tie
            stats[game.team1]["ties"] += 1
            stats[game.team2]["ties"] += 1
            
        # Debug output
        print(f"Game {game.id}: {game.team1} ({team1_total} pts) vs {game.team2} ({team2_total} pts)")
        if team1_total > team2_total:
            print(f"  Winner: {game.team1}")
        elif team2_total > team1_total:
            print(f"  Winner: {game.team2}")
        else:
            print("  Result: Tie")

    # Get all team aliases for this tournament to map team names to IDs
    team_aliases = TeamAlias.query.filter_by(tournament_id=tournament.id).all()
    team_name_to_id = {alias.team_name: alias.team_id for alias in team_aliases}
    
    # Process each game
    for game in games:
        # Get team names from the game
        team1_name = game.team1
        team2_name = game.team2
        
        # Get team IDs from the mapping
        team1_id = team_name_to_id.get(team1_name)
        team2_id = team_name_to_id.get(team2_name)
        
        if not team1_id or not team2_id:
            print(f"Warning: Could not find team IDs for game {game.id} ({team1_name} vs {team2_name})")
            continue
        
        # Initialize stats for these teams if they don't exist
        for team_id in [team1_id, team2_id]:
            if team_id not in overall_stats:
                overall_stats[team_id] = init_stats()[0]
                
                # Add to appropriate stage stats
                is_playoff = game.stage_id != 1 if hasattr(game, 'stage_id') and game.stage_id is not None else False
                if is_playoff:
                    playoff_stats[team_id] = init_stats()[0]
                else:
                    prelim_stats[team_id] = init_stats()[0]
        
        # Process the game for overall stats
        process_game(overall_stats, game)
        
        # Process for the appropriate stage stats
        is_playoff = game.stage_id != 1 if hasattr(game, 'stage_id') and game.stage_id is not None else False
        if is_playoff:
            process_game(playoff_stats, game)
        else:
            process_game(prelim_stats, game)
        
        # Update games_played, wins, losses, ties
        for stats_dict in [overall_stats, playoff_stats if is_playoff else prelim_stats]:
            if team1_id in stats_dict and team2_id in stats_dict:
                team1_stats = stats_dict[team1_id]
                team2_stats = stats_dict[team2_id]
                
                # Update games played
                team1_stats['games_played'] += 1
                team2_stats['games_played'] += 1
                
                # Update wins/losses/ties based on game result
                if game.result == 1:  # Team 1 won
                    team1_stats['wins'] += 1
                    team2_stats['losses'] += 1
                elif game.result == -1:  # Team 2 won
                    team1_stats['losses'] += 1
                    team2_stats['wins'] += 1
                else:  # Tie
                    team1_stats['ties'] += 1
                    team2_stats['ties'] += 1
    
    # Set the actual games played count for each team
    for team in team_games:
        for stats_dict in [overall_stats, prelim_stats, playoff_stats]:
            if team in stats_dict:
                stats = stats_dict[team]
                stats["games_played"] = stats["wins"] + stats["losses"] + stats["ties"]
                stats["win_percentage"] = (stats["wins"] + 0.5 * stats["ties"]) / stats["games_played"] if stats["games_played"] > 0 else 0

    # Prepare leaderboard lists with computed metrics.
    def compile_leaderboard(stats):
        lb = []
        for team, s in stats.items():
            games_played = s["games_played"]
            if games_played == 0:
                continue
                
            # Calculate statistics
            total_points = s["points"] + s["bonus_points"]
            pts_per_game = total_points / games_played
            bonus_eff = (s["bonus_points"] / s["bonus_count"]) if s["bonus_count"] > 0 else 0
            ppb_heard = (s["bonus_points"] / s["bonus_heard"]) if s["bonus_heard"] > 0 else 0
            tossup_conversion = ((s["tossups_10"] + s["tossups_15"]) / s["tossups_heard"] * 100) if s["tossups_heard"] > 0 else 0
            power_rate = (s["tossups_15"] / (s["tossups_10"] + s["tossups_15"]) * 100) if (s["tossups_10"] + s["tossups_15"]) > 0 else 0
            
            lb.append({
                "team": team,
                "wins": s["wins"],
                "losses": s["losses"],
                "ties": s["ties"],
                "win_percentage": s["win_percentage"] * 100,  # Convert to percentage
                "pts_per_game": pts_per_game,
                "bonus_eff": bonus_eff,
                "games_played": games_played,
                "bonus_heard": s["bonus_heard"],
                "ppb_heard": ppb_heard,
                "tossups_heard": s["tossups_heard"],
                "tossups_10": s["tossups_10"],
                "tossups_15": s["tossups_15"],
                "tossups_neg": s["tossups_neg"],
                "tossup_conversion": tossup_conversion,
                "power_rate": power_rate
            })
        
        # Sort by win percentage, then points per game
        lb.sort(key=lambda x: (x["win_percentage"], x["pts_per_game"]), reverse=True)
        return lb

    leaderboard_overall = compile_leaderboard(overall_stats)
    leaderboard_prelim = compile_leaderboard(prelim_stats)
    leaderboard_playoff = compile_leaderboard(playoff_stats)

    # Individual leaderboard with detailed stats
    player_stats = {}
    team_player_games = defaultdict(set)  # Track which players played in which games
    
    # First, get all players from all teams
    all_teams = set(game.team1 for game in games) | set(game.team2 for game in games)
    print(f"Found {len(all_teams)} teams in games")
    
    # Initialize all players first
    for team_name in all_teams:
        alias = TeamAlias.query.filter_by(team_name=team_name).first()
        if alias:
            for player in alias.players:
                player_id = f"{team_name}:{player.id}"  # Use team:player_id as unique key
                player_stats[player_id] = {
                    'id': player_id,
                    'name': player.name,
                    'team': team_name,
                    'games_played': 0,
                    'points': 0,
                    'tossups_10': 0,
                    'tossups_15': 0,
                    'tossups_neg': 0,
                    'tossups_heard': 0,
                    'bonus_heard': 0,
                    'bonus_points_earned': 0
                }
    
    # Process each game for player stats
    for game in games:
        try:
            scorecard = json.loads(game.scorecard)
            cycles = scorecard if isinstance(scorecard, list) else []
            
            # Get team aliases
            alias1 = TeamAlias.query.filter_by(team_name=game.team1).first()
            alias2 = TeamAlias.query.filter_by(team_name=game.team2).first()
            
            # Debug: Print team info
            print(f"\nProcessing game: {game.team1} vs {game.team2}")
            
            # Track which players participated in this game
            game_players = set()
            
            # Process each cycle in the scorecard
            for cycle in cycles:
                # Get scores for this cycle
                if not isinstance(cycle, dict):
                    continue
                    
                # Get the actual scores from the 'scores' array
                # The format is: [team1_player_scores, team1_bonus, team2_player_scores, team2_bonus]
                scores = cycle.get('scores', [[], 0, [], 0])
                
                # Extract player scores and bonuses
                team1_scores = scores[0] if isinstance(scores[0], list) else []
                team1_bonus = scores[1] if isinstance(scores[1], (int, float)) else 0
                team2_scores = scores[2] if len(scores) > 2 and isinstance(scores[2], list) else []
                team2_bonus = scores[3] if len(scores) > 3 and isinstance(scores[3], (int, float)) else 0
                
                # Debug: Print cycle info
                print(f"\nCycle: {cycle.get('tossup', {}).get('question', '?')}")
                print(f"Team 1 scores: {team1_scores}")
                print(f"Team 2 scores: {team2_scores}")
                print(f"Team 1 bonus: {team1_bonus}")
                print(f"Team 2 bonus: {team2_bonus}")
                
                # Process team 1 players
                if 'team1' in cycle and isinstance(cycle['team1'], dict):
                    print(f"\nProcessing team 1 ({game.team1}) players:")
                    
                    # Get the player stats for this team
                    team_players = {}
                    if alias1:
                        team_players = {p.id: p for p in alias1.players}
                    
                    # Process each player's score in this cycle
                    for player_id, points in cycle['team1'].items():
                        try:
                            points = int(points)
                            player_id = int(player_id)  # Convert to int for lookup
                        except (ValueError, TypeError):
                            continue
                            
                        # Find the player in our team
                        player = team_players.get(player_id)
                        if not player:
                            print(f"  Warning: Player ID {player_id} not found in team {game.team1}")
                            continue
                            
                        # Create player key and ensure player exists in stats
                        player_key = f"{game.team1}:{player_id}"
                        if player_key not in player_stats:
                            player_stats[player_key] = {
                                'id': player_key,
                                'name': player.name,
                                'team': game.team1,
                                'games_played': 0,
                                'points': 0,
                                'tossups_10': 0,
                                'tossups_15': 0,
                                'tossups_neg': 0,
                                'tossups_heard': 0,
                                'bonus_heard': 0,
                                'bonus_points_earned': 0
                            }
                        
                        # Mark player as having played in this game
                        game_players.add(player_key)
                        
                        # Update player stats based on points
                        if points == 10:
                            player_stats[player_key]['tossups_10'] += 1
                            player_stats[player_key]['tossups_heard'] += 1
                        elif points == 15:
                            player_stats[player_key]['tossups_15'] += 1
                            player_stats[player_key]['tossups_heard'] += 1
                        elif points == -5:
                            player_stats[player_key]['tossups_neg'] += 1
                            player_stats[player_key]['tossups_heard'] += 1
                        
                        # Add to total points
                        player_stats[player_key]['points'] += points
                        if is_active:
                            game_players.add(pid)
                        
                        # Only process points if they scored and were active
                        if pts != 0 and is_active:
                            player_stats[pid]['points'] += pts
                            player_stats[pid]['tossups_heard'] += 1
                            
                            if pts == 10:
                                player_stats[pid]['tossups_10'] += 1
                                player_stats[pid]['bonus_heard'] += 1
                                # Update team stats
                                team1_tossups_10 += 1
                                team1_bonus_heard += 1
                            elif pts == 15:
                                player_stats[pid]['tossups_15'] += 1
                                player_stats[pid]['bonus_heard'] += 1
                                # Update team stats
                                team1_tossups_15 += 1
                                team1_bonus_heard += 1
                            elif pts == -5:
                                player_stats[pid]['tossups_neg'] += 1
                                # Update team stats
                                team1_tossups_neg += 1
                            
                            # Update team total points
                            team1_total += pts
                            
                            # Update team tossups heard
                            team1_tossups_heard += 1
                            
                            # Update bonus stats if applicable
                            if pts in (10, 15) and team1_bonus > 0:
                                team1_bonus_pts += team1_bonus
                                team1_bonus_count += 1
                # Process team 2
                if alias2 and team2_scores:
                    print(f"\nProcessing team 2 ({game.team2}) players:")
                    for i, pts in enumerate(team2_scores):
                        if i >= len(alias2.players):
                            print(f"  Warning: More scores than players for team 2")
                            break
                            
                        player = alias2.players[i]
                        pid = player.id
                        print(f"  Player {i}: {player.name} (ID: {pid}) - Points: {pts}")
                        
                        # Check if player was active in this cycle (by ID or legacy index)
                        is_active = (pid in team2_active_ids or 
                                   (i < len(team2_active) and team2_active[i] == 1))
                        
                        if pid not in player_stats:
                            print(f"  Creating new player entry for {player.name}")
                            player_stats[pid] = {
                                'player': player.name,
                                'team': game.team2,
                                'games': 0,
                                'points': 0,
                                'tossups_10': 0,
                                'tossups_15': 0,
                                'tossups_neg': 0,
                                'tossups_heard': 0,
                                'bonus_heard': 0,
                                'bonus_points_earned': 0
                            }
                        
                        # Add to game players if active in this cycle
                        if is_active:
                            game_players.add(pid)
                        
                        # Only process points if they scored and were active
                        if pts != 0 and is_active:
                            player_stats[pid]['points'] += pts
                            player_stats[pid]['tossups_heard'] += 1
                            
                            if pts == 10:
                                player_stats[pid]['tossups_10'] += 1
                                player_stats[pid]['bonus_heard'] += 1
                                # Update team stats
                                team2_tossups_10 += 1
                                team2_bonus_heard += 1
                            elif pts == 15:
                                player_stats[pid]['tossups_15'] += 1
                                player_stats[pid]['bonus_heard'] += 1
                                # Update team stats
                                team2_tossups_15 += 1
                                team2_bonus_heard += 1
                            elif pts == -5:
                                player_stats[pid]['tossups_neg'] += 1
                                # Update team stats
                                team2_tossups_neg += 1
                            
                            # Update team total points
                            team2_total += pts
                            
                            # Update team tossups heard
                            team2_tossups_heard += 1
                            
                            # Update bonus stats if applicable
                            if pts in (10, 15) and team2_bonus > 0:
                                team2_bonus_pts += team2_bonus
                                team2_bonus_count += 1
            
            # Update games played for players who participated
            for pid in game_players:
                if pid in player_stats:
                    player_stats[pid]['games'] += 1
                    
        except Exception as e:
            print(f"Error processing game {game.id}: {str(e)}")
            continue
    
    # Prepare final leaderboard - include ALL players
    leaderboard_individual = []
    
    # First, get all players from all teams in the tournament
    # Initialize player stats if not already done
    all_teams = set(game.team1 for game in games) | set(game.team2 for game in games)
    for team_name in all_teams:
        alias = TeamAlias.query.filter_by(team_name=team_name).first()
        if alias:
            for player in alias.players:
                player_key = f"{team_name}:{player.id}"  # Use team:player_id as unique key
                if player_key not in player_stats:
                    player_stats[player_key] = {
                        'id': player_key,
                        'name': player.name,
                        'team': team_name,
                        'games_played': 0,
                        'points': 0,
                        'tossups_10': 0,
                        'tossups_15': 0,
                        'tossups_neg': 0,
                        'tossups_heard': 0,
                        'bonus_heard': 0,
                        'bonus_points_earned': 0
                    }
    
    # Process each game to update player stats
    for game in games:
        try:
            scorecard = json.loads(game.scorecard)
            if not isinstance(scorecard, list):
                continue
                
            # Track which players participated in this game
            game_players = set()
            
            for cycle in scorecard:
                if not isinstance(cycle, dict):
                    continue
                    
                # Process team 1 players
                if 'team1' in cycle and isinstance(cycle['team1'], dict):
                    for player_id, points in cycle['team1'].items():
                        try:
                            points = int(points)
                            player_key = f"{game.team1}:{player_id}"
                            if player_key in player_stats:
                                game_players.add(player_key)
                                # Update player stats based on points
                                if points == 10:
                                    player_stats[player_key]['tossups_10'] += 1
                                    player_stats[player_key]['tossups_heard'] += 1
                                elif points == 15:
                                    player_stats[player_key]['tossups_15'] += 1
                                    player_stats[player_key]['tossups_heard'] += 1
                                elif points == -5:
                                    player_stats[player_key]['tossups_neg'] += 1
                                    player_stats[player_key]['tossups_heard'] += 1
                                player_stats[player_key]['points'] += points
                        except (ValueError, TypeError):
                            continue
                            
                # Process team 2 players (similar to team 1)
                if 'team2' in cycle and isinstance(cycle['team2'], dict):
                    for player_id, points in cycle['team2'].items():
                        try:
                            points = int(points)
                            player_key = f"{game.team2}:{player_id}"
                            if player_key in player_stats:
                                game_players.add(player_key)
                                # Update player stats based on points
                                if points == 10:
                                    player_stats[player_key]['tossups_10'] += 1
                                    player_stats[player_key]['tossups_heard'] += 1
                                elif points == 15:
                                    player_stats[player_key]['tossups_15'] += 1
                                    player_stats[player_key]['tossups_heard'] += 1
                                elif points == -5:
                                    player_stats[player_key]['tossups_neg'] += 1
                                    player_stats[player_key]['tossups_heard'] += 1
                                player_stats[player_key]['points'] += points
                        except (ValueError, TypeError):
                            continue
            
            # Update games played for players who participated in this game
            for player_key in game_players:
                player_stats[player_key]['games_played'] += 1
                
        except Exception as e:
            print(f"Error processing game {game.id}: {e}")
    
    # Compile the individual leaderboard
    leaderboard_individual = []
    for player_key, stats in player_stats.items():
        games_played = stats.get('games_played', 0)
        if games_played > 0:  # Only include players who have played games
            leaderboard_individual.append({
                'id': stats.get('id', ''),
                'name': stats.get('name', 'Unknown Player'),
                'team': stats.get('team', 'Unknown Team'),
                'points': stats.get('points', 0),
                'tossups_10': stats.get('tossups_10', 0),
                'tossups_15': stats.get('tossups_15', 0),
                'tossups_neg': stats.get('tossups_neg', 0),
                'tossups_heard': stats.get('tossups_heard', 0),
                'games_played': games_played,
                'points_ppg': stats.get('points', 0) / games_played if games_played > 0 else 0,
                'tossups_heard_pg': stats.get('tossups_heard', 0) / games_played if games_played > 0 else 0
            })
    
    # Sort by points per game (descending)
    leaderboard_individual.sort(key=lambda x: x['points_ppg'], reverse=True)
    
    print(f"Generated leaderboard with {len(leaderboard_individual)} players")
    
    # Debug output
    print("\n=== Leaderboard Debug Info ===")
    print(f"Teams in leaderboard_overall: {len(leaderboard_overall) if leaderboard_overall else 0}")
    if leaderboard_overall:
        print("Sample team data:", leaderboard_overall[0])
    print("==========================\n")

    return render_template('team_leaderboard.html',
                           tournament=tournament,
                           leaderboard_overall=leaderboard_overall,
                           leaderboard_prelim=leaderboard_prelim,
                           leaderboard_playoff=leaderboard_playoff,
                           leaderboard_individual=leaderboard_individual)
