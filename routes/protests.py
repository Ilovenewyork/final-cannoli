from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models import db
from models.protest import Protest
from models.reader import Reader
from models.admin import Admin
from datetime import datetime

bp = Blueprint('protests', __name__)

@bp.route('/protests', methods=['POST'])
@login_required
def submit_protest():
    """
    Submit a new protest for a cycle in a game.
    Expected JSON payload:
    {
        "tournament_id": int,
        "game_id": int,
        "cycle_number": int,
        "message": str
    }
    """
    try:
        # Debug: Log the incoming request
        print("Received protest submission:", request.json)
        
        if not current_user.is_authenticated or not hasattr(current_user, 'id'):
            return jsonify({'error': 'Authentication required'}), 401
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data received'}), 400
        
        # Debug: Log the received data
        print("Received data:", data)
        
        # Validate required fields
        required_fields = ['tournament_id', 'game_id', 'cycle_number', 'message']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            error_msg = f'Missing required fields: {", ".join(missing_fields)}'
            print(error_msg)
            return jsonify({'error': error_msg}), 400
        
        # Debug: Log the raw data types received
        print("Raw data types received:", {
            'tournament_id': type(data.get('tournament_id')),
            'game_id': type(data.get('game_id')),
            'cycle_number': type(data.get('cycle_number')),
            'message': type(data.get('message'))
        })
        
        # Convert to integers, handling both string and numeric inputs
        try:
            def safe_int(value):
                if isinstance(value, (int, float)):
                    return int(value)
                if isinstance(value, str):
                    return int(float(value.strip() or 0))
                return 0
                
            tournament_id = safe_int(data.get('tournament_id', 0))
            game_id = safe_int(data.get('game_id', 0))
            cycle_number = safe_int(data.get('cycle_number', 0))
            
            # Debug: Log the converted values
            print("Converted values:", {
                'tournament_id': (tournament_id, type(tournament_id)),
                'game_id': (game_id, type(game_id)),
                'cycle_number': (cycle_number, type(cycle_number))
            })
            
            # Validate that we have positive numbers
            if tournament_id <= 0 or game_id <= 0 or cycle_number <= 0:
                error_msg = 'All numeric fields must be positive numbers'
                print(f"{error_msg}: tournament_id={tournament_id}, game_id={game_id}, cycle_number={cycle_number}")
                return jsonify({'error': error_msg}), 400
                
        except (ValueError, TypeError) as e:
            error_msg = f'Invalid data type for numeric fields. Please provide valid numbers. Error: {str(e)}'
            print(f"{error_msg}. Raw data: {data}")
            return jsonify({'error': error_msg}), 400
        
        # Create new protest
        protest = Protest(
            tournament_id=tournament_id,
            game_id=game_id,
            cycle_number=cycle_number,
            message=data['message'].strip(),
            created_by=current_user.id,
            status='pending'
        )
        
        db.session.add(protest)
        db.session.commit()
        
        print(f"Protest submitted successfully. ID: {protest.id}")
        return jsonify({
            'message': 'Protest submitted successfully',
            'protest_id': protest.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        error_msg = f'Error submitting protest: {str(e)}'
        print(error_msg)
        return jsonify({'error': 'Failed to submit protest. Please try again.'}), 500

@bp.route('/protests/<int:protest_id>/resolve', methods=['POST'])
@login_required
def resolve_protest(protest_id):
    """
    Resolve a protest (admin only)
    Expected JSON payload (all fields optional):
    {
        "resolution_notes": str
    }
    """
    from flask import session
    
    # Check if user is an admin using session
    if 'admin_id' not in session:
        return jsonify({'error': 'Admin login required'}), 403
    
    # Verify the admin user exists
    admin = Admin.query.get(session['admin_id'])
    if not admin:
        return jsonify({'error': 'Admin user not found'}), 403
    
    try:
        data = request.get_json() or {}
        protest = Protest.query.get_or_404(protest_id)
        
        # Update protest status to resolved
        protest.status = 'resolved'
        protest.resolved_at = datetime.utcnow()
        protest.resolved_by = admin.id
        
        # Set resolution notes if provided, otherwise use empty string
        if 'resolution_notes' in data and data['resolution_notes']:
            protest.resolution_notes = data['resolution_notes']
        else:
            protest.resolution_notes = 'No resolution notes provided.'
        
        db.session.commit()
        
        return jsonify({
            'message': 'Protest resolved successfully',
            'protest_id': protest.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/tournaments/<int:tournament_id>/protests', methods=['GET'])
def get_tournament_protests(tournament_id):
    """
    Get all protests for a tournament (admin only)
    """
    # Import the Admin model
    from models.admin import Admin
    from flask import session
    
    # Debug info
    print(f"Session data: {dict(session)}")
    
    # Check if user is an admin using session
    if 'admin_id' not in session:
        print("No admin_id in session")
        return jsonify({'error': 'Admin login required'}), 403
    
    # Verify the admin user exists
    admin = Admin.query.get(session['admin_id'])
    if not admin:
        print(f"Admin with ID {session.get('admin_id')} not found")
        return jsonify({'error': 'Admin user not found'}), 403
        
    print(f"Authenticated as admin: {admin.username}")
    
    try:
        # Join with Game to get round_number
        from models.game import Game
        protests = db.session.query(
            Protest,
            Game.round_number
        ).join(
            Game, Game.id == Protest.game_id
        ).filter(
            Protest.tournament_id == tournament_id
        ).order_by(
            Protest.status.asc(), 
            Protest.created_at.desc()
        ).all()
        
        result = []
        for p, round_number in protests:
            try:
                protest_data = {
                    'id': p.id,
                    'game_id': p.game_id,
                    'round_number': round_number,
                    'cycle_number': p.cycle_number,
                    'message': p.message,
                    'status': p.status,
                    'created_at': p.created_at.isoformat() if p.created_at else None,
                    'created_by': p.submitter.email if p.submitter else 'Unknown',
                    'resolved_at': p.resolved_at.isoformat() if p.resolved_at else None,
                    'resolved_by': p.resolver.email if p.resolver and p.resolved_by else None,
                    'resolution_notes': p.resolution_notes
                }
                result.append(protest_data)
            except Exception as e:
                print(f"Error serializing protest {p.id}: {str(e)}")
                continue
                
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
