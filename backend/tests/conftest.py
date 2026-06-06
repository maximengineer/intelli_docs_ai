import os

# Keep the suite hermetic: never touch the network or a real provider, even when
# a populated .env is present. Environment variables take precedence over .env in
# pydantic-settings, and this runs before any app import (so cached settings see
# it), which forces the deterministic offline path:
#   - ENABLE_LLM=false           -> generation/extraction/summary use heuristics
#   - EMBEDDING_BACKEND=hash      -> retrieval uses the local hash embedder
#   - VECTOR_STORE_BACKEND=memory -> no database connection at import or runtime
os.environ["ENABLE_LLM"] = "false"
os.environ["EMBEDDING_BACKEND"] = "hash"
os.environ["VECTOR_STORE_BACKEND"] = "memory"
os.environ.pop("DATABASE_URL", None)
