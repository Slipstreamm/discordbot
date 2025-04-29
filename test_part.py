# Test script for Part constructor
try:
    from gurt.api import types
    print("Successfully imported types module")
    
    # Test creating a Part with text
    part = types.Part(text="test")
    print(f"Successfully created Part with text: {part}")
    
    # Test creating a Part with URI
    part_uri = types.Part(uri="https://example.com", mime_type="text/plain")
    print(f"Successfully created Part with URI: {part_uri}")
    
    print("All tests passed!")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
