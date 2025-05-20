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
            current_app.logger.info(f'Successfully notified reasoner about saved chat: {filename}')
        except Exception as e:
            current_app.logger.error(f"Failed to notify reasoner about saved chat: {str(e)}")
    
    # ---- BEGIN Gemini API Integration ----
    try:
        current_app.logger.info(f'Preparing to send chat data to Gemini API for patient: {patient_name}')
        gemini_api_key = 'AIzaSyDq_Lch1KXstEeOl_C_4H1RstnlWQ-qyDQ' # User provided API Key
        gemini_api_url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_api_key}'

        system_prompt = """You are an AI assistant tasked with analyzing chats between a patient and a bot in a diabetes management app. Your goal is to extract and summarize indicators that may suggest potential deception or non-adherence to the prescribed program. Focus on the following aspects:

1. **Inconsistencies**: Note any contradictions in the patient's responses, either within this chat or compared to previous chats (if provided).
2. **Vague or Evasive Language**: Identify responses that lack specifics, use hedging language (e.g., "I think," "maybe"), or avoid direct answers to the bot's questions or answer with unrelated facts.
3. **Engagement Level**: Assess the length and detail of the patient's responses, noting if they are unusually brief or lack engagement or if they are unusually long.
4. **Potential Gaming of the System**: Flag any patterns that suggest the patient is providing answers they think the bot expects, such as overly consistent or perfect responses.

Present your findings in a concise summary, using bullet points or sections for clarity. Avoid making definitive judgments; instead, present observations that a doctor can use to further assess the patient's adherence. Also give a general summary of what the patient has said.
"""

        # Function to format a single chat log
        def format_chat_log(chat_data):
            formatted_messages = []
            log_patient_name = chat_data.get('patient_name', 'Unknown Patient')
            for msg in chat_data.get('messages', []):
                sender_name = msg.get('user', {}).get('name', 'Unknown')
                is_human = msg.get('user', {}).get('human', False)
                prefix = f'{sender_name} (Patient):\t' if is_human else 'Bot:\t'
                
                message_content = msg.get("message", "")
                formatted_messages.append(f'{prefix}{message_content}')
            return f'Chat with {log_patient_name} ({chat_data.get("timestamp", "N/A")}):\n' + '\n'.join(formatted_messages)

        all_chat_texts = []

        # Add current chat
        current_chat_log = format_chat_log(save_payload)
        all_chat_texts.append('Current Chat Session:\n' + current_chat_log)

        # Add previous chats
        previous_chat_texts = ['\n\nPrevious Saved Chats:']
        if os.path.exists(chats_dir):
            for chat_file_name in sorted(os.listdir(chats_dir)):
                if chat_file_name.endswith('.json') and chat_file_name != filename:
                    try:
                        with open(os.path.join(chats_dir, chat_file_name), 'r') as cf:
                            previous_chat_data = json.load(cf)
                            previous_chat_texts.append(format_chat_log(previous_chat_data))
                    except Exception as e:
                        current_app.logger.error(f'Error loading previous chat file {chat_file_name}: {str(e)}')
        
        if len(previous_chat_texts) > 1:
            all_chat_texts.extend(previous_chat_texts)
        else:
            all_chat_texts.append('\nNo previous chats found.')

        combined_chat_history = '\n\n'.join(all_chat_texts)
        
        gemini_payload = {
            'contents': [{
                'role': 'user',
                'parts': [
                    {'text': system_prompt},
                    {'text': '\n\nChat History for Analysis:\n' + combined_chat_history}
                ]
            }],
            'generationConfig': {
                'temperature': 0.7,
                'topK': 1,
                'topP': 1,
                'maxOutputTokens': 4096,
                'stopSequences': []
            },
            'safetySettings': [
                {'category': 'HARM_CATEGORY_HARASSMENT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
                {'category': 'HARM_CATEGORY_HATE_SPEECH', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
                {'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
                {'category': 'HARM_CATEGORY_DANGEROUS_CONTENT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'}
            ]
        }
        
        current_app.logger.debug(f"Gemini API Payload: {json.dumps(gemini_payload, indent=2)}")
        
        response = requests.post(gemini_api_url, json=gemini_payload, headers={'Content-Type': 'application/json'})
        response.raise_for_status() # Will raise an HTTPError if the HTTP request returned an unsuccessful status code
        
        gemini_response_data = response.json()
        current_app.logger.info('Successfully received response from Gemini API.')
        current_app.logger.debug(f"Gemini API Response: {json.dumps(gemini_response_data, indent=2)}")

        # ---- Save Gemini Response to summary.txt ----
        try:
            summary_filename = f"summary_{patient_name}_{timestamp}.txt"
            summary_filepath = os.path.join(chats_dir, summary_filename)
            
            # Extract the text content from the Gemini response
            # Assuming the response structure is like: {'candidates': [{'content': {'parts': [{'text': '...'}]}}]}
            gemini_text_response = ""
            if gemini_response_data.get('candidates') and \
               len(gemini_response_data['candidates']) > 0 and \
               gemini_response_data['candidates'][0].get('content') and \
               gemini_response_data['candidates'][0]['content'].get('parts') and \
               len(gemini_response_data['candidates'][0]['content']['parts']) > 0 and \
               gemini_response_data['candidates'][0]['content']['parts'][0].get('text'):
                gemini_text_response = gemini_response_data['candidates'][0]['content']['parts'][0]['text']
            else:
                gemini_text_response = "Could not extract text from Gemini response."
                current_app.logger.warning("Could not extract text from Gemini response. Saving raw JSON.")
                gemini_text_response += "\n\nRaw Gemini Response:\n" + json.dumps(gemini_response_data, indent=2)


            with open(summary_filepath, 'w') as f_summary:
                f_summary.write("Summary from Gemini API:\n")
                f_summary.write("========================\n\n")
                f_summary.write(f"Patient Name: {patient_name}\n")
                f_summary.write(f"Timestamp: {timestamp}\n\n")
                f_summary.write("--------------------\n")
                f_summary.write(gemini_text_response)
            
            current_app.logger.info(f"Gemini API response saved to {summary_filepath}")

        except Exception as e_summary:
            current_app.logger.error(f"Error saving Gemini API response to summary file: {str(e_summary)}")
        # ---- END Save Gemini Response ----

    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error calling Gemini API: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            current_app.logger.error(f"Gemini API Error Response Content: {e.response.text}")
    except Exception as e:
        current_app.logger.error(f"An unexpected error occurred during Gemini API integration: {str(e)}")
    # ---- END Gemini API Integration ----

    return "Chat saved successfully", 200
