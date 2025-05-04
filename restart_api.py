#!/usr/bin/env python
"""
Script to restart the API server with proper environment setup.
This ensures the database connections are properly initialized.
"""
import os
import sys
import subprocess
import time

def main():
    """Main function to restart the API server"""
    print("Restarting API server...")
    
    # Get the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Check if we're in the discordbot directory
    if os.path.basename(current_dir) != "discordbot":
        print("Error: This script must be run from the discordbot directory.")
        sys.exit(1)
    
    # Find any running API server processes
    try:
        print("Checking for running API server processes...")
        result = subprocess.run(
            ["ps", "-ef", "|", "grep", "api_server.py", "|", "grep", "-v", "grep"],
            shell=True,
            capture_output=True,
            text=True
        )
        
        if result.stdout.strip():
            print("Found running API server processes:")
            print(result.stdout)
            
            # Ask for confirmation before killing
            confirm = input("Do you want to kill these processes? (y/n): ")
            if confirm.lower() == 'y':
                # Kill the processes
                subprocess.run(
                    ["pkill", "-f", "api_server.py"],
                    shell=True
                )
                print("Processes killed.")
                time.sleep(2)  # Give processes time to terminate
            else:
                print("Aborted. Please stop the running API server processes manually.")
                sys.exit(1)
    except Exception as e:
        print(f"Error checking for running processes: {e}")
    
    # Start the API server
    print("Starting API server...")
    try:
        # Use the run_unified_api.py script
        subprocess.Popen(
            [sys.executable, "run_unified_api.py"],
            cwd=current_dir
        )
        print("API server started successfully.")
    except Exception as e:
        print(f"Error starting API server: {e}")
        sys.exit(1)
    
    print("API server restart complete.")

if __name__ == "__main__":
    main()
