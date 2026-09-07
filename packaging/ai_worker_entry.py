"""Frozen worker entry point; all inference executes outside the Qt process."""
from multiprocessing import freeze_support

if __name__ == "__main__":
    freeze_support()
    from app.ai_worker import main
    raise SystemExit(main())
