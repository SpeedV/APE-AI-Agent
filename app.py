import os
import uuid
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import capabilities
import shelve # Import the shelve module
import atexit # To handle graceful shutdown

# --- Initialization ---
app = Flask(__name__)
CORS(app)

memory_db = shelve.open('agent_memory', writeback=True)

def close_db():
    memory_db.close()
atexit.register(close_db)


@app.route('/.well-known/agent-card.json', methods=['GET'])
def agent_card():
    card = {
        "name": "APE AI Agent",
        "version": "1.0",
        "description": "An A2A agent with six basic capabilities for practicing agent design.",
        "endpoints": [
            {
            "url": "http://127.0.0.1:5000/v1/messages",
            "type": "JSON-RPC 2.0"
            }
        ],
        "capabilities": [
            "llm-style general QA",
            "tool usage",
            "image understanding",
            "web browsing",
            "code execution",
            "memory"
        ]
    }
    return jsonify(card)

@app.route('/', methods=['POST'])
def handle_message():
    try:
        data = request.get_json()
        message = data['params']['message']
        parts = message.get('parts', [])
        request_id = data.get('id')
        result_text = ""

        image_part = next((p for p in parts if p.get('kind') == 'image'), None)
        text_part = next((p for p in parts if p.get('kind') == 'text'), None)
        
        if image_part and text_part:
            prompt = text_part.get('text', 'Describe this image.')
            possible_keys = ['base64', 'data', 'content', 'image_data']
            image_base64 = None
            for key in possible_keys:
                if key in image_part: image_base64 = image_part[key]; break
            if not image_base64: result_text = "Error: Image part received but no valid image data key was found."
            else: result_text = capabilities.understand_image(image_base64, prompt)

        elif text_part:
            original_prompt = text_part.get('text', '')
            prompt_text = original_prompt.lower()
            
            recall_keywords = ['do you remember', 'what did i tell you', 'check your memory', 'what was paired with']
            storage_keywords = ['remember that', 'remember this', 'store this', 'for future reference'] # Expanded keywords
            code_keywords = ['calculate', 'compute', 'what is the result', 'program for', 'sum of squares']
            url_match = re.search(r'(https?://\S+)', original_prompt)

            if any(keyword in prompt_text for keyword in recall_keywords):
                numbers_found = re.findall(r'\d+', original_prompt)
                if not numbers_found:
                    result_text = "I'm sorry, please specify a number for me to search for in my memory."
                else:
                    query = numbers_found[0]
                    result_text = capabilities.recall_memories(query, original_prompt, memory_db)
            
            elif any(keyword in prompt_text for keyword in storage_keywords):
                fact_extraction_prompt = f"From the user's request, extract only the core fact or piece of information they want me to remember. For example, from 'Please remember this for later: the secret code is 1234', you would extract 'the secret code is 1234'. From the request '{original_prompt}', extract the core fact."
                response = capabilities.client.chat(model='llama3', messages=[{'role': 'user', 'content': fact_extraction_prompt}], options={'temperature': 0.0})
                fact_to_remember = response['message']['content'].strip().replace('"', '')
                
                fact_key = f"fact_{len(memory_db) + 1}"
                memory_db[fact_key] = fact_to_remember
                result_text = "OK, I've remembered that."
            
            elif any(keyword in prompt_text for keyword in code_keywords):
                result_text = capabilities.code_interpreter(original_prompt)
            
            elif "browse" in prompt_text or url_match:
                url = url_match.group(0).strip() if url_match else None
                query = original_prompt.replace(url, '').strip() if url else original_prompt
                if not url: result_text = "Please provide a URL to browse."
                else: result_text = capabilities.smart_browse(url=url, query=query)
            
            elif "hash" in prompt_text:
                params = capabilities.get_hash_params(original_prompt)
                if "error" in params: result_text = params["error"]
                else: result_text = capabilities.execute_hash_sequence(**params)
            
            else:
                result_text = capabilities.general_qa(original_prompt)
        
        else:
            return jsonify({"jsonrpc": "2.0", "error": {"code": -32602, "message": "Invalid params: No valid message parts found"}, "id": request_id}), 400

        normalized_text = str(result_text).replace('*', '').lower().strip()
        response_message = {"messageId": str(uuid.uuid4()), "role": "agent", "parts": [{"kind": "text", "text": normalized_text}]}
        json_rpc_response = { "jsonrpc": "2.0", "result": {"message": response_message}, "id": request_id }
        return jsonify(json_rpc_response)

    except Exception as e:
        return jsonify({"jsonrpc": "2.0", "error": {"code": -32000, "message": f"Server error: {e}"}, "id": data.get('id') if 'data' in locals() else None}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)