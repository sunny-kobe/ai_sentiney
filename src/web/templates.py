DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Sentinel Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background-color: #f5f5f7; color: #1d1d1f; }}
        .card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        h1, h2 {{ color: #1d1d1f; }}
        .btn {{ display: inline-block; background: #0071e3; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; border: none; cursor: pointer; font-size: 14px; }}
        .btn:hover {{ background: #0077ed; }}
        .btn:disabled {{ background: #ccc; cursor: not-allowed; }}
        .status-box {{ padding: 15px; background: #f0f0f0; border-radius: 8px; font-family: monospace; white-space: pre-wrap; margin-top: 10px; max-height: 300px; overflow-y: auto; }}
        textarea {{ width: 100%; height: 200px; padding: 10px; border-radius: 6px; border: 1px solid #ccc; font-family: monospace; }}
        .tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-right: 5px; }}
        .tag-green {{ background: #e8f5e9; color: #2e7d32; }}
        .tag-red {{ background: #ffebee; color: #c62828; }}
    </style>
</head>
<body>
    <h1>📈 AI Sentinel Dashboard</h1>
    
    <div class="card">
        <h2>🛠️ Actions</h2>
        <button id="analyzeBtn" class="btn" onclick="triggerAnalysis()">🚀 Run Analysis</button>
        <div id="status" class="status-box">Ready</div>
    </div>

    <div class="card">
        <h2>📝 Configuration (Start Code List)</h2>
        <p>Edit your portfolio codes below (comma separated):</p>
        <textarea id="configArea">{stock_list}</textarea>
        <br><br>
        <button class="btn" onclick="saveConfig()">Save Config</button>
    </div>

    <script>
        async function triggerAnalysis() {{
            const btn = document.getElementById('analyzeBtn');
            const status = document.getElementById('status');
            btn.disabled = true;
            status.innerText = "Running analysis...";
            
            try {{
                const response = await fetch('/api/analyze', {{ 
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ dry_run: true }}) 
                 }});
                const data = await response.json();
                status.innerText = JSON.stringify(data, null, 2);
            }} catch (e) {{
                status.innerText = "Error: " + e;
            }} finally {{
                btn.disabled = false;
            }}
        }}

        async function saveConfig() {{
            const content = document.getElementById('configArea').value;
            try {{
                const response = await fetch('/api/config', {{ 
                    method: 'POST',
                    body: JSON.stringify({{ stock_list: content }})
                }});
                alert('Config saved!');
            }} catch (e) {{
                alert('Failed to save: ' + e);
            }}
        }}
    </script>
</body>
</html>
"""
