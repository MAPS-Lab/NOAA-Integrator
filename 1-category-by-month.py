import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor

# Define the base directory where the files are stored
base_dir = "/meridian/AIS_archive/marinecadastre2"

# Ensure the base directory exists
if not os.path.exists(base_dir):
    print(f"Error: Directory {base_dir} does not exist.")
    exit()

# Get all files in the directory
files = [f for f in os.listdir(base_dir) if f.endswith(".zip")]

# Regular expressions for different file formats
pattern_2025 = re.compile(r"(\d{4})_ais_(\d{4})-(\d{2})-\d{2}\.csv\.zst")  # 2025
pattern_2015_2024 = re.compile(r"(\d{4})_AIS_(\d{4})_(\d{2})_\d{2}\.zip")  # 2015-2024
pattern_2009_2014 = re.compile(r"(\d{4})_Zone\d+_(\d{4})_(\d{2})\.zip")  # 2009,2010,2014
pattern_2011_2013 = re.compile(r"(\d{4})_Zone\d+_(\d{4})_(\d{2})\.gdb\.zip")  # 2011-2013

# Function to process a file and move it to the corresponding folder
def process_file(file):
    match_2025 = pattern_2025.match(file)
    match_2015_2024 = pattern_2015_2024.match(file)
    match_2009_2014 = pattern_2009_2014.match(file)
    match_2011_2013 = pattern_2011_2013.match(file)

    if match_2025:
        year, month = match_2025.group(1), match_2025.group(3)
    elif match_2015_2024:
        year, month = match_2015_2024.group(2), match_2015_2024.group(3)
    elif match_2009_2014:
        year, month = match_2009_2014.group(2), match_2009_2014.group(3)
    elif match_2011_2013:
        year, month = match_2011_2013.group(2), match_2011_2013.group(3)
    else:
        return f"Skipped: {file} (No matching pattern)"

    # Create folder name in {year}{month} format (e.g., 202406)
    folder_name = os.path.join(base_dir, f"{year}{month}")

    # Create the folder if it does not exist
    os.makedirs(folder_name, exist_ok=True)

    # Move the file to the corresponding folder
    src_path = os.path.join(base_dir, file)
    dst_path = os.path.join(folder_name, file)

    shutil.move(src_path, dst_path)
    return f"Moved: {file} → {folder_name}/"

# Use ThreadPoolExecutor to process files in parallel
with ThreadPoolExecutor() as executor:
    results = list(executor.map(process_file, files))

# Print results
for result in results:
    print(result)

print("File organization completed!")
