import re

# A word token: starts alphanumeric, then alphanumerics, underscores or hyphens.
# Shared by the hash embedder and the heuristic answerer so they tokenise alike.
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
