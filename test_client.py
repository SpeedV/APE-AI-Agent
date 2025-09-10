import requests
import json
import uuid
import base64

AGENT_URL = "http://127.0.0.1:8080"

def send_request(message_parts):
    """Helper function to construct and send a JSON-RPC request."""
    request_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    
    payload = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": message_id,
                "role": "user",
                "parts": message_parts
            }
        },
        "id": request_id
    }
    
    try:
        print(f"--- Sending request for: {message_parts[0].get('text', 'Image Task')} ---")
        response = requests.post(AGENT_URL, json=payload)
        response.raise_for_status()
        
        response_data = response.json()
        result_text = response_data.get('result', {}).get('message', {}).get('parts', [{}])[0].get('text', 'No text in response')
        
        print(f"✅ Agent Response: {result_text}\n")
        return result_text
    except requests.exceptions.RequestException as e:
        print(f"❌ Error: Could not connect to the agent at {AGENT_URL}. Is it running?")
        print(f"Details: {e}\n")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}\n")

if __name__ == "__main__":
    print("--- Starting Agent Capability Tests ---\n")

    # 1. General QA
    send_request([{"kind": "text", "text": "What is the largest moon of Saturn?"}])

    # 2. Tool Usage (Calculator)
    send_request([{"kind": "text", "text": "A rectangle is 8 cm long and 6 cm wide. What is its perimeter? (Answer with digits)"}])

    # 3. Web Browsing
    send_request([{"kind": "text", "text": "browse: https://www.python.org/"}])
    
    # 4. Code Execution
    code_prompt = """
    execute python:
    names = ['Alice', 'Bob', 'Charlie']
    for name in names:
        print(f'Hello, {name}!')
    """
    send_request([{"kind": "text", "text": code_prompt}])
    
    # 5. Memory (Store and Retrieve)
    send_request([{"kind": "text", "text": "remember that: my favorite color is blue"}])
    send_request([{"kind": "text", "text": "what did i ask you to remember?"}])

    # 6. Image Understanding
    try:
        red_pixel_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/wcAAwAB/epv2AAAAABJRU5ErkJggg=="
        send_request([
            {"kind": "image", "base64": red_pixel_base64},
            {"kind": "text", "text": "What color is this tiny image?"}
        ])
    except Exception as e:
        print(f"❌ Could not run image test. Error: {e}")

    print("--- All Tests Concluded ---")