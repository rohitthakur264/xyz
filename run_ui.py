import subprocess
import sys

if __name__ == "__main__":
    print("Starting Streamlit UI on http://localhost:8501")
    try:
        subprocess.run([sys.executable, "-m", "streamlit", "run", "ui/app.py", "--server.port", "8501"])
    except KeyboardInterrupt:
        print("Stopping Streamlit...")
