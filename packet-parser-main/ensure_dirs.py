import os
from pathlib import Path

def ensure_directories_exist():
    """Ensure that all required directories exist."""
    base_dir = Path(__file__).parent
    required_dirs = [
        'p-docx',
        'output',
        'p-pdf',
        'packets'
    ]
    
    for dir_name in required_dirs:
        dir_path = base_dir / dir_name
        dir_path.mkdir(exist_ok=True)
        print(f"Ensured directory exists: {dir_path}")

if __name__ == "__main__":
    ensure_directories_exist()
