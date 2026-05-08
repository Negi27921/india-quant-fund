import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.cloud_main import app  # noqa: E402  slim app — market, chat, screener only
