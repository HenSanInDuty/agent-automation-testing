"""
agents/ingestion/
─────────────────
Ingestion stage — no CrewAI agents.

The ingestion pipeline is implemented as a pure-Python orchestration in
``crews/ingestion_crew.py`` using direct litellm calls and the document
parser / text chunker tools.  No CrewAI Agent objects are defined here.
"""
