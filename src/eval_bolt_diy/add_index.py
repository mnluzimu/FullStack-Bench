import os


def add_index(workspace_dir):
    index_file_content = """<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <link rel="icon" type="image/svg+xml" href="/vite.svg" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Bolt.diy Generated Website</title>
    </head>
    <body>
        <div id="root"></div>
        <script type="module" src="/src/main.jsx"></script>
    </body>
    </html>"""

    index_file = os.path.join(workspace_dir, "frontend", "index.html")
    if os.path.exists(os.path.join(workspace_dir, "frontend")):
        if not os.path.exists(index_file):
            with open(index_file, "w", encoding="utf-8") as f:
                f.write(index_file_content)
            print(f"Created index.html in {workspace_dir}/frontend")
        else:
            with open(index_file, "r", encoding="utf-8") as f:
                content = f.read()
            if content.strip() == "":
                with open(index_file, "w", encoding="utf-8") as f:
                    f.write(index_file_content)
                print(f"Filled index.html in {workspace_dir}/frontend")