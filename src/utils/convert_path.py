import re

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

if __name__ == "__main__":
    # Example usage
    windows_path = r'D:\research\WebGen-Plus\WebGen-Agent2'
    linux_path = convert_windows_path_to_linux(windows_path)
    print(linux_path)  # Output: /d/research/WebGen-Plus/WebGen-Agent2

    # Test with non-Windows path
    unix_path = '/home/user/projects'
    print(convert_windows_path_to_linux(unix_path))  # Output: /home/user/projects