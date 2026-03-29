"""Training examples that teach the model when and how to use tools via <tool_call> blocks."""

from __future__ import annotations

TOOL_USE_EXAMPLES: list[dict] = [
    # ── write_file: various languages and scenarios ──────────────────────────
    {
        "instruction": "Create a Python file called hello.py that prints hello world",
        "response": 'I\'ll create that file for you.\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "hello.py", "content": "print(\'Hello, World!\')"}}\n</tool_call>',
    },
    {
        "instruction": "Can you write a binary search implementation in C++ and save it as binary_search.cpp?",
        "response": 'Sure! I\'ll create the file now.\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "binary_search.cpp", "content": "#include <iostream>\\n#include <vector>\\n\\nint binarySearch(const std::vector<int>& arr, int target) {\\n    int left = 0;\\n    int right = arr.size() - 1;\\n    while (left <= right) {\\n        int mid = left + (right - left) / 2;\\n        if (arr[mid] == target) return mid;\\n        else if (arr[mid] < target) left = mid + 1;\\n        else right = mid - 1;\\n    }\\n    return -1;\\n}\\n\\nint main() {\\n    std::vector<int> arr = {1, 3, 5, 7, 9, 11};\\n    int idx = binarySearch(arr, 7);\\n    std::cout << \\"Found at index: \\" << idx << std::endl;\\n    return 0;\\n}"}}\n</tool_call>',
    },
    {
        "instruction": "Create that file in the workspace",
        "response": 'I\'ll write it to the workspace now.\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "solution.py", "content": "def solve():\\n    pass"}}\n</tool_call>',
    },
    {
        "instruction": "Save that code to a file called utils.js",
        "response": 'Done, I\'ve saved it.\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "utils.js", "content": "export function formatDate(d) {\\n  return d.toISOString().split(\'T\')[0];\\n}"}}\n</tool_call>',
    },
    {
        "instruction": "Create a TypeScript config file",
        "response": 'I\'ll create a tsconfig.json for you.\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "tsconfig.json", "content": "{\\n  \\"compilerOptions\\": {\\n    \\"target\\": \\"ES2020\\",\\n    \\"module\\": \\"commonjs\\",\\n    \\"strict\\": true,\\n    \\"outDir\\": \\"./dist\\"\\n  }\\n}"}}\n</tool_call>',
    },
    {
        "instruction": "Write a Dockerfile for a Node.js app",
        "response": 'Here\'s a Dockerfile for Node.js.\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "Dockerfile", "content": "FROM node:18-alpine\\nWORKDIR /app\\nCOPY package*.json ./\\nRUN npm ci --production\\nCOPY . .\\nEXPOSE 3000\\nCMD [\\"node\\", \\"index.js\\"]"}}\n</tool_call>',
    },
    {
        "instruction": "Make a CSS file with a dark theme",
        "response": 'I\'ll create a dark theme stylesheet.\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "dark-theme.css", "content": ":root {\\n  --bg: #1a1a2e;\\n  --text: #e0e0e0;\\n  --accent: #0f3460;\\n}\\nbody {\\n  background: var(--bg);\\n  color: var(--text);\\n  font-family: sans-serif;\\n}"}}\n</tool_call>',
    },
    {
        "instruction": "Create a README.md for this project",
        "response": 'I\'ll set up a README.\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "README.md", "content": "# Project\\n\\nA brief description of the project.\\n\\n## Getting Started\\n\\n```bash\\nnpm install\\nnpm start\\n```\\n"}}\n</tool_call>',
    },
    # ── read_file ────────────────────────────────────────────────────────────
    {
        "instruction": "Read the contents of main.py",
        "response": 'Let me read that file.\n\n<tool_call>\n{"name": "read_file", "arguments": {"path": "main.py"}}\n</tool_call>',
    },
    {
        "instruction": "Show me what's in the config file",
        "response": 'I\'ll read it for you.\n\n<tool_call>\n{"name": "read_file", "arguments": {"path": "config.json"}}\n</tool_call>',
    },
    # ── list_files ───────────────────────────────────────────────────────────
    {
        "instruction": "What files are in the project?",
        "response": 'Let me check the workspace.\n\n<tool_call>\n{"name": "list_files", "arguments": {"path": "."}}\n</tool_call>',
    },
    {
        "instruction": "List the files in the src directory",
        "response": 'I\'ll list that directory.\n\n<tool_call>\n{"name": "list_files", "arguments": {"path": "src"}}\n</tool_call>',
    },
    # ── edit_file ────────────────────────────────────────────────────────────
    {
        "instruction": "Replace the print statement in hello.py with a logging call",
        "response": 'I\'ll update that for you.\n\n<tool_call>\n{"name": "edit_file", "arguments": {"path": "hello.py", "old_string": "print(\'Hello, World!\')", "new_string": "import logging\\nlogging.basicConfig(level=logging.INFO)\\nlogging.info(\'Hello, World!\')"}}\n</tool_call>',
    },
    {
        "instruction": "Change the port from 3000 to 8080 in server.js",
        "response": 'I\'ll update the port.\n\n<tool_call>\n{"name": "edit_file", "arguments": {"path": "server.js", "old_string": "3000", "new_string": "8080"}}\n</tool_call>',
    },
    # ── create_folder ────────────────────────────────────────────────────────
    {
        "instruction": "Create a src directory with an __init__.py inside it",
        "response": 'I\'ll set up that package structure.\n\n<tool_call>\n{"name": "create_folder", "arguments": {"path": "src"}}\n</tool_call>\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "src/__init__.py", "content": ""}}\n</tool_call>',
    },
    {
        "instruction": "Set up a components folder inside src",
        "response": 'Creating the directory now.\n\n<tool_call>\n{"name": "create_folder", "arguments": {"path": "src/components"}}\n</tool_call>',
    },
    # ── run_command ──────────────────────────────────────────────────────────
    {
        "instruction": "Run the tests",
        "response": 'I\'ll run the test suite now.\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "python -m pytest"}}\n</tool_call>',
    },
    {
        "instruction": "Install flask and create a basic web server",
        "response": 'I\'ll install Flask and set up a basic server.\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "pip install flask"}}\n</tool_call>\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "app.py", "content": "from flask import Flask\\n\\napp = Flask(__name__)\\n\\n@app.route(\'/\')\\ndef index():\\n    return \'Hello, World!\'\\n\\nif __name__ == \'__main__\':\\n    app.run(debug=True)"}}\n</tool_call>',
    },
    {
        "instruction": "Compile and run the C++ file",
        "response": 'I\'ll compile and run it.\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "g++ -o main main.cpp && ./main"}}\n</tool_call>',
    },
    {
        "instruction": "Check the Node.js version",
        "response": 'Let me check.\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "node --version"}}\n</tool_call>',
    },
    # ── Multi-step: project setup, install, and run ───────────────────────────
    {
        "instruction": "Set up a new React project from scratch and run it",
        "response": 'I\'ll scaffold a React app, install dependencies, and start the dev server.\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "package.json", "content": "{\\n  \\"name\\": \\"my-app\\",\\n  \\"private\\": true,\\n  \\"version\\": \\"1.0.0\\",\\n  \\"scripts\\": {\\n    \\"dev\\": \\"vite\\",\\n    \\"build\\": \\"vite build\\"\\n  },\\n  \\"dependencies\\": {\\n    \\"react\\": \\"^18.2.0\\",\\n    \\"react-dom\\": \\"^18.2.0\\"\\n  },\\n  \\"devDependencies\\": {\\n    \\"@vitejs/plugin-react\\": \\"^4.0.0\\",\\n    \\"vite\\": \\"^5.0.0\\"\\n  }\\n}"}}\n</tool_call>\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "vite.config.js", "content": "import { defineConfig } from \'vite\';\\nimport react from \'@vitejs/plugin-react\';\\n\\nexport default defineConfig({\\n  plugins: [react()],\\n});"}}\n</tool_call>\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "index.html", "content": "<!DOCTYPE html>\\n<html lang=\\"en\\">\\n<head><meta charset=\\"UTF-8\\"><title>My App</title></head>\\n<body>\\n  <div id=\\"root\\"></div>\\n  <script type=\\"module\\" src=\\"/src/main.jsx\\"></script>\\n</body>\\n</html>"}}\n</tool_call>\n\n<tool_call>\n{"name": "create_folder", "arguments": {"path": "src"}}\n</tool_call>\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "src/main.jsx", "content": "import React from \'react\';\\nimport ReactDOM from \'react-dom/client\';\\nimport App from \'./App\';\\n\\nReactDOM.createRoot(document.getElementById(\'root\')).render(<App />);"}}\n</tool_call>\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "src/App.jsx", "content": "export default function App() {\\n  return <h1>Hello, World!</h1>;\\n}"}}\n</tool_call>\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "npm install"}}\n</tool_call>\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "npm run dev"}}\n</tool_call>',
    },
    {
        "instruction": "Create a Python Flask API with a /health endpoint, install deps, and start it",
        "response": 'I\'ll set up the project, install Flask, and start the server.\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "requirements.txt", "content": "flask>=3.0\\ngunicorn>=21.2"}}\n</tool_call>\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "app.py", "content": "from flask import Flask, jsonify\\n\\napp = Flask(__name__)\\n\\n@app.route(\'/health\')\\ndef health():\\n    return jsonify(status=\'ok\')\\n\\nif __name__ == \'__main__\':\\n    app.run(host=\'0.0.0.0\', port=5000)"}}\n</tool_call>\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "pip install -r requirements.txt"}}\n</tool_call>\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "python app.py"}}\n</tool_call>',
    },
    {
        "instruction": "Initialize a Node.js Express project with a homepage route and run it on port 3000",
        "response": 'I\'ll create the project files, install Express, and start the server.\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "package.json", "content": "{\\n  \\"name\\": \\"express-app\\",\\n  \\"version\\": \\"1.0.0\\",\\n  \\"scripts\\": {\\n    \\"start\\": \\"node index.js\\"\\n  }\\n}"}}\n</tool_call>\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "index.js", "content": "const express = require(\'express\');\\nconst app = express();\\n\\napp.get(\'/\', (req, res) => {\\n  res.send(\'Hello from Express!\');\\n});\\n\\napp.listen(3000, () => {\\n  console.log(\'Server running at http://localhost:3000\');\\n});"}}\n</tool_call>\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "npm install express"}}\n</tool_call>\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "npm start"}}\n</tool_call>',
    },
    {
        "instruction": "Set up a static HTML/CSS/JS site with a live server",
        "response": 'I\'ll create the site files and serve them with a live server.\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "index.html", "content": "<!DOCTYPE html>\\n<html lang=\\"en\\">\\n<head>\\n  <meta charset=\\"UTF-8\\">\\n  <meta name=\\"viewport\\" content=\\"width=device-width, initial-scale=1.0\\">\\n  <title>My Site</title>\\n  <link rel=\\"stylesheet\\" href=\\"style.css\\">\\n</head>\\n<body>\\n  <h1>Welcome</h1>\\n  <p id=\\"msg\\"></p>\\n  <script src=\\"app.js\\"></script>\\n</body>\\n</html>"}}\n</tool_call>\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "style.css", "content": "body {\\n  font-family: system-ui, sans-serif;\\n  max-width: 600px;\\n  margin: 2rem auto;\\n  background: #111;\\n  color: #eee;\\n}"}}\n</tool_call>\n\n<tool_call>\n{"name": "write_file", "arguments": {"path": "app.js", "content": "document.getElementById(\'msg\').textContent = \'Site is live!\';"}}\n</tool_call>\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "npx serve ."}}\n</tool_call>',
    },
    {
        "instruction": "Create a Django project with one app and run the dev server",
        "response": 'I\'ll install Django, scaffold the project, and start the server.\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "pip install django"}}\n</tool_call>\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "django-admin startproject mysite ."}}\n</tool_call>\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "python manage.py startapp core"}}\n</tool_call>\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "python manage.py migrate"}}\n</tool_call>\n\n<tool_call>\n{"name": "run_command", "arguments": {"command": "python manage.py runserver 0.0.0.0:8000"}}\n</tool_call>',
    },
    # ── No-tool: pure knowledge questions ────────────────────────────────────
    {
        "instruction": "What is a REST API?",
        "response": "A REST API (Representational State Transfer Application Programming Interface) is an architectural style for building web services. It uses standard HTTP methods like GET, POST, PUT, and DELETE to perform operations on resources identified by URLs. REST APIs are stateless, meaning each request contains all the information needed to process it.",
    },
    {
        "instruction": "Explain how binary search works",
        "response": "Binary search is an efficient algorithm for finding a value in a sorted array. It works by repeatedly dividing the search space in half. You compare the target to the middle element — if equal, you're done; if the target is smaller, search the left half; if larger, search the right half. This gives O(log n) time complexity, much faster than linear search.",
    },
    {
        "instruction": "What's the difference between a stack and a queue?",
        "response": "A stack is a LIFO (Last In, First Out) data structure — the last element added is the first removed, like a stack of plates. A queue is FIFO (First In, First Out) — the first element added is the first removed, like a line at a store. Stacks use push/pop operations, while queues use enqueue/dequeue.",
    },
    {
        "instruction": "How does CSS flexbox work?",
        "response": "CSS Flexbox is a one-dimensional layout model. You set `display: flex` on a container, and its children become flex items. Key properties: `flex-direction` controls the main axis (row or column), `justify-content` aligns items along the main axis, and `align-items` aligns them along the cross axis. Items can grow or shrink with the `flex` property.",
    },
]
