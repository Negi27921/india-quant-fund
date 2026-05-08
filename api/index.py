import sys, os
# Expose repo root so `from api.main import ...` resolves correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.main import app as handler  # noqa: E402  (Vercel looks for `handler` or `app`)
