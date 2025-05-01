import copy
import json
from typing import Dict, Any

# --- Schema Preprocessing Helper ---
# Copied from discordbot/gurt/api.py
def _preprocess_schema_for_vertex(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively preprocesses a JSON schema dictionary to replace list types
    (like ["string", "null"]) with the first non-null type, making it
    compatible with Vertex AI's GenerationConfig schema requirements.

    Args:
        schema: The JSON schema dictionary to preprocess.

    Returns:
        A new, preprocessed schema dictionary.
    """
    if not isinstance(schema, dict):
        return schema # Return non-dict elements as is

    processed_schema = copy.deepcopy(schema) # Work on a copy

    for key, value in processed_schema.items():
        if key == "type" and isinstance(value, list):
            # Find the first non-"null" type in the list
            first_valid_type = next((t for t in value if isinstance(t, str) and t.lower() != "null"), None)
            if first_valid_type:
                processed_schema[key] = first_valid_type
            else:
                # Fallback if only "null" or invalid types are present (shouldn't happen in valid schemas)
                processed_schema[key] = "object" # Or handle as error
                print(f"Warning: Schema preprocessing found list type '{value}' with no valid non-null string type. Falling back to 'object'.")
        elif isinstance(value, dict):
            processed_schema[key] = _preprocess_schema_for_vertex(value) # Recurse for nested objects
        elif isinstance(value, list):
            # Recurse for items within arrays (e.g., in 'properties' of array items)
            processed_schema[key] = [_preprocess_schema_for_vertex(item) if isinstance(item, dict) else item for item in value]
        # Handle 'properties' specifically
        elif key == "properties" and isinstance(value, dict):
             processed_schema[key] = {prop_key: _preprocess_schema_for_vertex(prop_value) for prop_key, prop_value in value.items()}
        # Handle 'items' specifically if it's a schema object
        elif key == "items" and isinstance(value, dict):
             processed_schema[key] = _preprocess_schema_for_vertex(value)

    return processed_schema

# --- Response Schema ---
# Copied from discordbot/gurt/config.py
RESPONSE_SCHEMA = {
    "name": "gurt_response",
    "description": "The structured response from Gurt.",
    "schema": {
        "type": "object",
        "properties": {
            "should_respond": {
                "type": "boolean",
                "description": "Whether the bot should send a text message in response."
            },
            "content": {
                "type": "string",
                "description": "The text content of the bot's response. Can be empty if only reacting."
            },
            "react_with_emoji": {
                "type": ["string", "null"],
                "description": "Optional: A standard Discord emoji to react with, or null/empty if no reaction."
            },
            "reply_to_message_id": {
                "type": ["string", "null"],
                "description": "Optional: The ID of the message this response should reply to. Null or omit for a regular message."
            }
            # Note: tool_requests is handled by Vertex AI's function calling mechanism
        },
        "required": ["should_respond", "content"]
    }
}

if __name__ == "__main__":
   processed = _preprocess_schema_for_vertex(RESPONSE_SCHEMA['schema'])
   print(json.dumps(processed, indent=2))
