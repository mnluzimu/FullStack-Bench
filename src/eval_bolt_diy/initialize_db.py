import os
import psycopg2

from pathlib import Path
from typing import Optional


def find_first_sql(directory: str | Path) -> Optional[Path]:
    """
    Recursively search *directory* for the first file whose name ends with
    '.sql' (case–insensitive).  
    Returns the `pathlib.Path` object of the file, or `None` if no match
    exists.

    Parameters
    ----------
    directory : str | pathlib.Path
        The root folder in which to start the search.

    Examples
    --------
    >>> find_first_sql("/tmp/project")
    PosixPath('/tmp/project/migrations/0001_init.sql')

    >>> find_first_sql("/does/not/contain/sql")
    None
    """
    root = Path(directory).expanduser().resolve()

    if not root.is_dir():
        raise ValueError(f"{root} is not a directory")

    # Depth-first, lexicographical order
    for path in root.rglob("*.sql"):
        if path.is_file():
            return path

    return None


def initialize_db(sql_file):
    """
    Connects to the PostgreSQL database and executes the SQL schema file.
    
    Args:
        sql_file (str): Path to the SQL file containing the database schema
    """
    # Get database configuration from environment variables
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', 5432),
        'user': os.getenv('DB_USERNAME', 'myappuser'),
        'password': os.getenv('DB_PASSWORD', 'myapppassword'),
        'database': os.getenv('DB_NAME', 'myapp')
    }
    
    # Connect to the database
    try:
        connection = psycopg2.connect(**db_config)
        cursor = connection.cursor()
        
        # Read the SQL file
        with open(sql_file, 'r', encoding='utf-8') as file:
            sql_commands = file.read()
        
        # Execute the SQL commands
        cursor.execute(sql_commands)
        
        # Commit the changes
        connection.commit()
        
        print("Database schema initialized successfully!")
        
    except psycopg2.Error as e:
        print(f"Error initializing database: {e}")
        
    finally:
        # Close the cursor and connection
        if cursor:
            cursor.close()
        if connection:
            connection.close()

if __name__ == "__main__":
    # Example usage
    # initialize_db(r"E:\Qwen-Code\workspaces\Qwen3-Coder-480B-A35B-Instruct-FP8_fullstack\000002\backend\schema.sql")
    print(find_first_sql(r"E:\Qwen-Code\workspaces\Qwen3-Coder-480B-A35B-Instruct-FP8_fullstack\000002\frontend"))