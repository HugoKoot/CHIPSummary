from flask import Blueprint, current_app, request
import flask_sse
import requests
import json
from datetime import datetime
import os


bp = Blueprint('main', __name__)


@bp.route('/')
def hello():
    return 'Hello, I am the website backend module!'


@bp.route('/process', methods=['POST'])
def response():
    data = request.json
    flask_sse.sse.publish({'message': data['message']}, type='response')
    return "Message sent!"


@bp.route('/submit', methods=['POST'])
def submit():
    data = request.json
    
    t2t_address = current_app.config.get("TRIPLE_EXTRACTOR_ADDRESS", None)
    if t2t_address:
        requests.post(f"http://{t2t_address}/process", json=data)

    return f"Submitted sentence '{data['sentence']}' from {data['patient_name']} to t2t!"


@bp.route('/save-chat', methods=['POST'])
def save_chat():
    data = request.json
    messages = data.get('messages', [])
    patient_name = data.get('patient_name', 'unknown')
    
    current_app.logger.debug(f"Attempting to save chat for patient: {patient_name}")
    current_app.logger.debug(f"Chat data received: {json.dumps(data, indent=2)}")
    
    if not messages:
        current_app.logger.warning("No messages received, nothing to save.")
        return "No messages to save", 400
        
    # Create a timestamp for the filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"chat_{patient_name}_{timestamp}.json"
    
    # Create chats directory if it doesn't exist
    chats_dir = os.path.join(current_app.root_path, 'chats')
    os.makedirs(chats_dir, exist_ok=True)
    
    # Data to be saved
    save_payload = {
        'patient_name': patient_name,
        'timestamp': timestamp,
        'messages': messages
    }
    
    # Save the chat to a file
    filepath = os.path.join(chats_dir, filename)
    with open(filepath, 'w') as f:
        json.dump(save_payload, f, indent=2)
    
    current_app.logger.info(f"Chat saved successfully to {filepath}")
    current_app.logger.debug(f"Saved chat content: {json.dumps(save_payload, indent=2)}")
    
    # Notify other modules about the saved chat
    reasoner_address = current_app.config.get('REASONER_ADDRESS', None)
    if reasoner_address:
        try:
            requests.post(f"http://{reasoner_address}/chat-saved", json={
                'patient_name': patient_name,
                'chat_file': filename
            })
        except Exception as e:
            current_app.logger.error(f"Failed to notify reasoner about saved chat: {str(e)}")
    
    return "Chat saved successfully", 200
