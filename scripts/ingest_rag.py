"""
This is a script to ingest RAG data into for the Treaty Analyzer Workflow.

It needs to be run from the `py/apps/agent-process` directory of the Chariot monorepo.

Place documents in the `docs` subdirectory of that directory.
"""

from agent_process.scripts.initialize_rag import ingest_local_rag_data
import logging

model_config = {
  "ai_provider": "chariot",
  "name": "sentence-transformers/all-MiniLM-L6-v2",
  "organization_name": "USAREUR-AF",
  "project_name": "Data Operations",
  "embedding_size": 384
}
directory = "docs"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ingest_local_rag_data(directory, model_config)
