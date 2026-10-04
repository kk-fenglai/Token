"""F29 — built-in AI assistant (DeepSeek).

An in-process agent loop over TokenScope's own tools: usage Q&A, cost-saving
advice, dev-project stewardship and a scheduled patrol. The model is reached
through DeepSeek's OpenAI-compatible Chat Completions API; the tool whitelist
in `tools.py` is the main safety boundary (there is no shell, no file editing).
"""
