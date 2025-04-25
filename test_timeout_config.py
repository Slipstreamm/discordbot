import json
import os

# Define the path for the JSON file to store timeout chance
TIMEOUT_CONFIG_FILE = os.path.join("data", "timeout_config.json")

def load_timeout_config():
    """Load timeout configuration from JSON file"""
    timeout_chance = 0.005  # Default value
    if os.path.exists(TIMEOUT_CONFIG_FILE):
        try:
            with open(TIMEOUT_CONFIG_FILE, "r") as f:
                data = json.load(f)
                if "timeout_chance" in data:
                    timeout_chance = data["timeout_chance"]
                    print(f"Loaded timeout chance: {timeout_chance}")
                else:
                    print("timeout_chance not found in config file")
        except Exception as e:
            print(f"Error loading timeout configuration: {e}")
    else:
        print(f"Config file does not exist: {TIMEOUT_CONFIG_FILE}")
    return timeout_chance

def save_timeout_config(timeout_chance):
    """Save timeout configuration to JSON file"""
    try:
        # Ensure data directory exists
        os.makedirs(os.path.dirname(TIMEOUT_CONFIG_FILE), exist_ok=True)
        
        config_data = {
            "timeout_chance": timeout_chance,
            "target_user_id": 748405715520978965,
            "timeout_duration": 60
        }
        with open(TIMEOUT_CONFIG_FILE, "w") as f:
            json.dump(config_data, f, indent=4)
        print(f"Saved timeout configuration with chance: {timeout_chance}")
        return True
    except Exception as e:
        print(f"Error saving timeout configuration: {e}")
        return False

# Test the functionality
if __name__ == "__main__":
    # Load the current config
    current_chance = load_timeout_config()
    print(f"Current timeout chance: {current_chance}")
    
    # Update the timeout chance
    new_chance = 0.01  # 1%
    if save_timeout_config(new_chance):
        print(f"Successfully updated timeout chance to {new_chance}")
    
    # Load the config again to verify it was saved
    updated_chance = load_timeout_config()
    print(f"Updated timeout chance: {updated_chance}")
    
    # Restore the original value
    if save_timeout_config(current_chance):
        print(f"Restored timeout chance to original value: {current_chance}")
