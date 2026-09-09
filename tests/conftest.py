"""
Pytest configuration file for setting up test environment
"""

import sys
from pathlib import Path

# Add the project root directory to Python path
# This allows imports like 'from scraper import ConcertScraper' to work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
