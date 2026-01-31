#!/usr/bin/env python3
"""
Docker sandbox utilities for running agent sessions.
"""
from __future__ import annotations

import os
import subprocess
import time
import yaml
import re

import sys
from typing import List

import docker
from docker.errors import APIError, DockerException


def free_docker_port(
    port: int,
    *,
    remove: bool = True,
    stop_timeout: int = 5,
) -> List[str]:
    """
    Free a host TCP port from any Docker container that maps it.

    Parameters
    ----------
    port : int
        Host-side TCP port to free.
    remove : bool, default True
        If True, containers are removed after they are stopped.
    stop_timeout : int, default 5
        Seconds to wait for a graceful stop before the container is killed.

    Returns
    -------
    list[str]
        List of container IDs that were affected.

    Raises
    ------
    docker.errors.DockerException
        If the Docker engine is unreachable or an API error occurs.
    """
    if not (1 <= port <= 65535):
        raise ValueError("port must be an integer between 1 and 65535")

    client = docker.from_env()
    affected: List[str] = []

    for container in client.containers.list(all=True):
        # Ports is a dict like {"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5434"}]}
        ports = container.attrs.get("NetworkSettings", {}).get("Ports") or {}
        for _container_port, bindings in ports.items():
            if bindings is None:                        # port not published
                continue
            for bind in bindings:                       # may be multiple host ports
                if int(bind["HostPort"]) == port:
                    cid = container.id
                    affected.append(cid)
                    name = container.name
                    print(f"→ Container {name} ({cid[:12]}) publishes port {port}")

                    if container.status == "running":
                        print(f"  • Stopping …")
                        container.stop(timeout=stop_timeout)

                    if remove:
                        print(f"  • Removing …")
                        container.remove()
                    else:
                        print(f"  • Left stopped (not removed)")

                    # a container can only publish the same host port once
                    break

    if affected:
        print(f"✔ Port {port} freed from {len(affected)} container(s).")
    else:
        print(f"ℹ No container was publishing port {port}.")

    return affected


def convert_windows_path_to_linux(path):
    """
    Convert a Windows path to a Linux path if it's detected as a Windows path.
    
    Args:
        path (str): The path to convert
        
    Returns:
        str: The converted path if it was Windows style, original path otherwise
    """
    # Check if this is a Windows path (starts with drive letter like C:\)
    windows_path_pattern = re.compile(r'^[a-zA-Z]:\\')
    
    if windows_path_pattern.match(path):
        # Convert backslashes to forward slashes
        linux_path = path.replace('\\', '/')
        
        # Convert drive letter to lowercase and prepend with /
        drive_letter = linux_path[0].lower()
        linux_path = f'/{drive_letter}{linux_path[2:]}'
        
        return linux_path
    
    # Return original path if not a Windows path
    return path


def write_logging_conf(conf_path: str) -> None:
    """
    Create a tiny PostgreSQL conf.d fragment that enables statement logging
    into CSV files.  The file is idempotent – it is only rewritten if missing.
    """
    if os.path.exists(conf_path):
        return

    os.makedirs(os.path.dirname(conf_path), exist_ok=True)
    with open(conf_path, "w", encoding="utf-8") as f:
        f.write(
            "# Automatically generated – do not edit inside the container\n"
            "logging_collector = on\n"
            "log_destination   = 'csvlog'\n"
            "log_statement     = 'all'\n"
            "log_duration      = on\n"
        )
    print(f"✔ logging.conf written to {conf_path}")


def create_docker_compose_file(
    working_dir: str,
    log_dir: str,
    compose_path: str,
    db_dir: str,
    *,
    db_port: int = 5432,
) -> None:
    """
    Build a docker-compose YAML that

    • bind-mounts *db_dir* at /var/lib/postgresql/14/main
    • binds *logging.conf* at /etc/postgresql/14/main/conf.d/90-logging.conf
    """
    linux_working_dir = convert_windows_path_to_linux(working_dir)
    linux_log_dir = convert_windows_path_to_linux(log_dir)
    linux_db_dir = convert_windows_path_to_linux(db_dir)

    sample_id = os.path.basename(log_dir)  # → volume name uniqueness

    # ---------- write the logging.conf next to the compose file -------------
    host_conf_path = os.path.join(os.path.dirname(compose_path), "logging.conf")
    write_logging_conf(host_conf_path)
    linux_host_conf_path = convert_windows_path_to_linux(host_conf_path)

    os.makedirs(db_dir, exist_ok=True)

    # ---------- compose content ---------------------------------------------
    compose_content = {
        "services": {
            "workspace": {
                "image": "webgen-agent-postgres:latest",
                "tty": True,
                "stdin_open": True,
                "command": ["sleep", "infinity"],
                "volumes": [
                    f"postgres_data_{sample_id}:/var/lib/postgresql/14/main",
                    f"{linux_host_conf_path}:/etc/postgresql/14/main/conf.d/90-logging.conf:ro",
                ],
                "environment": {
                    "DB_HOST": "localhost",
                    "DB_PORT": db_port,
                    "DB_USERNAME": "myappuser",
                    "DB_PASSWORD": "myapppassword",
                    "DB_NAME": "myapp",
                },
                "ports": [f"{db_port}:5432"],
            }
        },
        "volumes": {
            f"postgres_data_{sample_id}": {
                "driver": "local",
                "driver_opts": {
                    "type": "none",
                    "o": "bind",
                    "device": linux_db_dir,
                },
            }
        },
    }

    os.makedirs(os.path.dirname(compose_path), exist_ok=True)
    with open(compose_path, "w", encoding="utf-8") as fh:
        yaml.dump(compose_content, fh, default_flow_style=False, sort_keys=False)

    print(f"✔ docker-compose file written to {compose_path}")


def start_docker_containers(compose_path: str):
    """Start Docker containers using the compose file"""
    print("Starting Docker containers...")
    for attempt in range(3):  # Retry up to 3 times
        try:
            result = subprocess.run(["docker", "compose", "-f", compose_path, "up", "-d", "--remove-orphans"], 
                                  check=True, capture_output=True, text=True)
            print(result)
            
            print("Docker containers started successfully")
            return True
        except subprocess.CalledProcessError as e:
            error_output = e.stderr.lower()
            if "network" in error_output and "not found" in error_output and attempt < 2:
                print(f"Network error on attempt {attempt + 1}, retrying in 5 seconds...")
                print(f"Error details: {e.stderr}")
                time.sleep(5)
                continue
            else:
                print(f"Failed to start Docker containers after {attempt + 1} attempts")
                print(f"Stderr: {e.stderr}")
                print(f"Stdout: {e.stdout}")
                return False
    return False


def stop_docker_containers(compose_path: str):
    """Stop Docker containers using the compose file"""
    print("Stopping Docker containers...")
    try:
        # First try to stop gracefully
        subprocess.run(["docker", "compose", "-f", compose_path, "down", "-v", "--remove-orphans"], check=True, timeout=30)
        print("Docker containers stopped successfully")
        return True
    except subprocess.TimeoutExpired:
        print("Graceful shutdown timed out, forcing stop...")
        try:
            # Force stop if graceful shutdown fails
            subprocess.run(["docker", "compose", "-f", compose_path, "down", "-v", "--remove-orphans"], check=True, timeout=30)
            print("Docker containers force stopped successfully")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"Failed to stop Docker containers: {e}")
            # Try to clean up any remaining containers
            try:
                subprocess.run(["docker", "compose", "-f", compose_path, "kill"], check=True, timeout=10)
                subprocess.run(["docker", "compose", "-f", compose_path, "rm", "-f", "-v"], check=True, timeout=10)
                print("Docker containers killed and removed")
            except Exception as cleanup_error:
                print(f"Failed to cleanup containers: {cleanup_error}")
            return False
    except subprocess.CalledProcessError as e:
        print(f"Failed to stop Docker containers: {e}")
        return False


if __name__ == "__main__":
    working_dir = r'D:\research\TDDev\outputs\test\example_workspace'
    log_dir = r'D:\research\TDDev\outputs\test\example_log'
    compose_path = r'D:\research\TDDev\outputs\test\docker-compose.yml'
    db_dir = r'D:\research\TDDev\outputs\test\example_db'
    DB_PORT = 5432
    create_docker_compose_file(working_dir, log_dir, compose_path, db_dir, db_port=DB_PORT)
    stop_docker_containers(compose_path)
    free_docker_port(DB_PORT)
    start_docker_containers(compose_path)
    stop_docker_containers(compose_path)