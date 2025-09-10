# APE-AI-Agent

A minimal JSON-RPC 2.0 Agent communicating over A2A that supports the following basic implementations:
- General QA
- Tool usage
- Image understanding
- Web browsing
- Code execution
- Memory

### Run locally

```bash
pip install -r requirements.txt
python app.py
```

### Notes

Implemented assuming a locally hosted llm setup with ollama, using llama3 for general llm operations and moondream for image recognition. Can be changed to use OpenAI, used ollama to avoid paying for credits.
