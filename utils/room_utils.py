from models.room_alias import RoomAlias

def get_room_display_name(tournament_id, room_number, default_prefix='Room '):
    """
    Get the display name for a room, using the alias if available.
    
    Args:
        tournament_id (int): The ID of the tournament
        room_number (int): The room number to look up
        default_prefix (str): The prefix to use when no alias exists (default: 'Room ')
        
    Returns:
        str: The room's display name (either the alias or the default prefix + number)
    """
    if not room_number:
        return "Unassigned"
        
    # Try to find a room alias
    alias = RoomAlias.query.filter_by(
        tournament_id=tournament_id,
        room_number=room_number
    ).first()
    
    if alias and alias.room_name:
        return alias.room_name
    
    return f"{default_prefix}{room_number}"

def get_room_aliases(tournament_id):
    """
    Get all room aliases for a tournament as a dictionary mapping room numbers to names.
    
    Args:
        tournament_id (int): The ID of the tournament
        
    Returns:
        dict: A dictionary mapping room numbers to their display names
    """
    aliases = RoomAlias.query.filter_by(tournament_id=tournament_id).all()
    return {alias.room_number: alias.room_name for alias in aliases}
