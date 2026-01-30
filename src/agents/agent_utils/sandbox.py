#!/usr/bin/env python3
"""
Docker sandbox utilities for running agent sessions.
"""

import hashlib
import os
import time
import subprocess
import yaml

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


def create_docker_compose_file(working_dir: str, log_dir: str, compose_path: str):
    """Create a generic Docker Compose file for the agent session."""
    project_root      = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    linux_project_root = convert_windows_path_to_linux(project_root)
    linux_log_dir      = convert_windows_path_to_linux(log_dir)
    linux_working_dir  = convert_windows_path_to_linux(working_dir)

    # ──────────────────────────────────────────────────────────────────
    # Construct a deterministic hash from the human-readable container name
    # ──────────────────────────────────────────────────────────────────
    readable_name   = os.path.basename(os.path.dirname(compose_path))
    name_hash       = _hash_name(readable_name)          # 12-char hex
    container_name  = f"container_{name_hash}"     # keep some context
    volume_prefix   = f"postgres_data_{name_hash}"
    network_name    = f"webgen_network_{name_hash}"
    # ──────────────────────────────────────────────────────────────────

    db_dir = os.path.join(log_dir, "db")
    os.makedirs(db_dir, exist_ok=True)

    compose_content = {
        "services": {
            "workspace": {
                "container_name": container_name,
                "image": "webgen-agent-postgres:latest",
                "tty": True,
                "stdin_open": True,
                "command": ["sleep", "infinity"],
                "volumes": [
                    f"{working_dir}:{linux_working_dir}",
                    f"{log_dir}:{linux_log_dir}",
                    f"{volume_prefix}:/var/lib/postgresql/14/main",
                    f"{project_root}:{linux_project_root}:ro",
                ],
                "environment": {
                    "DB_HOST": "localhost",
                    "DB_PORT": 5432,
                    "DB_USERNAME": "myappuser",
                    "DB_PASSWORD": "myapppassword",
                    "DB_NAME": "myapp",
                },
                "networks": [network_name],
            }
        },
        "volumes": {
            volume_prefix: {
                "driver": "local",
                "driver_opts": {
                    "type": "none",
                    "o": "bind",
                    "device": db_dir,
                },
            }
        },
        "networks": {
            network_name: {
                "driver": "bridge",
                "external": False,
            }
        },
    }

    with open(compose_path, "w", encoding="utf-8") as fh:
        yaml.dump(compose_content, fh, default_flow_style=False, sort_keys=False)

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