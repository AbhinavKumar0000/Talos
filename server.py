from fastmcp import FastMCP
import psutil
import os
import platform
import shutil
from datetime import datetime

# Initialize the Server
mcp = FastMCP("LocalHostMedic")

@mcp.tool()
def get_system_vitals():
    """
    Get a health check of the current system. 
    Returns CPU usage, Memory usage, Battery status, and Boot time.
    """
    # CPU & Memory
    cpu_usage = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    
    # Battery (Handle cases where no battery exists like Desktops)
    battery = psutil.sensors_battery()
    battery_status = "No Battery/Desktop"
    if battery:
        plugged = "Plugged In" if battery.power_plugged else "On Battery"
        battery_status = f"{battery.percent}% ({plugged})"

    # Boot time calculation
    boot_time = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "cpu_usage_percent": cpu_usage,
        "ram_usage_percent": memory.percent,
        "ram_available_gb": round(memory.available / (1024**3), 2),
        "battery_status": battery_status,
        "boot_time": boot_time,
        "os_platform": f"{platform.system()} {platform.release()}"
    }

@mcp.tool()
def list_top_processes(limit: int = 5, sort_by: str = "memory"):
    """
    List the most resource-intensive processes running right now.
    Args:
        limit: Number of processes to return (default 5).
        sort_by: Sort by 'memory' or 'cpu'.
    """
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'username', 'memory_percent', 'cpu_percent']):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Sort based on user preference
    if sort_by == "cpu":
        procs.sort(key=lambda x: x['cpu_percent'], reverse=True)
    else:
        procs.sort(key=lambda x: x['memory_percent'], reverse=True)

    return procs[:limit]

@mcp.tool()
def kill_process(pid: int):
    """
    Terminates a specific process by its Process ID (PID).
    Use list_top_processes first to find the PID.
    """
    try:
        p = psutil.Process(pid)
        p.terminate()
        return f"Success: Process {pid} ({p.name()}) has been terminated."
    except psutil.NoSuchProcess:
        return f"Error: Process with PID {pid} not found."
    except psutil.AccessDenied:
        return f"Error: Permission denied. You cannot kill PID {pid}."
    

import speedtest
import pyautogui

@mcp.tool()
def check_internet_speed():
    """
    Checks current internet download and upload speeds.
    Note: This takes about 10-20 seconds to run.
    """
    try:
        st = speedtest.Speedtest()
        st.get_best_server()
        download_mbps = round(st.download() / (1024 * 1024), 2)
        upload_mbps = round(st.upload() / (1024 * 1024), 2)
        ping = st.results.ping
        return {
            "download_speed": f"{download_mbps} Mbps",
            "upload_speed": f"{upload_mbps} Mbps",
            "ping": f"{ping} ms"
        }
    except Exception as e:
        return f"Error checking speed: {str(e)}"
    


@mcp.tool()
def take_screenshot(filename: str = "screenshot.png"):
    """
    Takes a screenshot of the current screen and saves it.
    Args:
        filename: Name of the file (default: screenshot.png)
    """
    # Get the path to your Desktop or a safe folder
    save_path = os.path.join(os.path.expanduser("~"), "Desktop", filename)
    
    screenshot = pyautogui.screenshot()
    screenshot.save(save_path)
    
    return f"Screenshot saved to: {save_path}"

@mcp.tool()
def get_disk_usage():
    """Returns the storage usage for the main disk."""
    total, used, free = shutil.disk_usage("/")
    
    return {
        "total_gb": round(total / (1024**3), 2),
        "used_gb": round(used / (1024**3), 2),
        "free_gb": round(free / (1024**3), 2),
        "percent_used": round((used / total) * 100, 1)
    }

@mcp.tool()
def find_large_files(directory: str, min_size_mb: int = 500):
    """
    Scans a specific directory for files larger than a certain size.
    Args:
        directory: The path to scan (e.g., 'C:/Users/Name/Downloads').
        min_size_mb: Minimum file size to flag in Megabytes.
    """
    large_files = []
    min_size_bytes = min_size_mb * 1024 * 1024
    
    # Safety Check: Prevent scanning root directly to avoid hanging
    if len(directory) < 4 and platform.system() == "Windows":
        return "Safety Error: Please specify a subfolder (e.g., C:/Users), not the root drive."

    if not os.path.exists(directory):
        return f"Error: Directory '{directory}' not found."

    count = 0
    # Walk through directory
    for root, _, files in os.walk(directory):
        if count > 50: break # Hard limit to prevent context overflow
        for name in files:
            try:
                filepath = os.path.join(root, name)
                size = os.path.getsize(filepath)
                if size > min_size_bytes:
                    large_files.append({
                        "file": name,
                        "path": filepath,
                        "size_mb": round(size / (1024 * 1024), 2)
                    })
                    count += 1
            except OSError:
                continue # Skip files we can't access
                
    return large_files if large_files else "No large files found."

@mcp.tool()
def organize_desktop():
    """
    Organizes the User's Desktop by moving files into folders 
    (Images, Documents, Code) based on file extensions.
    """
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    
    # Define rules
    folders = {
        "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp"],
        "Documents": [".pdf", ".docx", ".txt", ".xlsx", ".pptx"],
        "Code": [".py", ".js", ".html", ".css", ".cpp", ".json"],
        "Archives": [".zip", ".rar", ".7z", ".tar"]
    }
    
    moved_count = 0
    
    for filename in os.listdir(desktop):
        file_path = os.path.join(desktop, filename)
        
        # Skip directories
        if os.path.isdir(file_path):
            continue
            
        # Get extension
        _, ext = os.path.splitext(filename)
        ext = ext.lower()
        
        # Move file
        for folder_name, extensions in folders.items():
            if ext in extensions:
                target_folder = os.path.join(desktop, folder_name)
                os.makedirs(target_folder, exist_ok=True)
                shutil.move(file_path, os.path.join(target_folder, filename))
                moved_count += 1
                break
                
    return f"Organization Complete: Moved {moved_count} files."

if __name__ == "__main__":
    mcp.run()