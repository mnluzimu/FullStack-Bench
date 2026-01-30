#!/usr/bin/env python3
"""
Docker sandbox utilities for running agent sessions.
"""
from __future__ import annotations

import re
import sys
from typing import List

import os
import subprocess
import time
import yaml
import hashlib

from .convert_path import convert_windows_path_to_linux


def _hash_name(name: str, length: int = 12) -> str:
    """
    Return the first `length` hex chars of the SHA-256 digest of `name`.

    The result is
    * deterministic      – same `name` ⇒ same hash every run
    * practically unique – collision probability ≪ 10⁻¹² for `length` ≥ 12
    * Docker-friendly    – lowercase hex, matches `[a-z0-9]+`
    """
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:length]


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


def create_docker_compose_file(working_dir: str, log_dir: str, output_dir: str, compose_path: str, db_dir: str):
    """Create a generic Docker Compose file for the agent session"""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    linux_project_root = convert_windows_path_to_linux(project_root)
    linux_log_dir = convert_windows_path_to_linux(log_dir)
    linux_working_dir = convert_windows_path_to_linux(working_dir)
    linux_output_dir = convert_windows_path_to_linux(output_dir)
    sample_id = os.path.basename(log_dir)
    
    # container_name = os.path.basename(os.path.dirname(compose_path))

    readable_name   = os.path.basename(os.path.dirname(compose_path))
    name_hash       = _hash_name(readable_name)          # 12-char hex
    container_name  = f"container_{name_hash}"     # keep some context
    volume_prefix   = f"postgres_data_{name_hash}"
    network_name    = f"webgen_network_{name_hash}"

    # ---------- write the logging.conf next to the compose file -------------
    host_conf_path = os.path.join(os.path.dirname(compose_path), "logging.conf")
    write_logging_conf(host_conf_path)
    linux_host_conf_path = convert_windows_path_to_linux(host_conf_path)

    
    # Create the Docker Compose content with unique network name
    compose_content = {
        'services': {
            'workspace': {
                'container_name': container_name,
                'image': 'webgen-agent-postgres:latest',
                'tty': True,
                'stdin_open': True,
                'command': ['sleep', 'infinity'],
                'volumes': [
                    f'{working_dir}:{linux_working_dir}',
                    f'{log_dir}:{linux_log_dir}',
                    f'{output_dir}:{linux_output_dir}',
                    f'postgres_data_{container_name}:/var/lib/postgresql/14/main',
                    f'{project_root}:{linux_project_root}:ro'
                ],
                'environment': {
                    'DB_HOST': 'localhost',
                    'DB_PORT': 5432,
                    'DB_USERNAME': 'myappuser',
                    'DB_PASSWORD': 'myapppassword',
                    'DB_NAME': 'myapp'
                },
                'networks': [f'webgen_network_{container_name}']
            }
        },
        'volumes': {
            f'postgres_data_{container_name}': {
                'driver': 'local',
                'driver_opts': {
                    'type': 'none',
                    'o': 'bind',
                    'device': db_dir
                }
            }
        },
        'networks': {
            f'webgen_network_{container_name}': {
                'driver': 'bridge',
                'external': False
            }
        }
    }
    # Save the Docker Compose file
    with open(compose_path, 'w') as f:
        yaml.dump(compose_content, f, default_flow_style=False, sort_keys=False)
    
    print(f"Docker Compose file created at: {compose_path}")


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
                subprocess.run(["docker", "compose", "-f", compose_path, "rm", "--stop", "-v", "--force"], check=True, timeout=10)
                print("Docker containers killed and removed")
            except Exception as cleanup_error:
                print(f"Failed to cleanup containers: {cleanup_error}")
            return False
    except subprocess.CalledProcessError as e:
        print(f"Failed to stop Docker containers: {e}")
        return False