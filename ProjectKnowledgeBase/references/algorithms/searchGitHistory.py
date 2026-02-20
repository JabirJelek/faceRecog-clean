

# ==============================================
# REFERENCED
# REASON: This file is utilized to check local history of git, we can utilzied the knowledge for our documentation purposes.
# LEARNINGS: It captures git history in local storage while still consisting of description.
# REFERENCE: To create documentation purposes
# ==============================================

# This program will run a subprocess module from python

import subprocess
from datetime import datetime

# Hardcoded start and end dates
start_date = "2026-01-01"
end_date = "2026-01-31"

def get_py_files_in_date_range():
    print(f"Searching for .py files in git history from {start_date} to {end_date}...")
    
    # Command to get all .py files changed in the date range
    command = [
        'git', 'log',
        f'--since={start_date}',
        f'--until={end_date}',
        '--pretty=format:',
        '--name-only',
        '--all',  # Search all branches
        '--', '*.py'
    ]

    try:
        # Execute the git command
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        
        # Process the output
        all_files = result.stdout.strip().split('\n')
        
        # Remove empty strings and filter only .py files
        py_files = [f for f in all_files if f and f.endswith('.py')]
        
        # Remove duplicates while preserving order
        unique_files = []
        for file in py_files:
            if file not in unique_files:
                unique_files.append(file)
        
        # Sort alphabetically
        unique_files.sort()
        
        # Display results
        print(f"\nFound {len(unique_files)} unique .py files changed between {start_date} and {end_date}:\n")
        
        for i, file in enumerate(unique_files, 1):
            print(f"{i:3d}. {file}")
            
        return unique_files
        
    except subprocess.CalledProcessError as e:
        print(f"Git command error: {e.stderr}")
        return []
    except FileNotFoundError:
        print("Error: Git is not installed or not found in PATH")
        return []
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return []

def get_detailed_py_changes():
    print(f"\nDetailed commit history for .py files from {start_date} to {end_date}:")
    print("=" * 60)
    
    command = [
        'git', 'log',
        f'--since={start_date}',
        f'--until={end_date}',
        '--pretty=format:%C(yellow)%h%Creset - %C(blue)%an%Creset - %C(green)%ad%Creset - %s',
        '--name-only',
        '--all',
        '--', '*.py'
    ]
    
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        detailed_output = result.stdout
        print(detailed_output)
        return detailed_output
    except subprocess.CalledProcessError as e:
        error_msg = f"Error getting detailed history: {e.stderr}"
        print(error_msg)
        return error_msg

if __name__ == "__main__":
    # Get the list of changed .py files
    changed_files = get_py_files_in_date_range()
    
    # Get detailed commit history
    detailed_changes = get_detailed_py_changes()
    
    # Save to file option
    if changed_files or detailed_changes:
        save_option = input("\nDo you want to save this list to a file? (y/n): ")
        if save_option.lower() == 'y':
            filename = f"py_changes_{start_date}_to_{end_date}.txt"
            try:
                with open(filename, 'w') as f:
                    # Write file list section
                    f.write(f"Python files changed from {start_date} to {end_date}\n")
                    f.write("=" * 50 + "\n\n")
                    
                    if changed_files:
                        f.write(f"Found {len(changed_files)} unique .py files:\n\n")
                        for i, file in enumerate(changed_files, 1):
                            f.write(f"{i:3d}. {file}\n")
                    else:
                        f.write("No .py files found in the specified date range.\n")
                    
                    # Write detailed changes section
                    f.write("\n" + "=" * 50 + "\n")
                    f.write("DETAILED COMMIT HISTORY\n")
                    f.write("=" * 50 + "\n\n")
                    f.write(detailed_changes)
                    
                print(f"\nList saved to {filename}")
                print(f"File includes {len(changed_files)} files and detailed commit history.")
                
            except Exception as e:
                print(f"Error saving file: {e}")