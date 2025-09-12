#!/usr/bin/env python3
"""
Script to extract all archive files (zip, rar, 7z) from the data folder.
Preserves original archive files after extraction.

Usage:
    python clean_data.py                    # Extract all archives from ../data
    python clean_data.py --data-dir /path   # Extract from custom directory
    python clean_data.py --dry-run          # Show what would be extracted
    python clean_data.py --verbose          # Enable verbose logging

Requirements:
    pip install py7zr rarfile
"""

import os
import sys
import zipfile
import logging
import argparse
from pathlib import Path
from typing import List, Set

# Optional imports for different archive types
try:
    import rarfile
    RAR_AVAILABLE = True
except ImportError:
    RAR_AVAILABLE = False
    print("Warning: rarfile not available. RAR files will be skipped.")

try:
    import py7zr
    SEVENZ_AVAILABLE = True
except ImportError:
    SEVENZ_AVAILABLE = False
    print("Warning: py7zr not available. 7Z files will be skipped.")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('extraction.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Supported archive extensions
ARCHIVE_EXTENSIONS = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}

def find_archive_files(data_dir: Path) -> List[Path]:
    """
    Recursively find all archive files in the data directory.
    
    Args:
        data_dir: Path to the data directory
        
    Returns:
        List of Path objects for all archive files found
    """
    archive_files = []
    
    for root, dirs, files in os.walk(data_dir):
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix.lower() in ARCHIVE_EXTENSIONS:
                archive_files.append(file_path)
    
    return archive_files

def extract_zip(archive_path: Path, extract_to: Path) -> bool:
    """
    Extract a ZIP file.
    
    Args:
        archive_path: Path to the ZIP file
        extract_to: Directory to extract to
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        return True
    except Exception as e:
        logger.error(f"Failed to extract ZIP {archive_path}: {e}")
        return False

def extract_rar(archive_path: Path, extract_to: Path) -> bool:
    """
    Extract a RAR file.
    
    Args:
        archive_path: Path to the RAR file
        extract_to: Directory to extract to
        
    Returns:
        True if successful, False otherwise
    """
    if not RAR_AVAILABLE:
        logger.error(f"Cannot extract RAR {archive_path}: rarfile library not available")
        return False
    
    try:
        with rarfile.RarFile(archive_path, 'r') as rar_ref:
            rar_ref.extractall(extract_to)
        return True
    except Exception as e:
        logger.error(f"Failed to extract RAR {archive_path}: {e}")
        return False

def extract_7z(archive_path: Path, extract_to: Path) -> bool:
    """
    Extract a 7Z file.
    
    Args:
        archive_path: Path to the 7Z file
        extract_to: Directory to extract to
        
    Returns:
        True if successful, False otherwise
    """
    if not SEVENZ_AVAILABLE:
        logger.error(f"Cannot extract 7Z {archive_path}: py7zr library not available")
        return False
    
    try:
        with py7zr.SevenZipFile(archive_path, mode='r') as z:
            z.extractall(extract_to)
        return True
    except Exception as e:
        logger.error(f"Failed to extract 7Z {archive_path}: {e}")
        return False

def extract_archive(archive_path: Path) -> bool:
    """
    Extract an archive file based on its extension.
    
    Args:
        archive_path: Path to the archive file
        
    Returns:
        True if successful, False otherwise
    """
    extension = archive_path.suffix.lower()
    extract_to = archive_path.parent
    
    logger.info(f"Extracting {archive_path.name} to {extract_to}")
    
    if extension == '.zip':
        return extract_zip(archive_path, extract_to)
    elif extension == '.rar':
        return extract_rar(archive_path, extract_to)
    elif extension == '.7z':
        return extract_7z(archive_path, extract_to)
    else:
        logger.warning(f"Unsupported archive format: {extension}")
        return False

def main():
    """
    Main function to extract all archives in the data folder.
    """
    parser = argparse.ArgumentParser(description='Extract all archive files from the data folder')
    parser.add_argument('--data-dir', type=str, help='Path to the data directory (default: ../data)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be extracted without actually extracting')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Get the data directory path
    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        # Default: assume script is in scripts/ folder
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
        data_dir = project_root / 'data'
    
    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        sys.exit(1)
    
    logger.info(f"Starting archive extraction from: {data_dir}")
    
    # Find all archive files
    archive_files = find_archive_files(data_dir)
    
    if not archive_files:
        logger.info("No archive files found in the data directory")
        return
    
    logger.info(f"Found {len(archive_files)} archive files")
    
    if args.dry_run:
        logger.info("DRY RUN - No files will be extracted")
        for archive_path in archive_files:
            logger.info(f"Would extract: {archive_path.relative_to(data_dir)}")
        return
    
    # Track extraction results
    successful = 0
    failed = 0
    
    # Extract each archive
    for i, archive_path in enumerate(archive_files, 1):
        logger.info(f"Processing {i}/{len(archive_files)}: {archive_path.relative_to(data_dir)}")
        
        if extract_archive(archive_path):
            successful += 1
            logger.info(f"✓ Successfully extracted {archive_path.name}")
        else:
            failed += 1
            logger.error(f"✗ Failed to extract {archive_path.name}")
    
    # Summary
    logger.info(f"\nExtraction complete!")
    logger.info(f"Successfully extracted: {successful}")
    logger.info(f"Failed extractions: {failed}")
    logger.info(f"Total archives processed: {len(archive_files)}")

if __name__ == "__main__":
    main()
