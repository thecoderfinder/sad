import os
import sys
import subprocess

def install_packages():
    packages = ["pyautogui", "psutil"]
    for package in packages:
        try:
            __import__(package)
            print(f"{package} is already installed.")
        except ImportError:
            print(f"Installing {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

if __name__ == "__main__":
    install_packages()
    print("All packages are installed.")
