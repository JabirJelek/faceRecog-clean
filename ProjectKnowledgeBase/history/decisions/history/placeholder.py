#!/usr/bin/env python3
"""
Simple script to display HTML content in the default browser.
Usage: python html_runner.py "HTML content" [title]
"""

import sys
import tempfile
import webbrowser
import os

def open_html_in_browser(html_content, title="HTML Viewer"):
    """Create a temporary HTML file and open it in the default browser."""
    
    # Wrap content in basic HTML structure with the provided title
    html_template = f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <meta charset="UTF-8">
</head>
<body>
    {html_content}
</body>
</html>"""
    
    # Create a temporary HTML file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write(html_template)
        temp_file = f.name
    
    # Open in default browser
    webbrowser.open(f'file://{temp_file}')
    
    # Note: The file will be deleted when the OS cleans temp files
    # You could add cleanup logic if needed
    print(f"Opening in browser... (temporary file: {temp_file})")

def main():
    # Check for minimum arguments
    if len(sys.argv) < 2:
        print("Usage: python html_runner.py \"HTML content\" [title]")
        print("Example: python html_runner.py \"<h1>Hello</h1>\" \"My Page\"")
        sys.exit(1)
    
    # Get HTML content from first argument
    html_content = sys.argv[1]
    
    # Get optional title from second argument
    title = sys.argv[2] if len(sys.argv) > 2 else "HTML Viewer"
    
    open_html_in_browser(html_content, title)

if __name__ == "__main__":
    main()