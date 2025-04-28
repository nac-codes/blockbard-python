import importlib
import subprocess
import sys

REQUIRED_PACKAGES = [
    "flask",
    "requests",
    "openai",
    "yaml"  # PyYAML package provides the 'yaml' module
]

def check_dependencies():
    """Checks if all required packages are installed."""
    missing_packages = []
    for package_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(package_name)
        except ImportError:
            # Map module name back to pip package name if different
            pip_package_name = package_name
            if package_name == "yaml":
                pip_package_name = "PyYAML"
            missing_packages.append(pip_package_name)

    if missing_packages:
        print("\nError: Required Python packages are missing:", file=sys.stderr)
        for pkg in missing_packages:
            print(f"  - {pkg}", file=sys.stderr)
        
        print("\nPlease install the required packages.", file=sys.stderr)
        print("It is highly recommended to use a virtual environment.", file=sys.stderr)
        print("Example commands:", file=sys.stderr)
        print("  python3 -m venv venv", file=sys.stderr)
        print("  source venv/bin/activate  # On Linux/macOS", file=sys.stderr)
        print("  .\\venv\\Scripts\\activate    # On Windows", file=sys.stderr)
        print("  pip install -r requirements.txt", file=sys.stderr)
        
        return False
    
    return True

def ensure_dependencies():
    """Checks dependencies and exits if they are not met."""
    if not check_dependencies():
        sys.exit(1) 