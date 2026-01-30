import os
import json
import sys
import shutil
from tqdm import tqdm
import zipfile

def unzip_files(zip_file_paths, output_root):
    """
    Given a list of .zip files and a desired output root directory,
    unzip each file into a subdirectory named after the .zip file.
    
    :param zip_file_paths: List of paths to .zip files (e.g. ["path/to/file1.zip", "path/to/file2.zip"]).
    :param output_root: Output root directory where extracted folders will be created.
    """
    # Ensure the output_root exists
    if not os.path.exists(output_root):
        os.makedirs(output_root)
    
    for zip_path in tqdm(zip_file_paths):

        try:
            # Get the base name of the zip file (e.g. "my_archive" from "my_archive.zip")
            base_name = os.path.splitext(os.path.basename(zip_path))[0]
            
            # Construct the output folder path
            output_dir = os.path.join(output_root, base_name)
            
            # Create the output directory if it doesn't exist
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Extract all contents of the zip file into the output directory
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(output_dir)
        except:
            print(f"Error extracting {zip_path} to {output_dir}")


if __name__ == "__main__":
    output_root = r"E:\TDDev-Fork\outputs\qwen3coder480B_extracted"
    input_dir = r"E:\TDDev-Fork\outputs\qwen3coder480B"
    
    zip_file_paths = [os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.endswith('.zip')]
    unzip_files(zip_file_paths, output_root)