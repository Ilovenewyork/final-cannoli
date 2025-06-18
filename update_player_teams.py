from app import create_app
from extensions import db
from models.player import Player

def update_player_teams():
    # Get all players with their aliases
    players = db.session.query(Player, TeamAlias).join(
        TeamAlias, Player.alias_id == TeamAlias.id
    ).all()
    
    updated = 0
    for player, alias in players:
        if not player.team_id and alias.team_id:
            player.team_id = alias.team_id
            updated += 1
    
    if updated > 0:
        db.session.commit()
        print(f"Updated {updated} players with team IDs")
    else:
        print("No players needed updating")

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        from models.team_alias import TeamAlias
        update_player_teams()
