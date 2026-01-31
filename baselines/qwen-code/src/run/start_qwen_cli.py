#!/usr/bin/env python3
"""
Python script to automatically start the Qwen Code CLI and input a user instruction.
This script uses subprocess to launch the CLI with the appropriate arguments.
"""

import subprocess
import sys
import os
import argparse
import logging
from typing import Optional


def setup_logging(log_file_path: Optional[str] = None):
    """
    Set up logging configuration.

    Args:
        log_file_path: Optional path to log file. If None, logs to console only.
    """
    # Configure logging format
    log_format = '%(asctime)s - %(levelname)s - %(message)s'

    if log_file_path:
        # Create directory if it doesn't exist
        log_dir = os.path.dirname(log_file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # Configure logging to file and console
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler(log_file_path),
                logging.StreamHandler(sys.stdout)
            ]
        )
    else:
        # Configure logging to console only
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[logging.StreamHandler(sys.stdout)]
        )


def start_qwen_cli(
    prompt: str,
    working_dir: str,
    model: Optional[str] = None,
    debug: bool = False,
    output_format: str = "text",
    approval_mode: str = "default",
    all_files: bool = False,
    show_memory_usage: bool = False,
    yolo: bool = False,
    auth_type: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
    additional_args: Optional[list] = None,
    log_file_path: Optional[str] = None,
    timeout: Optional[int] = None,
) -> int:
    """
    Start the Qwen Code CLI with a specific prompt and optional authentication settings.

    Args:
        prompt: The user instruction to send to the CLI
        model: The model to use (optional)
        debug: Enable debug mode
        output_format: Output format (text, json, stream-json)
        approval_mode: Approval mode (plan, default, auto-edit, yolo)
        all_files: Include all files in context
        show_memory_usage: Show memory usage
        yolo: Enable YOLO mode (auto-approve all actions)
        auth_type: Authentication type (qwen-oauth or use-openai)
        openai_api_key: OpenAI API key (for OpenAI-compatible API)
        openai_base_url: OpenAI base URL (for custom endpoints)
        additional_args: Additional command line arguments to pass to the CLI
        log_file_path: Optional path to log file where output will be saved

    Returns:
        The exit code of the CLI process
    """
    # Set up logging
    setup_logging(log_file_path)

    # Build the command
    cmd = ["npx", "@qwen-code/qwen-code@0.5.2"]

    # Add authentication settings if provided
    if auth_type:
        cmd.extend(["--auth-type", auth_type])

    if openai_api_key:
        cmd.extend(["--openai-api-key", openai_api_key])

    if openai_base_url:
        cmd.extend(["--openai-base-url", openai_base_url])

    # Add other flags based on parameters
    if model:
        cmd.extend(["--model", model])

    if debug:
        cmd.append("--debug")

    if output_format and output_format != "text":
        cmd.extend(["--output-format", output_format])

    if approval_mode and approval_mode != "default":
        cmd.extend(["--approval-mode", approval_mode])

    if all_files:
        cmd.append("--all-files")

    if show_memory_usage:
        cmd.append("--show-memory-usage")

    if yolo:
        cmd.append("--yolo")

    # Add the prompt as a positional argument
    cmd.append(prompt)

    # Add any additional arguments
    if additional_args:
        cmd.extend(additional_args)

    command_str = ' '.join(cmd)
    logging.info(f"Running command: {command_str}")

    try:
        # Prepare the subprocess with appropriate output handling
        if log_file_path:
            # If logging to file, capture output and write to both file and console
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=os.environ.copy(),
                shell=(os.name == 'nt'),  # Use shell on Windows
                cwd=working_dir,
                timeout=timeout,
            )

            # Log the output
            if result.stdout:
                logging.info(f"CLI Output:\n{result.stdout}")
            if result.stderr:
                logging.error(f"CLI Error Output:\n{result.stderr}")

            # Print to console as well
            if result.stdout:
                print(result.stdout, end='')
            if result.stderr:
                print(result.stderr, end='', file=sys.stderr)

            # Return the exit code
            return result.returncode
        else:
            # If not logging to file, run normally
            result = subprocess.run(
                cmd,
                check=True,
                stdout=sys.stdout,
                stderr=sys.stderr,
                env=os.environ.copy(),
                shell=(os.name == 'nt'), # Use shell on Windows
                cwd=working_dir,
                timeout=timeout,
            )
            return result.returncode
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running Qwen Code CLI: {e}")
        logging.error(f"Command: {command_str}")
        if hasattr(e, 'stdout') and e.stdout:
            logging.info(f"CLI Output:\n{e.stdout}")
        if hasattr(e, 'stderr') and e.stderr:
            logging.error(f"CLI Error Output:\n{e.stderr}")
        return e.returncode
    except FileNotFoundError:
        logging.error("Error: 'npx' command not found. Please ensure Node.js and npm are installed.")
        logging.info("You can also try running this script from a Node.js command prompt or ensuring Node.js is in your PATH.")
        return 1


def start_qwen_cli_shell_fallback(
    prompt: str,
    working_dir: str,
    model: Optional[str] = None,
    debug: bool = False,
    output_format: str = "text",
    approval_mode: str = "default",
    all_files: bool = False,
    show_memory_usage: bool = False,
    yolo: bool = False,
    auth_type: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
    additional_args: Optional[list] = None,
    log_file_path: Optional[str] = None,
    timeout: Optional[int] = None,
) -> int:
    """
    Alternative method to start the Qwen Code CLI using shell execution as fallback for Windows compatibility.

    Args:
        prompt: The user instruction to send to the CLI
        model: The model to use (optional)
        debug: Enable debug mode
        output_format: Output format (text, json, stream-json)
        approval_mode: Approval mode (plan, default, auto-edit, yolo)
        all_files: Include all files in context
        show_memory_usage: Show memory usage
        yolo: Enable YOLO mode (auto-approve all actions)
        auth_type: Authentication type (qwen-oauth or use-openai)
        openai_api_key: OpenAI API key (for OpenAI-compatible API)
        openai_base_url: OpenAI base URL (for custom endpoints)
        additional_args: Additional command line arguments to pass to the CLI
        log_file_path: Optional path to log file where output will be saved

    Returns:
        The exit code of the CLI process
    """
    # Set up logging
    setup_logging(log_file_path)

    # Build the command as a string for shell execution
    cmd_parts = ["npx", "@qwen-code/qwen-code@0.5.2"]

    # Add authentication settings if provided
    if auth_type:
        cmd_parts.extend(["--auth-type", auth_type])

    if openai_api_key:
        cmd_parts.extend(["--openai-api-key", openai_api_key])

    if openai_base_url:
        cmd_parts.extend(["--openai-base-url", openai_base_url])

    # Add other flags based on parameters
    if model:
        cmd_parts.extend(["--model", model])

    if debug:
        cmd_parts.append("--debug")

    if output_format and output_format != "text":
        cmd_parts.extend(["--output-format", output_format])

    if approval_mode and approval_mode != "default":
        cmd_parts.extend(["--approval-mode", approval_mode])

    if all_files:
        cmd_parts.append("--all-files")

    if show_memory_usage:
        cmd_parts.append("--show-memory-usage")

    if yolo:
        cmd_parts.append("--yolo")

    # Add the prompt as a positional argument
    cmd_parts.append(prompt)

    # Add any additional arguments
    if additional_args:
        cmd_parts.extend(additional_args)

    cmd_str = ' '.join(f'"{part}"' if ' ' in part else part for part in cmd_parts)

    logging.info(f"Running command (with shell fallback): {cmd_str}")

    try:
        # Prepare the subprocess with appropriate output handling
        if log_file_path:
            # If logging to file, capture output and write to both file and console
            result = subprocess.run(
                cmd_str,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True,
                cwd=working_dir,
                timeout=timeout,
            )

            # Log the output
            if result.stdout:
                logging.info(f"CLI Output:\n{result.stdout}")
            if result.stderr:
                logging.error(f"CLI Error Output:\n{result.stderr}")

            # Print to console as well
            if result.stdout:
                print(result.stdout, end='')
            if result.stderr:
                print(result.stderr, end='', file=sys.stderr)

            # Return the exit code
            return result.returncode
        else:
            # If not logging to file, run normally
            result = subprocess.run(
                cmd_str,
                check=True,
                stdout=sys.stdout,
                stderr=sys.stderr,
                shell=True,
                cwd=working_dir,
                timeout=timeout,
            )
            return result.returncode
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running Qwen Code CLI: {e}")
        logging.error(f"Command: {cmd_str}")
        if hasattr(e, 'stdout') and e.stdout:
            logging.info(f"CLI Output:\n{e.stdout}")
        if hasattr(e, 'stderr') and e.stderr:
            logging.error(f"CLI Error Output:\n{e.stderr}")
        return e.returncode
    except FileNotFoundError:
        logging.error("Error: 'npx' command not found. Please ensure Node.js and npm are installed.")
        logging.info("You can also try running this script from a Node.js command prompt or ensuring Node.js is in your PATH.")
        return 1




def execute_qwen_cli(
    prompt: str,
    working_dir: str,
    model: Optional[str] = None,
    debug: bool = False,
    output_format: str = "text",
    approval_mode: str = "default",
    all_files: bool = False,
    show_memory_usage: bool = False,
    yolo: bool = False,
    auth_type: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
    additional_args: Optional[list] = None,
    log_file_path: Optional[str] = None,
    timeout: Optional[int] = None,
) -> int:
    """
    Execute the Qwen Code CLI with the given parameters, including fallback logic.

    Args:
        prompt: The user instruction to send to the CLI
        model: The model to use (optional)
        debug: Enable debug mode
        output_format: Output format (text, json, stream-json)
        approval_mode: Approval mode (plan, default, auto-edit, yolo)
        all_files: Include all files in context
        show_memory_usage: Show memory usage
        yolo: Enable YOLO mode (auto-approve all actions)
        auth_type: Authentication type (qwen-oauth or use-openai)
        openai_api_key: OpenAI API key (for OpenAI-compatible API)
        openai_base_url: OpenAI base URL (for custom endpoints)
        additional_args: Additional command line arguments to pass to the CLI
        log_file_path: Optional path to log file where output will be saved

    Returns:
        The exit code of the CLI process
    """
    # Try primary method first
    exit_code = start_qwen_cli(
        prompt=prompt,
        working_dir=working_dir,
        model=model,
        debug=debug,
        output_format=output_format,
        approval_mode=approval_mode,
        all_files=all_files,
        show_memory_usage=show_memory_usage,
        yolo=yolo,
        auth_type=auth_type,
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url,
        additional_args=additional_args,
        log_file_path=log_file_path,
        timeout=timeout,
    )

    # If it fails on Windows, try the fallback method
    if exit_code != 0 and os.name == 'nt':
        print("Primary method failed, trying fallback method for Windows...")
        # Use the shell fallback for both auth and non-auth modes since they're the same function
        exit_code = start_qwen_cli_shell_fallback(
            prompt=prompt,
            working_dir=working_dir,
            model=model,
            debug=debug,
            output_format=output_format,
            approval_mode=approval_mode,
            all_files=all_files,
            show_memory_usage=show_memory_usage,
            yolo=yolo,
            auth_type=auth_type,
            openai_api_key=openai_api_key,
            openai_base_url=openai_base_url,
            additional_args=additional_args,
            log_file_path=log_file_path,
            timeout=timeout,
        )

    return exit_code


def main():
    parser = argparse.ArgumentParser(
        description="Automatically start the Qwen Code CLI with a user instruction"
    )

    parser.add_argument(
        "prompt",
        help="The user instruction to send to Qwen Code"
    )
    
    parser.add_argument(
        "--working-dir",
        help="The working dir"
    )

    parser.add_argument(
        "--model",
        help="Model to use for the request"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode"
    )

    parser.add_argument(
        "--output-format",
        choices=["text", "json", "stream-json"],
        default="text",
        help="Output format (default: text)"
    )

    parser.add_argument(
        "--approval-mode",
        choices=["plan", "default", "auto-edit", "yolo"],
        default="default",
        help="Approval mode (default: default)"
    )

    parser.add_argument(
        "--all-files",
        action="store_true",
        help="Include all files in context"
    )

    parser.add_argument(
        "--show-memory-usage",
        action="store_true",
        help="Show memory usage in status bar"
    )

    parser.add_argument(
        "--yolo",
        action="store_true",
        help="Enable YOLO mode (auto-approve all actions)"
    )

    parser.add_argument(
        "--auth-type",
        choices=["qwen-oauth", "use-openai"],
        help="Authentication type"
    )

    parser.add_argument(
        "--openai-api-key",
        help="OpenAI API key for authentication"
    )

    parser.add_argument(
        "--openai-base-url",
        help="OpenAI base URL for custom endpoints"
    )

    parser.add_argument(
        "--log-file",
        help="Path to log file where output will be saved"
    )

    parser.add_argument(
        "--additional-args",
        nargs="*",
        help="Additional arguments to pass to the CLI"
    )

    args = parser.parse_args()

    # Use the execute_qwen_cli function to handle the execution and fallback logic
    return execute_qwen_cli(
        prompt=args.prompt,
        working_dir=args.working_dir,
        model=args.model,
        debug=args.debug,
        output_format=args.output_format,
        approval_mode=args.approval_mode,
        all_files=args.all_files,
        show_memory_usage=args.show_memory_usage,
        yolo=args.yolo,
        auth_type=args.auth_type,
        openai_api_key=args.openai_api_key,
        openai_base_url=args.openai_base_url,
        additional_args=args.additional_args,
        log_file_path=args.log_file
    )


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)