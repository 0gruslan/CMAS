import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(_repo_root, "shared"))
sys.path.insert(0, os.path.dirname(__file__))
