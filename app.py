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

@app.event("app_mention")
def message_hello(event, say):
    # Received the event
    thread_ts = event.get("thread_ts", event.get("ts"))
    print("\n\n\n\n\n\n Started New Session")
    
    # Check if the event is in the correct channel
    if event.get("channel") not in ["C08RKK2AMT2", "C088JM79NLX"]:
        return say("Sorry, I can only respond to messages in the #being-adept channel.", thread_ts=thread_ts)
    
    # Prepare the base wait message
    base_wait_message = f"Please wait while I process your request <@{event['user']}>! \nThis may take a few minutes. \n\nStatus:"
    
    # Track the first message for updating later
    first_message = say(base_wait_message, thread_ts=thread_ts)
    current_ts = first_message["ts"]
    
    print(f"Received a message: {event['text']}")
    print(f"Thread TS: {thread_ts}")
    print(f"Current TS: {current_ts}")
    
    # Checking for previous conversations
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
    if db.search(query.previous_response_id.exists()):
        app.client.chat_update(channel=event["channel"], ts=current_ts, text=f"{base_wait_message} Found previous conversations! (2/5)")
        previous_response_id = db.get(query.dataType == "previous_response_id")
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
    
    # Seting the previous response ID if it exists
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
    db.insert({"dataType": "previous_response_id", "previous_response_id": previous_response_id})
    db.insert({"dataType": "current_field_config", "current_field_config": xml_response["NEW_FIELD_CONFIGURATIONS"]})

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

if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
