import os
import subprocess
import json
import re
import time
import sys
import shlex

from pathlib import Path
from typing import Union, Optional


WRAPPER_FILENAME = "start-wrapper.cjs"
DETECTION_TIMEOUT = 60  # seconds
PM2_LOG_DIR = os.path.expanduser("~/.pm2/logs")

WRAPPER_TEMPLATE = """
const {{ spawn }} = require('child_process');

const child = spawn({command}, {args}, {{
  shell: true,
  stdio: 'inherit',
  windowsHide: true
}});

child.on('error', err => {{
  console.error('Failed to start child process:', err);
}});
"""

def remove_files_in_dir(dir_path: str) -> None:
    """
    Delete every regular file in *dir_path*.
    Sub‑directories (and their contents) are left untouched.
    """
    for entry in os.listdir(dir_path):
        fp = os.path.join(dir_path, entry)
        if os.path.isfile(fp):
            os.remove(fp)



def load_json(in_file):
    with open(in_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def find_node_apps(base_dir):
    return [f for f in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, f))]


def parse_start_command(command_str):
    parts = shlex.split(command_str)
    command = json.dumps(parts[0])
    args = json.dumps(parts[1:])
    return command, args


def create_wrapper_script(app_dir, start_command):
    command, args = parse_start_command(start_command)
    script_content = WRAPPER_TEMPLATE.format(command=command, args=args)
    # replace("{command}", command).replace("{args}", args)
    wrapper_path = os.path.join(app_dir, WRAPPER_FILENAME)
    with open(wrapper_path, "w", encoding="utf-8") as f:
        f.write(script_content.strip())
    print(f"📝 Created wrapper in {wrapper_path}")


def generate_ecosystem_config(apps, base_dir, commands):
    apps_config = []
    for app in apps:
        app_path = get_app_path(base_dir, app)
        create_wrapper_script(app_path, commands[app]["last_start_action"])
        apps_config.append({
            "name": app,
            "cwd": app_path,
            "script": "node",
            "args": WRAPPER_FILENAME
        })
    return {"apps": apps_config}


def write_ecosystem_file(config, output_file):
    content = "module.exports = " + json.dumps(config, indent=2) + ";"
    with open(output_file, "w") as f:
        f.write(content)
    print(f"✅ Generated {output_file}")


def get_app_path(base_dir, app):
    app_path = os.path.join(base_dir, app)
    if len(os.listdir(app_path)) == 1 and os.path.isdir(os.path.join(app_path, os.listdir(app_path)[0])):
        app_path = os.path.join(app_path, os.listdir(app_path)[0])
    return app_path


def replace_string(
    path: Union[str, Path],
    old: str,
    new: str,
    *,
    regex: bool = False,
    flags: int = 0
) -> int:
    """
    Replace text in *path*.

    Parameters
    ----------
    path   : file path (str or pathlib.Path)
    old    : text or regular-expression pattern to be replaced
    new    : replacement text
    regex  : if True, treat *old* as a regular expression (default False)
    flags  : regex flags forwarded to re.sub / re.subn  (e.g. re.MULTILINE)

    Returns
    -------
    int – number of replacements performed
    """
    path = Path(path)

    content = path.read_text(encoding="utf-8")

    if regex:
        content, n = re.subn(old, new, content, flags=flags)
    else:
        n = content.count(old)
        content = content.replace(old, new)

    path.write_text(content, encoding="utf-8")
    return n


def find_port(path: str | Path, key: str = "PORT") -> Optional[int]:
    """
    Return the integer value assigned to KEY in an ``.env``-style file.

    Parameters
    ----------
    path : str | pathlib.Path
        Path to the file to be scanned.
    key  : str, default ``"PORT"``
        The variable name to look for (e.g. "PORT", "DB_PORT").

    Returns
    -------
    int | None
        • The first numeric value found for KEY  
        • ``None`` if KEY is not present or no number follows it.

    Examples
    --------
    >>> find_port("backend/.env")
    3001
    >>> find_port("backend/.env", key="DB_PORT")
    5432
    """
    if not os.path.isfile(path):
        return None
    pattern = rf"^{re.escape(key)}\s*=\s*(\d+)"      # capture digits after KEY=
    text = Path(path).read_text(encoding="utf-8")

    match = re.search(pattern, text, flags=re.M)
    return int(match.group(1)) if match else None


def run_npm_install(apps, base_dir, commands):
    for app in apps:
        print(f"📦 Installing dependencies for {app}...")
        app_path = get_app_path(base_dir, app)
        old_str = "DB_HOST=workspace"
        new_str = "DB_HOST=localhost"
        if os.path.isfile(os.path.join(app_path, "backend/.env")):
            replace_string(os.path.join(app_path, "backend/.env"), old_str, new_str)

        backend_port = find_port(os.path.join(app_path, "backend/.env"))
        if backend_port is not None:
            kill_service_on_port(backend_port)

        frontend_port = find_port(os.path.join(app_path, "frontend/.env.local"))
        if frontend_port is not None:
            kill_service_on_port(frontend_port)
        
        for cmd in commands[app]["shell_actions"]:
            try:
                subprocess.run(cmd, shell=True, cwd=app_path, check=True)
            except:
                print(f"Install error when executing: {cmd}")


def run_command(cmd):
    kwargs = dict(shell=True)
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.run(cmd, **kwargs)


def start_pm2(ecosystem_file):
    print("🚀 Starting apps with PM2...")
    run_command("pm2 delete all")
    run_command(f"pm2 start {ecosystem_file}")


def detect_ports_from_pm2_logs(apps):
    results = {
        "log_files": {},
    }
    print("🔍 Detecting ports from PM2 logs...")
    
    port_pattern = re.compile(r"http[s]?://(?:localhost|127\.0\.0\.1):(\d+)", re.IGNORECASE)
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')    

    start_time = time.time()
    while time.time() - start_time < DETECTION_TIMEOUT:
        for app in apps:
            if app in results:
                continue

            log_file = os.path.join(PM2_LOG_DIR, f"{app.replace('_', '-')}-out.log")
            if not os.path.exists(log_file):
                continue

            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                content = ansi_escape.sub('', content).strip()
                print(content)
                match = port_pattern.search(content)
                if match:
                    port = int(match.group(1))
                    print(f"✅ {app} is running on port {port}")
                    results[app] = port
            results["log_files"][app] = log_file

        if len(results) == len(apps) + 1:
            break

        time.sleep(2)

    return results

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


def start_services(base_dir, commands):
    remove_files_in_dir(PM2_LOG_DIR)
    if not os.path.exists(base_dir):
        print(f"❌ Path does not exist: {base_dir}")
        return

    for app in commands.keys():
        if commands[app]["shell_actions"] is None or len(commands[app]["shell_actions"]) == 0:
            commands[app]["shell_actions"] = ["npm install"]
        if commands[app]["last_start_action"] is None or len(commands[app]["last_start_action"]) == 0:
            commands[app]["last_start_action"] = "npm run dev"
            package_json = os.path.join(base_dir, app, "package.json")
            if os.path.isfile(package_json):
                try:
                    data = load_json(package_json)
                    if "scripts" in data.keys() and "dev" not in data["scripts"].keys():
                        if "start" in data["scripts"].keys():
                            commands[app]["last_start_action"] = "npm run start"
                        elif "serve" in data["scripts"].keys():
                            commands[app]["last_start_action"] = "npm run serve"
                            if "build" in data["scripts"].keys():
                                commands[app]["shell_actions"].append("npm run build")
                except:
                    print("[WARNING] get package.json failed")

    ecosystem_path = os.path.join(base_dir, "ecosystem.config.js")
    output_path = os.path.join(base_dir, "services.json")

    apps = commands.keys()
    if not apps:
        print("❌ No Node.js apps found.")
        return

    run_npm_install(apps, base_dir, commands)

    config = generate_ecosystem_config(apps, base_dir, commands)
    write_ecosystem_file(config, ecosystem_path)

    kill_service_on_port(3000)
    kill_service_on_port(3001)

    start_pm2(ecosystem_path)

    ports = detect_ports_from_pm2_logs(apps)

    with open(output_path, "w") as f:
        json.dump(ports, f, indent=2)

    print(f"📄 Saved service ports to {output_path}")
    return ports


if __name__ == "__main__":
    kill_service_on_port(3000)
    kill_service_on_port(3001)