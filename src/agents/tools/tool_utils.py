import subprocess
import os
from typing import List, Dict, Any, Set



def kill_service_on_port(port):
    """
    Finds the process running on the specified port and terminates it.

    Args:
        port (int): The port number to check and terminate the corresponding process.

    Returns:
        str: A message indicating the result of the operation.
    """
    try:
        # Run the `ss` command to find the process using the specified port
        cmd = f"ss -tulnp | grep :{port}"
        result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
        
        if result.returncode != 0 or not result.stdout.strip():
            return f"No process found running on port {port}."
        
        # Extract the process ID (PID) from the output
        output = result.stdout.strip()
        pid_start = output.find("pid=")
        if pid_start == -1:
            return f"Could not find the PID for port {port} in the output: {output}"
        
        pid_start += len("pid=")
        pid_end = output.find(",", pid_start)
        pid = output[pid_start:pid_end].strip()
        
        # Kill the process
        os.kill(int(pid), 9)  # Signal 9 is SIGKILL
        return f"Successfully terminated the process with PID {pid} running on port {port}."
    
    except ValueError as ve:
        return f"Error parsing PID: {ve}"
    except PermissionError:
        return "Permission denied. Please run this script with sudo or as root."
    except Exception as e:
        return f"An error occurred: {e}"


if __name__ == "__main__":
    port_to_kill = 3000  # Example port
    result = kill_service_on_port(port_to_kill)
    print(result)

    port_to_kill = 3001  # Example port
    result = kill_service_on_port(port_to_kill)
    print(result)