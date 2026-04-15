"""
ProductOS — 4-Role Agentic Product Builder
Flask server with SSE streaming
"""

import os, json, sqlite3, uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, Response, request, send_from_directory, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

BASE    = Path(__file__).parent
DB_PATH = BASE / 'sessions.db'

app = Flask(__name__, static_folder=str(BASE))
CORS(app)

# In-memory config per session (cleared on restart — fine for a live tool)
_session_configs = {}

# ── Database ───────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                idea TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
        ''')

init_db()

# ── Key resolution ─────────────────────────────────────────────────────────────
def resolve_key(provider: str, user_key: str = '') -> str:
    """User key > env var. Ollama needs no key."""
    if provider == 'ollama':
        return 'ollama'
    if user_key:
        return user_key
    env_var = 'ANTHROPIC_API_KEY' if provider == 'anthropic' else 'OPENAI_API_KEY'
    return os.getenv(env_var, '')

# ── SSE helpers ────────────────────────────────────────────────────────────────
def sse(data: dict) -> str:
    return f'data: {json.dumps(data)}\n\n'

# ── Pipeline ───────────────────────────────────────────────────────────────────
def stream_pipeline(idea: str, session_id: str):
    from agents import Orchestrator

    config   = _session_configs.pop(session_id, {})
    provider = config.get('provider', 'anthropic')
    model    = config.get('model', 'claude-sonnet-4-6')
    api_key  = config.get('api_key', '')

    if not api_key:
        yield sse({'type': 'error', 'message': f'No API key for {provider}. Add one in ⚙ settings.'})
        return

    try:
        if provider == 'ollama':
            from openai import OpenAI
            client = OpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
        elif provider == 'openai':
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
        else:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        yield sse({'type': 'error', 'message': f'Failed to init client: {e}'})
        return

    orch = Orchestrator(client, provider=provider, model=model)

    with get_db() as db:
        db.execute('UPDATE sessions SET status=? WHERE id=?', ('running', session_id))

    yield sse({'type': 'session_start', 'session_id': session_id, 'idea': idea})

    try:
        for event in orch.run(idea):
            if event['type'] == 'agent_done':
                with get_db() as db:
                    db.execute(
                        'INSERT OR REPLACE INTO artifacts (id,session_id,role,content,created_at) VALUES (?,?,?,?,?)',
                        (str(uuid.uuid4()), session_id, event['role'], event['content'], datetime.now().isoformat())
                    )
            elif event['type'] == 'keepalive':
                # SSE comment — keeps the browser connection alive during inter-agent pauses
                yield ': keepalive\n\n'
                continue
            yield sse(event)
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        print(f'\n[ProductOS ERROR] Session {session_id}:\n{err}')
        with get_db() as db:
            db.execute('UPDATE sessions SET status=? WHERE id=?', ('error', session_id))
        yield sse({'type': 'error', 'message': str(e)})
        return

    with get_db() as db:
        db.execute('UPDATE sessions SET status=? WHERE id=?', ('complete', session_id))

    yield sse({'type': 'complete', 'session_id': session_id})

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory(str(BASE), 'index.html')

@app.route('/favicon.ico')
def favicon():
    # Return a minimal SVG favicon — stops the 404 noise in the console
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect x="0" y="0" width="7" height="7" fill="#FB923C"/><rect x="9" y="0" width="7" height="7" fill="#2DD4BF"/><rect x="0" y="9" width="7" height="7" fill="#A78BFA"/><rect x="9" y="9" width="7" height="7" fill="#4ADE80"/></svg>'
    from flask import Response
    return Response(svg, mimetype='image/svg+xml')

@app.route('/api/build', methods=['POST'])
def build():
    """Create a session and store config. Returns session_id for /api/stream."""
    data     = request.json or {}
    idea     = data.get('idea', '').strip()
    provider = data.get('provider', 'anthropic')
    model    = data.get('model', 'claude-sonnet-4-6')
    user_key = data.get('api_key', '').strip()

    if not idea:
        return {'error': 'idea is required'}, 400

    api_key = resolve_key(provider, user_key)
    if not api_key and provider != 'ollama':
        return {'error': f'No API key found for {provider}. Add one in ⚙ settings.'}, 400

    session_id = str(uuid.uuid4())[:8]
    with get_db() as db:
        db.execute(
            'INSERT INTO sessions (id,idea,status,created_at) VALUES (?,?,?,?)',
            (session_id, idea, 'pending', datetime.now().isoformat())
        )

    _session_configs[session_id] = {
        'api_key':  api_key,
        'model':    model,
        'provider': provider,
    }

    return {'session_id': session_id}

@app.route('/api/stream')
def stream():
    session_id = request.args.get('session', '').strip()
    if not session_id:
        return {'error': 'session param required'}, 400

    with get_db() as db:
        row = db.execute('SELECT idea FROM sessions WHERE id=?', (session_id,)).fetchone()
    if not row:
        return {'error': 'session not found'}, 404

    idea = row['idea']

    def generate():
        yield from stream_pipeline(idea, session_id)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no','Connection':'keep-alive'}
    )

@app.route('/api/sessions')
def list_sessions():
    with get_db() as db:
        rows = db.execute(
            'SELECT id,idea,status,created_at FROM sessions ORDER BY created_at DESC LIMIT 30'
        ).fetchall()
    return [dict(r) for r in rows]

@app.route('/api/session/<sid>')
def get_session(sid):
    with get_db() as db:
        s = db.execute('SELECT * FROM sessions WHERE id=?', (sid,)).fetchone()
        a = db.execute('SELECT * FROM artifacts WHERE session_id=? ORDER BY created_at', (sid,)).fetchall()
    if not s:
        return {'error': 'not found'}, 404
    return {'session': dict(s), 'artifacts': [dict(x) for x in a]}

if __name__ == '__main__':
    print('\n╔════════════════════════════════════════╗')
    print('║  ProductOS · 4-Role Agentic Builder    ║')
    print('║  http://localhost:5002                 ║')
    print('╚════════════════════════════════════════╝\n')
    app.run(port=5002, debug=False, threaded=True)
