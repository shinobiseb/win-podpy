"""Application entry point.

The GUI calls the shared processing pipeline, which reads its settings from
config.py. Run this file from the project launcher or with Python directly.
"""

from gui import main


if __name__ == "__main__":
    main()