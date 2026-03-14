#!/usr/bin/env python3
"""
Verify that all required packages are installed before starting Flask
"""

import sys
import importlib

def check_package(package_name, display_name=None):
    """Check if a package is installed"""
    display_name = display_name or package_name
    try:
        module = importlib.import_module(package_name)
        version = getattr(module, '__version__', 'unknown')
        print(f"  [OK] {display_name:20} v{version}")
        return True
    except ImportError as e:
        print(f"  [FAIL] {display_name:20} - {str(e)}")
        return False

def main():
    print("\n" + "="*60)
    print("  HEALTH AI - DEPENDENCY CHECK")
    print("="*60 + "\n")
    
    packages = [
        ('flask', 'Flask'),
        ('pandas', 'Pandas'),
        ('numpy', 'NumPy'),
        ('pdfplumber', 'PDFPlumber'),
        ('PyPDF2', 'PyPDF2'),
    ]
    
    all_ok = True
    for package_name, display_name in packages:
        if not check_package(package_name, display_name):
            all_ok = False
    
    print("\n" + "="*60)
    
    if all_ok:
        print("  [SUCCESS] All dependencies are installed!")
        print("  [INFO] Flask is ready to start...")
    else:
        print("  [ERROR] Some dependencies are missing!")
        print("  [FIX] Run: pip install -r requirements.txt")
        sys.exit(1)
    
    print("="*60 + "\n")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
