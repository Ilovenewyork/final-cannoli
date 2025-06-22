from flask import Blueprint, render_template, abort
from models import db
from models.tournament import Tournament
from models.team_alias import TeamAlias
from models.player import Player
import json
from models.game import Game
from collections import defaultdict

public_bp = Blueprint('public', __name__, template_folder='../templates/public')

# Removed old team route (/schedule/<teamname>)
@public_bp.route('/schedule/<int:tournament_id>/<teamname>')
def team_schedule(tournament_id, teamname):
    tournament = Tournament.query.get(tournament_id)
    if not tournament:
        abort(404, description="Tournament not found")
    format_data = tournament.format
    aliases = TeamAlias.query.filter_by(tournament_id=tournament.id, stage_id=1).all()
    alias_dict = {alias.team_id: alias.team_name for alias in aliases}
    
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
    return render_template('schedule.html', teamname=teamname, tournament=tournament, schedule=schedule_resolved)

@public_bp.route('/schedule/<int:tournament_id>')
def schedule_all(tournament_id):
    tournament = Tournament.query.get(tournament_id)
    if not tournament:
        abort(404, description="No tournament found")
    format_data = tournament.format
    
    # Get all team aliases for this tournament
    aliases = TeamAlias.query.filter_by(tournament_id=tournament.id).all()
    alias_dict = {alias.team_id: alias.team_name for alias in aliases}
    
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
        if not team_ref or not isinstance(team_ref, str):
            return team_ref
            
        # If it's a direct team ID, return the team name
        if team_ref.isdigit():
            return alias_dict.get(int(team_ref), team_ref)
            
        # Check if it's a game reference like 'W(S2R1M1)'
        import re
        match = re.match(r'^(W|L|T)\((S\d+R\d+M\d+)\)$', team_ref)
        if match:
            result_type, game_ref = match.groups()
            
            # Find the referenced game
            ref_game = game_lookup.get(game_ref)
            if not ref_game:
                return team_ref  # Return original if game not found
                
            # Get the winner/loser based on result_type
            if result_type == 'W':
                winning_team = ref_game.team1 if ref_game.score1 > ref_game.score2 else ref_game.team2
            elif result_type == 'L':
                winning_team = ref_game.team2 if ref_game.score1 > ref_game.score2 else ref_game.team1
            else:  # 'T' for tie (shouldn't happen in elimination)
                return "Tie"
                
            return alias_dict.get(winning_team, str(winning_team))
            
        return team_ref  # Return as is if not a recognized format
    
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
                    is_completed = False
                    
                    # Extract scores from scorecard if available
                    if game.scorecard:
                        try:
                            scorecard_data = json.loads(game.scorecard)
                            if isinstance(scorecard_data, list) and len(scorecard_data) > 0:
                                # Scorecard is a list of question results, calculate totals
                                for q in scorecard_data:
                                    if 'scores' in q and len(q['scores']) >= 4:
                                        # Sum up the scores for team1 (index 0) and team2 (index 2)
                                        team1_scores = q['scores'][0]
                                        team2_scores = q['scores'][2]
                                        if isinstance(team1_scores, list):
                                            score1 += sum(s for s in team1_scores if isinstance(s, (int, float)))
                                        if isinstance(team2_scores, list):
                                            score2 += sum(s for s in team2_scores if isinstance(s, (int, float)))
                                
                                # Consider game completed if there are any non-zero scores
                                is_completed = score1 > 0 or score2 > 0
                                
                                # Player names are not being displayed
                        except Exception as e:
                            print(f"Error parsing scorecard: {e}")
                    
                    matches.append({
                        'match_number': match_number,
                        'teams': [team1_name, team2_name],
                        'scores': [score1, score2],
                        'completed': is_completed
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
                        matches.append({
                            'match_number': pairing.get('match_number'),
                            'teams': resolved,
                            'scores': ["-", "-"],
                            'completed': False
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
                         schedule=schedule_resolved)

@public_bp.route('/tournament/<int:tournament_id>/leaderboard')
def team_leaderboard(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    
    # Get all games for this tournament that have scorecards
    games = Game.query.filter(
        Game.tournament_id == tournament.id,
        Game.scorecard.isnot(None)
    ).all()
    
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
            "games": 0, 
            "points": 0, 
            "bonus_points": 0, 
            "bonus_count": 0,
            "bonus_heard": 0,  # Number of bonuses heard (earned by getting tossup right)
            "tossups_heard": 0,  # Total tossups heard
            "tossups_10": 0,    # Number of 10 point tossups
            "tossups_15": 0,    # Number of 15 point tossups (powers)
            "tossups_neg": 0,   # Number of -5 point tossups (negs)
            "win_score": 0
        })
    overall_stats = init_stats()
    prelim_stats = init_stats()
    playoff_stats = init_stats()

    # Process a single game for a given stats bucket.
    def process_game(stats, game):
        try:
            scorecard = json.loads(game.scorecard)
            # Handle both list and dictionary formats for cycles
            if isinstance(scorecard, list):
                cycles = scorecard
            else:
                cycles = scorecard.get("cycles", [])
        except Exception:
            cycles = []
            
        for cycle in cycles:
            # Handle both list and dictionary cycle formats
            if isinstance(cycle, dict):
                scores = cycle.get("scores", [])
                team1_active = cycle.get("team1Players", [])
                team2_active = cycle.get("team2Players", [])
            else:
                scores = cycle if isinstance(cycle, list) else []
                team1_active = []
                team2_active = []
                
            # Extract scores and bonuses
            team1_scores = []
            team1_bonus = 0
            team2_scores = []
            team2_bonus = 0
            
            if isinstance(scores, list) and len(scores) >= 4:
                team1_scores = scores[0] if isinstance(scores[0], list) else []
                team1_bonus = scores[1] if isinstance(scores[1], (int, float)) else 0
                team2_scores = scores[2] if isinstance(scores[2], list) else []
                team2_bonus = scores[3] if isinstance(scores[3], (int, float)) else 0
                
                # Set default active players if not specified
                if not team1_active:
                    team1_active = [True] * len(team1_scores)
                if not team2_active:
                    team2_active = [True] * len(team2_scores)
            
            # Process team 1
            team1_total = sum(pts for i, pts in enumerate(team1_scores) 
                            if i < len(team1_active) and team1_active[i] is not False)
            team1_bonus_pts = team1_bonus if any(pts > 0 for pts in team1_scores) else 0
            team1_bonus_count = 1 if any(pts > 0 for pts in team1_scores) else 0
            team1_bonus_heard = sum(1 for pts in team1_scores if pts in (10, 15))
            team1_tossups_heard = sum(1 for pts in team1_scores if pts != 0)
            team1_tossups_10 = sum(1 for pts in team1_scores if pts == 10)
            team1_tossups_15 = sum(1 for pts in team1_scores if pts == 15)
            team1_tossups_neg = sum(1 for pts in team1_scores if pts == -5)
            
            # Process team 2
            team2_total = sum(pts for i, pts in enumerate(team2_scores) 
                            if i < len(team2_active) and team2_active[i] is not False)
            team2_bonus_pts = team2_bonus if any(pts > 0 for pts in team2_scores) else 0
            team2_bonus_count = 1 if any(pts > 0 for pts in team2_scores) else 0
            team2_bonus_heard = sum(1 for pts in team2_scores if pts in (10, 15))
            team2_tossups_heard = sum(1 for pts in team2_scores if pts != 0)
            team2_tossups_10 = sum(1 for pts in team2_scores if pts == 10)
            team2_tossups_15 = sum(1 for pts in team2_scores if pts == 15)
            team2_tossups_neg = sum(1 for pts in team2_scores if pts == -5)
            
            # Update stats for both teams
            for team, points, bonus, bonus_cnt, bonus_heard, tossups_heard, t10, t15, tneg in [
                (game.team1, team1_total, team1_bonus_pts, team1_bonus_count, 
                 team1_bonus_heard, team1_tossups_heard, team1_tossups_10, 
                 team1_tossups_15, team1_tossups_neg),
                (game.team2, team2_total, team2_bonus_pts, team2_bonus_count,
                 team2_bonus_heard, team2_tossups_heard, team2_tossups_10,
                 team2_tossups_15, team2_tossups_neg)
            ]:
                stats[team]["games"] = 1  # Will be set to actual count later
                stats[team]["points"] += points
                stats[team]["bonus_points"] += bonus
                stats[team]["bonus_count"] += bonus_cnt
                stats[team]["bonus_heard"] += bonus_heard
                stats[team]["tossups_heard"] += tossups_heard
                stats[team]["tossups_10"] += t10
                stats[team]["tossups_15"] += t15
                stats[team]["tossups_neg"] += tneg
        
        # Update win/loss records after processing all cycles
        if game.result == 1:  # Team 1 won
            stats[game.team1]["win_score"] += 1
        elif game.result == -1:  # Team 2 won
            stats[game.team2]["win_score"] += 1
        elif game.result == 0:  # Draw
            stats[game.team1]["win_score"] += 0.5
            stats[game.team2]["win_score"] += 0.5

    # Process each game into overall bucket and into prelim or playoff bucket.
    for game in games:
        process_game(overall_stats, game)
        if game.stage_id == 1:
            process_game(prelim_stats, game)
        else:
            process_game(playoff_stats, game)

    # Prepare leaderboard lists with computed metrics.
    def compile_leaderboard(stats):
        lb = []
        for team, s in stats.items():
            games_played = s["games"]
            win_record = s["win_score"] / games_played if games_played else 0
            # Include both tossup and bonus points in PPG
            total_points = s["points"] + s["bonus_points"]
            pts_per_game = total_points / games_played if games_played else 0
            bonus_eff = (s["bonus_points"] / s["bonus_count"]) if s["bonus_count"] else 0
            lb.append({
                "team": team,
                "win_record": win_record,
                "pts_per_game": pts_per_game,
                "bonus_eff": bonus_eff,
                "games": games_played,
                "bonus_heard": s["bonus_heard"],
                "ppb_heard": (s["bonus_points"] / s["bonus_heard"]) if s["bonus_heard"] > 0 else 0,
                "tossups_heard": s["tossups_heard"],
                "tossups_10": s["tossups_10"],
                "tossups_15": s["tossups_15"],
                "tossups_neg": s["tossups_neg"],
                "tossup_conversion": (
                    (s["tossups_10"] + s["tossups_15"]) / s["tossups_heard"] * 100
                ) if s["tossups_heard"] > 0 else 0,
                "power_rate": (
                    s["tossups_15"] / (s["tossups_10"] + s["tossups_15"]) * 100
                ) if (s["tossups_10"] + s["tossups_15"]) > 0 else 0
            })
        lb.sort(key=lambda x: (x["win_record"], x["pts_per_game"]), reverse=True)
        return lb

    leaderboard_overall = compile_leaderboard(overall_stats)
    leaderboard_prelim = compile_leaderboard(prelim_stats)
    leaderboard_playoff = compile_leaderboard(playoff_stats)

    # Individual leaderboard with detailed stats
    player_stats = {}
    
    # First, get all players from all teams
    all_teams = set(game.team1 for game in games) | set(game.team2 for game in games)
    print(f"Found {len(all_teams)} teams in games")
    
    # Initialize all players first
    for team_name in all_teams:
        alias = TeamAlias.query.filter_by(team_name=team_name).first()
        if alias:
            for player in alias.players:
                player_stats[player.id] = {
                    'player': player.name,
                    'team': team_name,
                    'games': 0,
                    'points': 0,
                    'tossups_10': 0,
                    'tossups_15': 0,
                    'tossups_neg': 0,
                    'tossups_heard': 0,
                    'bonus_heard': 0,
                    'bonus_points_earned': 0
                }
    
    # Process each game
    for game in games:
        try:
            scorecard = json.loads(game.scorecard)
            cycles = scorecard if isinstance(scorecard, list) else []
            
            # Get team aliases
            alias1 = TeamAlias.query.filter_by(team_name=game.team1).first()
            alias2 = TeamAlias.query.filter_by(team_name=game.team2).first()
            
            # Debug: Print team info
            print(f"\nProcessing game: {game.team1} vs {game.team2}")
            print(f"Team 1 alias: {alias1}")
            print(f"Team 2 alias: {alias2}")
            
            if alias1:
                print(f"Team 1 players: {[p.name for p in alias1.players]}")
            if alias2:
                print(f"Team 2 players: {[p.name for p in alias2.players]}")
            
            # Track which players participated in this game
            game_players = set()
            
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
                
                # Process team 1
                if alias1 and team1_scores:
                    print(f"\nProcessing team 1 ({game.team1}) players:")
                    for i, pts in enumerate(team1_scores):
                        if i >= len(alias1.players):
                            print(f"  Warning: More scores than players for team 1")
                            break
                            
                        player = alias1.players[i]
                        pid = player.id
                        print(f"  Player {i}: {player.name} (ID: {pid}) - Points: {pts}")
                        
                        if pid not in player_stats:
                            print(f"  Creating new player entry for {player.name}")
                            player_stats[pid] = {
                                'player': player.name,
                                'team': game.team1,
                                'games': 0,
                                'points': 0,
                                'tossups_10': 0,
                                'tossups_15': 0,
                                'tossups_neg': 0,
                                'tossups_heard': 0,
                                'bonus_heard': 0,
                                'bonus_points_earned': 0
                            }
                        
                        # Always add player to game_players if they were in the lineup
                        game_players.add(pid)
                        
                        # Only process points if they scored
                        if pts != 0:
                            player_stats[pid]['points'] += pts
                            player_stats[pid]['tossups_heard'] += 1
                            
                            if pts == 10:
                                player_stats[pid]['tossups_10'] += 1
                                player_stats[pid]['bonus_heard'] += 1
                            elif pts == 15:
                                player_stats[pid]['tossups_15'] += 1
                                player_stats[pid]['bonus_heard'] += 1
                            elif pts == -5:
                                player_stats[pid]['tossups_neg'] += 1
                
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
                        
                        # Always add player to game_players if they were in the lineup
                        game_players.add(pid)
                        
                        # Only process points if they scored
                        if pts != 0:
                            player_stats[pid]['points'] += pts
                            player_stats[pid]['tossups_heard'] += 1
                            
                            if pts == 10:
                                player_stats[pid]['tossups_10'] += 1
                                player_stats[pid]['bonus_heard'] += 1
                            elif pts == 15:
                                player_stats[pid]['tossups_15'] += 1
                                player_stats[pid]['bonus_heard'] += 1
                            elif pts == -5:
                                player_stats[pid]['tossups_neg'] += 1
            
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
    all_teams = set(game.team1 for game in games) | set(game.team2 for game in games)
    for team_name in all_teams:
        alias = TeamAlias.query.filter_by(team_name=team_name).first()
        if alias:
            for player in alias.players:
                if player.id not in player_stats:
                    player_stats[player.id] = {
                        'player': player.name,
                        'team': team_name,
                        'games': 0,
                        'points': 0,
                        'tossups_10': 0,
                        'tossups_15': 0,
                        'tossups_neg': 0,
                        'tossups_heard': 0,
                        'bonus_heard': 0,
                        'bonus_points_earned': 0
                    }
    
    # Now add all players to the leaderboard
    for pid, stats in player_stats.items():
        games_played = stats['games']
        tossups_total = stats['tossups_10'] + stats['tossups_15']
        tossups_heard = stats['tossups_heard']
        
        # Calculate stats with division by zero protection
        stats['pts_per_game'] = stats['points'] / games_played if games_played > 0 else 0
        stats['tossup_conversion'] = (tossups_total / tossups_heard * 100) if tossups_heard > 0 else 0
        stats['power_rate'] = (stats['tossups_15'] / tossups_total * 100) if tossups_total > 0 else 0
        
        leaderboard_individual.append(stats)
    
    # Sort by points per game (descending)
    leaderboard_individual.sort(key=lambda x: x['pts_per_game'], reverse=True)
    
    print(f"Generated leaderboard with {len(leaderboard_individual)} players")

    return render_template('team_leaderboard.html',
                           tournament=tournament,
                           leaderboard_overall=leaderboard_overall,
                           leaderboard_prelim=leaderboard_prelim,
                           leaderboard_playoff=leaderboard_playoff,
                           leaderboard_individual=leaderboard_individual)
