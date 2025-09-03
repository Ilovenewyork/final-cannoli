from flask import Blueprint, jsonify, request, current_app
from models.alert import Alert, AlertLevel
from models.game import Game
from extensions import db
from flask_login import login_required, current_user
from datetime import datetime

bp = Blueprint('alerts', __name__)

@bp.route('/alerts', methods=['POST'])
@login_required
def create_alert():
    """Create a new alert (TD call or emergency)"""
    data = request.get_json()
    
    # Validate required fields
    if not data or 'game_id' not in data or 'level' not in data:
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        # Get the game to ensure it exists
        game = Game.query.get_or_404(data['game_id'])
        
        # Normalize the alert level to handle case differences
        level_str = data['level'].upper()
        if level_str == 'TD_CALL':
            alert_level = AlertLevel.TD_CALL
        elif level_str == 'EMERGENCY':
            alert_level = AlertLevel.EMERGENCY
        else:
            raise ValueError(f"Invalid alert level: {data['level']}")
        
        # Create the alert
        alert = Alert(
            game_id=game.id,
            room=data.get('room', f"Room {game.id}"),
            level=alert_level,
            message=data.get('message', '')
        )
        
        db.session.add(alert)
        db.session.commit()
        
        # TODO: Notify admins in real-time (using WebSocket or similar)
        
        return jsonify(alert.to_dict()), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error creating alert: {str(e)}')
        return jsonify({'error': 'Failed to create alert'}), 500

@bp.route('/alerts', methods=['GET'])
@login_required
def get_alerts():
    """Get all active alerts"""
    try:
        # Get unresolved alerts, ordered by most recent first
        alerts = Alert.query.filter_by(resolved=False)\
                          .order_by(Alert.created_at.desc())\
                          .all()
        return jsonify([alert.to_dict() for alert in alerts])
    except Exception as e:
        current_app.logger.error(f'Error fetching alerts: {str(e)}')
        return jsonify({'error': 'Failed to fetch alerts'}), 500

@bp.route('/alerts/<int:alert_id>/resolve', methods=['POST'])
@login_required
def resolve_alert(alert_id):
    """Mark an alert as resolved"""
    try:
        alert = Alert.query.get_or_404(alert_id)
        alert.resolved = True
        alert.resolved_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({'message': 'Alert resolved successfully'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error resolving alert: {str(e)}')
        return jsonify({'error': 'Failed to resolve alert'}), 500
