import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from app.extensions import db


def main():
    app = create_app()
    with app.app_context():
        db.create_all()
        print("OK: db.create_all() completed")


if __name__ == "__main__":
    main()

