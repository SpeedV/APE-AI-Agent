import os
import ollama
import requests
from bs4 import BeautifulSoup
import io
import contextlib
import base64
import json
import hashlib
import re
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager
from PIL import Image

# --- Ollama Client Setup ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
client = ollama.Client(host=OLLAMA_HOST)

AGENT_SYSTEM_PROMPT = """
Begin your response with a concise direct answer to the prompt's main question. Use clear, straightforward language and contractions. Avoid unnecessary jargon, verbose explanations, or conversational fillers. Structure the response logically. Use markdown headings (##) to create distinct sections if the response is more than a few paragraphs or covers different points, topics, or steps. If a response uses markdown headings, add horizontal lines to separate sections. Prioritize coherence over excessive fragmentation. When appropriate bold key words in the response.
"""

# --- Helper Functions ---

def is_moves_left(board):
    return '_' in board

def evaluate(board):
    # Check rows, columns, and diagonals for a win or loss
    win_conditions = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8], # rows
        [0, 3, 6], [1, 4, 7], [2, 5, 8], # columns
        [0, 4, 8], [2, 4, 6]             # diagonals
    ]
    for condition in win_conditions:
        if board[condition[0]] == board[condition[1]] == board[condition[2]]:
            if board[condition[0]] == 'X': return 10
            elif board[condition[0]] == 'O': return -10
    return 0

def minimax(board, depth, is_maximizer):
    score = evaluate(board)
    if score == 10: return score - depth
    if score == -10: return score + depth
    if not is_moves_left(board): return 0

    if is_maximizer:
        best = -1000
        for i in range(9):
            if board[i] == '_':
                board[i] = 'X'
                best = max(best, minimax(board, depth + 1, not is_maximizer))
                board[i] = '_'
        return best
    else:
        best = 1000
        for i in range(9):
            if board[i] == '_':
                board[i] = 'O'
                best = min(best, minimax(board, depth + 1, not is_maximizer))
                board[i] = '_'
        return best

def find_best_move(board):
    best_val = -1000
    best_move = -1
    for i in range(9):
        if board[i] == '_':
            board[i] = 'X'
            move_val = minimax(board, 0, False)
            board[i] = '_'
            if move_val > best_val:
                best_move = i
                best_val = move_val
    return best_move

# --- Capabilities ---

def static_browse(url: str, query: str) -> str:
    """Stage 1: Fetches and analyzes the static HTML of a page."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        full_text = str(soup)
        if not full_text:
            return "Web browsing error: Could not extract any text from the page."
        
        system_prompt = "You are a web page analysis assistant. Based on the provided HTML SOURCE CODE, your job is to answer the user's QUERY. Respond with only the specific information requested. If the information cannot be found, respond with 'Information not found.'"
        llm_prompt = f"HTML SOURCE CODE: \"\"\"{full_text[:8000]}\"\"\"\n\nQUERY: \"{query}\""
        
        response = client.chat(
            model='llama3', messages=[{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': llm_prompt}]
        )
        return response['message']['content']
    except Exception as e:
        return f"Static browsing error: {e}"

def interactive_browse(url: str, query: str) -> str:
    """Uses Selenium and the Minimax algorithm to play and win Tic-Tac-Toe."""
    driver = None
    try:
        service = FirefoxService(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service)
        driver.get(url)
        
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "cell")))

        for turn in range(5):
            board_elements = driver.find_elements(By.CLASS_NAME, "cell")
            board_state = [elem.text.upper() or '_' for elem in board_elements]

            move_index = find_best_move(board_state)
            if move_index == -1: break
            
            cells = driver.find_elements(By.CLASS_NAME, "cell")
            if 0 <= move_index < len(cells) and cells[move_index].is_enabled():
                cells[move_index].click()
            else:
                driver.quit()
                return "Error: Minimax chose an invalid square, which should not happen."

            # Check for win condition
            expected_date = datetime.utcnow().strftime('%Y%m%d')
            found_correct_number = False
            for _ in range(5): 
                try:
                    congrats_element = driver.find_element(By.ID, "congratulations")
                    congrats_text = congrats_element.text
                    match = re.search(r'\b(\d{14})\b', congrats_text)
                    if match:
                        found_number = match.group(1)
                        if found_number.startswith(expected_date):
                            driver.quit()
                            return found_number 
                except:
                    pass
                time.sleep(1)

        driver.quit()
        return "Error: Played the game but did not find the code."
    except Exception as e:
        if driver: driver.quit()
        return f"Interactive browsing error: {e}"

def smart_browse(url: str, query: str) -> str:
    """Orchestrates the two-stage browsing process."""
    print("--- Running Stage 1: Static Analysis ---")
    static_result = static_browse(url, query)
    
    if static_result and "Information not found" not in static_result:
        # Check if the static result looks like the answer
        if re.search(r'\d{14}', static_result):
             return static_result

    print("--- Static analysis failed. Escalating to Stage 2: Interactive Session ---")
    if "ttt.puppy9.com" in url:
        return interactive_browse(url, query)
    else:
        return f"Static analysis did not find the answer ('{query}'). This page is not a known interactive task."

def general_qa(prompt: str) -> str:
    response = client.chat(
        model='llama3',
        messages=[{'role': 'system', 'content': AGENT_SYSTEM_PROMPT}, {'role': 'user', 'content': prompt}]
    )
    return response['message']['content']

def understand_image(image_base64: str, prompt: str) -> str:
    """Decodes and saves the received image for debugging before sending it to the model."""
    print("DEBUG: `understand_image` function was called.")
    
    try:
        print("DEBUG: Attempting to decode base64 string...")
        if not image_base64 or len(image_base64) < 10:
            return "Error: Received an empty or invalid base64 string."
        
        image_bytes = base64.b64decode(image_base64)
        print("DEBUG: Base64 decoding successful.")
        
        image = Image.open(io.BytesIO(image_bytes))
        image.save("debug_received_image.png")
        print("DEBUG: Image successfully saved to debug_received_image.png")
    
    except Exception as e:
        print(f"DEBUG: An error occurred during decoding or saving: {e}")
        return f"Image data processing error: {e}"
    
    print("DEBUG: Sending image to the moondream model...")
    try:
        response = client.chat(
            model='moondream',
            messages=[{'role': 'user', 'content': prompt}],
            images=[image_bytes],
            options={"timeout": 60}
        )
        return response['message']['content']
    except Exception as e:
        return f"Ollama model error: {e}"

def get_math_expression(prompt: str) -> str:
    system_prompt = "You are a calculator's assistant. Given a word problem, your only job is to return the raw mathematical expression needed to solve it."
    response = client.chat(model='llama3', messages=[{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': prompt}])
    return response['message']['content'].strip().replace("`", "")

def use_calculator(expression: str) -> str:
    try:
        allowed_chars = "0123456789+-*/(). "
        if all(char in allowed_chars for char in expression):
            return str(eval(expression))
        else:
            return "Error: Invalid characters in expression."
    except Exception as e:
        return f"Calculation error: {e}"

def get_hash_params(prompt: str) -> dict:
    try:
        string_match = re.search(r'string "([^"]+)"', prompt)
        algos = re.findall(r'\b(sha512|md5)\b', prompt)
        if string_match and algos:
            return {"input_string": string_match.group(1), "algorithms": algos}
        else:
            return {"error": "Regex failed to find the required string and algorithms in the prompt."}
    except Exception as e:
        return {"error": f"An unexpected error occurred during Regex parsing: {e}"}

def execute_hash_sequence(input_string: str, algorithms: list) -> str:
    current_value = input_string
    try:
        for algo in algorithms:
            if algo not in ['md5', 'sha512']: return f"Error: Unsupported algorithm '{algo}'"
            current_bytes = current_value.encode('utf-8')
            hasher = hashlib.new(algo)
            hasher.update(current_bytes)
            current_value = hasher.hexdigest()
        return current_value
    except Exception as e:
        return f"Hashing execution error: {e}"
    
def code_interpreter(prompt: str) -> str:
    """
    Asks an LLM to generate Python code to solve a prompt, then executes the code
    and returns the output. This is a powerful and versatile tool for computational tasks.
    """
    # Step 1: Ask the LLM to generate Python code.
    system_prompt = """
    You are a world-class Python programmer. The user will provide a prompt that requires a calculation or a programmatic solution.
    Your task is to write a self-contained Python script that solves the user's prompt.
    The script MUST print the final, single numerical answer to standard output.
    Do not provide any explanation, commentary, or markdown formatting.
    Only provide the raw Python code.
    """
    
    try:
        response = client.chat(
            model='llama3',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': prompt}
            ],
            options={"temperature": 0.0}
        )
        code_to_execute = response['message']['content'].strip()
        
        # Clean the code if it's wrapped in markdown
        if code_to_execute.startswith("```python"):
            code_to_execute = code_to_execute[9:]
        if code_to_execute.startswith("```"):
            code_to_execute = code_to_execute[3:]
        if code_to_execute.endswith("```"):
            code_to_execute = code_to_execute[:-3]
        
        # Step 2: Execute the generated code and capture its output.
        output_buffer = io.StringIO()
        with contextlib.redirect_stdout(output_buffer):
            exec(code_to_execute, {})
        
        result = output_buffer.getvalue().strip()
        return result or "[No output from code execution]"

    except Exception as e:
        return f"Code interpreter error: {e}"
    
def recall_memories(query: str, original_prompt: str, db: dict) -> str:
    """
    Searches the memory database for facts relevant to a query, then uses an LLM
    to formulate a specific answer based on the user's original question.
    """
    found_facts = []
    # Find all facts that contain the query keyword
    for key, fact in db.items():
        if query.lower() in fact.lower():
            found_facts.append(fact)
    
    if not found_facts:
        return "I couldn't find any information about that in my memory."

    facts_str = "; ".join(found_facts)
    prompt = f"Based on the following stored fact(s): '{facts_str}', provide a direct answer to the user's original question: '{original_prompt}'"
    
    response = client.chat(
        model='llama3',
        messages=[{'role': 'user', 'content': prompt}]
    )
    return response['message']['content']
