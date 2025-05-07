import os
import time
from pathlib import Path
import re
import json

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from tinydb import TinyDB, Query
from openai import OpenAI

load_dotenv()

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
openai = OpenAI()

ALLOWED_CHANNELS = ["C08RKK2AMT2", "C088JM79NLX"]

# First, we need to extract the common processing logic from message_hello
def process_bot_interaction(event, say):
    thread_ts = event.get("thread_ts", event.get("ts"))
    print("\n\n\n\n\n\n Started New Session")
    
    # Replace user IDs with names
    # event['text'] = replace_user_ids_with_names(event['text'], app.client)

    # Prepare the base wait message
    base_wait_message = f"Please wait while I process your request <@{event['user']}>! \nThis may take a few minutes. \n\nStatus:"
    
    # Track the first message for updating later
    first_message = say(base_wait_message, thread_ts=thread_ts)
    current_ts = first_message["ts"]
    
    print(f"Received a message: {event['text']}")
    print(f"Thread TS: {thread_ts}")
    print(f"Current TS: {current_ts}")
    
    # Continue with the rest of the existing logic from message_hello
    app.client.chat_update(channel=event["channel"], ts=current_ts, text=f"{base_wait_message} Checking for previous conversations... (1/5)")
    db = TinyDB(f"db/{thread_ts}.json")
    query = Query()
    
    # Cleanup old JSON files
    now = time.time()
    cutoff = now - (int(os.environ.get("MESSAGE_RETENTION_DAYS")) * 86400)
    for file in Path('.').glob('db/*.json'):
        timestamp = float(file.stem.split('.')[0])
        if timestamp < cutoff:
            os.remove(file)
    
    # Check if the bot history exists
    previous_response_id = None
    if db.search(query.previous_response_id.exists()) and db.get(query.dataType == "previous_response_id") is not None:
        app.client.chat_update(channel=event["channel"], ts=current_ts, text=f"{base_wait_message} Found previous conversations! (2/5)")
        previous_response_id = db.get(query.dataType == "previous_response_id")
        print("Data : ", previous_response_id)
        previous_response_id = previous_response_id["previous_response_id"]
        print(f"Previous response ID: {previous_response_id}")
    
    # Setup model inference parameter template
    parameters = {
        "model": "gpt-4.1-mini",
        "input": [
            {"role": "user", "content": None},
        ],
        "store": True,
        "tools": [
            {
                "type": "web_search_preview",
                "user_location": {
                    "type": "approximate"
                },
                "search_context_size": "low"
            }
        ],
    }
    
    app.client.chat_update(channel=event["channel"], ts=current_ts, text=f"{base_wait_message} Preparing the model inference parameters...(3/5)")
    
    # preparing input
    user_prompt = ""
    with open("prompts/chat_user_prompt.txt", "r") as file:
            user_prompt = file.read()
    
    # Load the default current field configuration
    current_field_config = ""
    if db.search(query.current_field_config.exists()):
        current_field_config = db.get(query.dataType == "current_field_config")
        current_field_config = current_field_config["current_field_config"]
    else:
        with open("data/CURRENT_FIELD_CONFIG.json", "r") as file:
            current_field_config = file.read()
    current_field_config = json.loads(current_field_config)
    
    # Setting the previous response ID if it exists
    if previous_response_id:
        parameters["previous_response_id"] = previous_response_id
    else:
        # Prepare the system and user prompts
        system_prompt = ""
        with open("prompts/chat_system_prompt.txt", "r") as file:
            system_prompt = file.read()

        # Prepare the field meta
        field_meta = ""
        with open("data/FIELD_META.json", "r") as file:
            field_meta = file.read()

        # Prepare the field configuration
        field_configuration = ""
        with open("data/FIELD_CONFIGURATIONS.json", "r") as file:
            field_configuration = file.read()
        
        # Replace variables in the system prompt
        system_prompt_data = {
            "FIELD_META": field_meta,
            "FIELD_CONFIGURATIONS": field_configuration,
        }
        system_prompt = replace_variables(system_prompt, system_prompt_data)
        parameters["input"].insert(0, {"role": "system", "content": system_prompt})
        
    # Replace variables in the user prompt
    user_prompt_data = {
        "USER_MESSAGE": event["text"],
        "CURRENT_FIELD_CONFIGURATIONS": json.dumps(current_field_config),
        "CURRENT_SYSTEM_DATA": f"Date: {time.strftime('%Y-%m-%d')}, Time: {time.strftime('%H:%M:%S')}, User: {event['user']}",
    }
    user_prompt = replace_variables(user_prompt, user_prompt_data)
    parameters["input"][-1]["content"] = user_prompt

    app.client.chat_update(channel=event["channel"], ts=current_ts, text=f"{base_wait_message} Sending the request to OpenAI... (4/5)")

    print(f"Parameters: {parameters}")
    
    # Create new conversation if no previous response is found
    response = openai.responses.create(**parameters)
    raw_response = response.output_text
    app.client.chat_update(channel=event["channel"], ts=current_ts, text=f"{base_wait_message} Processing the response... (5/5)")
    xml_response = extract_xml_tags(raw_response)
    app.client.chat_update(channel=event["channel"], ts=current_ts, text=xml_response["BOT_MESSAGE"])
    previous_response_id = response.id

    # Use upsert for database operations
    db.upsert({'dataType': 'previous_response_id', 'previous_response_id': previous_response_id}, query.dataType == "previous_response_id")
    db.upsert({'dataType': 'current_field_config', 'current_field_config': xml_response["NEW_FIELD_CONFIGURATIONS"]}, query.dataType == "current_field_config")

# Modify the existing app_mention handler to use our new common function
@app.event("app_mention")
def message_hello(event, say):
    # Check if the event is in the correct channel
    if event.get("channel") not in ALLOWED_CHANNELS:
        thread_ts = event.get("thread_ts", event.get("ts"))
        return say("Sorry, I can only respond to messages in the #being-adept channel.", thread_ts=thread_ts)
    
    # Process the app_mention using our shared function
    process_bot_interaction(event, say)

# Add a new handler for regular messages in threads
@app.event("message")
def handle_thread_message(event, say):
    # Ignore bot messages and message edits
    if "subtype" in event and event["subtype"] in ["bot_message", "message_changed"]:
        return
    
    # Ignore direct mentions of the bot (they'll be handled by app_mention)
    bot_id = app.client.auth_test()["user_id"]
    if event.get("text") and f"<@{bot_id}>" in event.get("text"):
        return
    
    # Check if this is part of a thread
    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return  # Not in a thread, ignore
        
    # Check if we have a DB file for this thread (indicating we were previously mentioned)
    db_file = Path(f"db/{thread_ts}.json")
    if not db_file.exists():
        return  # We were never mentioned in this thread, ignore
        
    # Check if the event is in the correct channel
    if event.get("channel") not in ALLOWED_CHANNELS:
        return  # Don't respond in incorrect channels
    
    # Process the message
    process_bot_interaction(event, say)

def replace_variables(text, replacements):
    result = text
    for key, value in replacements.items():
        placeholder = "{" + key + "}"
        result = result.replace(placeholder, value)
    return result

def extract_xml_tags(text):
    pattern = r'<([^>]+)>(.*?)</\1>'
    matches = re.findall(pattern, text, re.DOTALL)
    
    result = {}
    for tag, content in matches:
        result[tag] = content.strip()
    
    return result

def replace_user_ids_with_names(text, slack_client):
    user_id_pattern = r'<@(U[A-Z0-9]+)>'
    user_ids = re.findall(user_id_pattern, text)
    for user_id in user_ids:
        response = slack_client.users_info(user=user_id)        
        if response['ok']:
            user = response['user']
            name = user.get('profile', {}).get('real_name') or user.get('name', f'Unknown User ({user_id})')
            text = text.replace(f'<@{user_id}>', f'"@{name}"')
    return text

if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
