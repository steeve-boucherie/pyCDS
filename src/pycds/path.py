"""Path handler"""
from pathlib import Path


# PROJECT ROOT
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

# OUTPUT FOLDERS
DOWNLOAD_FOLDER: Path = PROJECT_ROOT / 'downloads'
TMP_FOLDER: Path = PROJECT_ROOT / 'tmp'
