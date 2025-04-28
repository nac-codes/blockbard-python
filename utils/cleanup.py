import os
import signal
import subprocess
import sys

def get_processes_using_ports(ports):
    """
    Get processes using the specified ports.
    
    Args:
        ports: List of port numbers
        
    Returns:
        Dictionary mapping ports to PIDs
    """
    port_to_pid = {}
    
    for port in ports:
        try:
            # For macOS, use lsof
            if sys.platform == 'darwin':
                cmd = f"lsof -i :{port} -t"
                result = subprocess.check_output(cmd, shell=True).decode().strip()
                if result:
                    pids = result.split('\n')
                    port_to_pid[port] = [int(pid) for pid in pids]
            # For Linux, use netstat or ss
            elif sys.platform.startswith('linux'):
                cmd = f"netstat -tulpn | grep :{port} | awk '{{print $7}}' | cut -d'/' -f1"
                result = subprocess.check_output(cmd, shell=True).decode().strip()
                if result:
                    pids = result.split('\n')
                    port_to_pid[port] = [int(pid) for pid in pids if pid]
            # For Windows
            elif sys.platform == 'win32':
                cmd = f"netstat -ano | findstr :{port}"
                result = subprocess.check_output(cmd, shell=True).decode()
                if result:
                    lines = result.split('\n')
                    pids = []
                    for line in lines:
                        if f":{port}" in line:
                            parts = line.strip().split()
                            if parts and len(parts) >= 5:
                                pids.append(int(parts[-1]))
                    if pids:
                        port_to_pid[port] = pids
        except subprocess.CalledProcessError:
            # Command failed, port might not be in use
            pass
            
    return port_to_pid

def kill_processes(pids):
    """
    Kill processes with the given PIDs.
    
    Args:
        pids: List of process IDs to kill
        
    Returns:
        Number of processes successfully killed
    """
    killed = 0
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Sent SIGTERM to process {pid}")
            killed += 1
        except ProcessLookupError:
            print(f"Process {pid} not found")
        except PermissionError:
            print(f"Permission denied when trying to kill process {pid}")
        except Exception as e:
            print(f"Error killing process {pid}: {e}")
            
    return killed

def main():
    # Define ports used by our application
    tracker_port = 5500
    node_ports = [5501, 5502, 5503]
    all_ports = [tracker_port] + node_ports
    
    print(f"Checking for processes using ports: {all_ports}")
    
    # Get processes using our ports
    port_to_pid = get_processes_using_ports(all_ports)
    
    if not port_to_pid:
        print("No processes found using the specified ports.")
        return
    
    # Print and kill processes
    total_killed = 0
    for port, pids in port_to_pid.items():
        if pids:
            print(f"Port {port} is used by process(es) with PID(s): {pids}")
            killed = kill_processes(pids)
            total_killed += killed
    
    print(f"Total processes killed: {total_killed}")

if __name__ == "__main__":
    main() 