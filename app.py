import json
import glob
import os
import re
from flask import Flask, jsonify, render_template

app = Flask(__name__)

MODEL_DATE_RE = re.compile(r'-\d{8}$')


def normalize_model(model_name: str) -> str:
    """Strip trailing date suffix like -20251101 from model names."""
    if model_name:
        return MODEL_DATE_RE.sub('', model_name)
    return model_name or 'unknown'


def load_sessions():
    project_dir = os.path.expanduser('~/.claude/projects')
    files = glob.glob(f'{project_dir}/**/*.jsonl', recursive=True)

    sessions = []
    for f in files:
        sess = {
            'model': None,
            'date': None,
            'input': 0,
            'output': 0,
            'cache_create': 0,
            'cache_read': 0,
        }
        try:
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if 'timestamp' in obj and not sess['date']:
                        sess['date'] = obj['timestamp'][:10]
                    msg = obj.get('message', {})
                    if isinstance(msg, dict):
                        if 'model' in msg and msg['model'] and not sess['model']:
                            sess['model'] = normalize_model(msg['model'])
                        usage = msg.get('usage', {})
                        if usage and isinstance(usage, dict):
                            sess['input'] += usage.get('input_tokens', 0) or 0
                            sess['output'] += usage.get('output_tokens', 0) or 0
                            sess['cache_create'] += usage.get('cache_creation_input_tokens', 0) or 0
                            sess['cache_read'] += usage.get('cache_read_input_tokens', 0) or 0
        except Exception:
            continue

        if sess['input'] or sess['output']:
            if not sess['model']:
                sess['model'] = 'unknown'
            if not sess['date']:
                sess['date'] = 'unknown'
            sessions.append(sess)

    # Sort by date descending
    sessions.sort(key=lambda s: s['date'], reverse=True)
    return sessions


@app.route('/api/usage')
def api_usage():
    sessions = load_sessions()
    return jsonify(sessions)


@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(port=5050, debug=False)
