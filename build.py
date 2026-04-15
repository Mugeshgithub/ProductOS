#!/usr/bin/env python3
"""
ProductOS — 4-Role Agentic Product Builder
Runs PM → System Architect → Software Architect → Programmer in sequence.
Each agent reads all previous artifacts and can push back.

Usage:
  python3 build.py "your product idea"
  python3 build.py "your idea" --only pm          # run just PM
  python3 build.py "your idea" --only architect   # run just system architect
  python3 build.py "your idea" --from launch_engineer  # resume from launch engineer
  python3 build.py --session my_session           # resume existing session
"""

import os, sys, json, argparse
from datetime import datetime
from pathlib import Path
import anthropic

BASE     = Path(__file__).parent
PROMPTS  = BASE / 'prompts'
SESSIONS = BASE / 'sessions'
ARTIFACTS= BASE / 'artifacts'

ROLES = ['pm', 'system_architect', 'software_architect', 'launch_engineer']

ROLE_LABELS = {
    'pm':                 '📋 Product Manager',
    'system_architect':   '🏗️  System Architect',
    'software_architect': '🔧 Software Architect',
    'launch_engineer':    '🚀 Launch Engineer',
}

ARTIFACT_NAMES = {
    'pm':                 'PRD — Product Requirements Document',
    'system_architect':   'HLD — High Level Design',
    'software_architect': 'LLD — Low Level Design',
    'launch_engineer':    'Plan — Build & Launch Plan',
}

def load_prompt(role: str) -> str:
    path = PROMPTS / f'{role}.md'
    return path.read_text() if path.exists() else ''

def load_artifact(session_dir: Path, role: str) -> str:
    path = session_dir / f'{role}.md'
    return path.read_text() if path.exists() else ''

def save_artifact(session_dir: Path, role: str, content: str):
    path = session_dir / f'{role}.md'
    path.write_text(content)
    print(f'  ✓ Saved → sessions/{session_dir.name}/{role}.md')

def build_context(session_dir: Path, current_role: str, idea: str) -> str:
    """Build the full context for a role — includes idea + all previous artifacts."""
    ctx = f'## Original Product Idea\n{idea}\n\n'

    prev_roles = ROLES[:ROLES.index(current_role)]
    for role in prev_roles:
        artifact = load_artifact(session_dir, role)
        if artifact:
            ctx += f'## {ARTIFACT_NAMES[role]}\n{artifact}\n\n'

    return ctx

def run_role(client: anthropic.Anthropic, session_dir: Path, role: str, idea: str, model: str = 'claude-sonnet-4-6') -> str:
    """Run a single agent role and return its output."""
    system_prompt = load_prompt(role)
    context       = build_context(session_dir, role, idea)

    label = ROLE_LABELS[role]
    print(f'\n{"─"*60}')
    print(f'{label}')
    print(f'{"─"*60}')
    print(f'  Thinking...\n')

    user_message = context + f'\nNow produce your {ARTIFACT_NAMES[role]}. Be sharp, specific, and push back if needed.'

    result = ''
    with client.messages.stream(
        model=model,
        max_tokens=3000,
        system=system_prompt,
        messages=[{'role': 'user', 'content': user_message}]
    ) as stream:
        for text in stream.text_stream:
            print(text, end='', flush=True)
            result += text

    print('\n')
    return result

def create_session(idea: str) -> Path:
    """Create a new session directory."""
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    slug = idea[:30].lower().replace(' ', '_').replace('/', '-')
    slug = ''.join(c for c in slug if c.isalnum() or c == '_')
    session_dir = SESSIONS / f'{ts}_{slug}'
    session_dir.mkdir(parents=True, exist_ok=True)

    # Save idea
    (session_dir / 'idea.txt').write_text(idea)

    # Save metadata
    meta = {
        'idea': idea,
        'created': datetime.now().isoformat(),
        'roles_completed': [],
    }
    (session_dir / 'meta.json').write_text(json.dumps(meta, indent=2))

    return session_dir

def load_session(name: str) -> tuple[Path, str]:
    """Load an existing session."""
    session_dir = SESSIONS / name
    if not session_dir.exists():
        # Try partial match
        matches = list(SESSIONS.glob(f'*{name}*'))
        if not matches:
            print(f'Session not found: {name}')
            sys.exit(1)
        session_dir = matches[-1]

    idea = (session_dir / 'idea.txt').read_text().strip()
    return session_dir, idea

def print_summary(session_dir: Path, idea: str, roles_run: list):
    print(f'\n{"═"*60}')
    print(f'  ProductOS — Session Complete')
    print(f'{"═"*60}')
    print(f'  Idea    : {idea[:60]}')
    print(f'  Session : {session_dir.name}')
    print(f'\n  Artifacts produced:')
    for role in roles_run:
        artifact_path = session_dir / f'{role}.md'
        if artifact_path.exists():
            size = artifact_path.stat().st_size
            print(f'    {ROLE_LABELS[role]:<30} → {role}.md ({size} bytes)')
    print(f'\n  View all: ls {session_dir}')
    print(f'{"═"*60}\n')

def main():
    parser = argparse.ArgumentParser(description='ProductOS — 4-Role Agentic Builder')
    parser.add_argument('idea',            nargs='?', help='Product idea to build')
    parser.add_argument('--session', '-s', help='Resume existing session by name')
    parser.add_argument('--only',          help='Run only one role: pm|system_architect|software_architect|launch_engineer')
    parser.add_argument('--from',  dest='from_role', help='Resume from a specific role')
    parser.add_argument('--model', default='claude-sonnet-4-6', help='Claude model to use')
    args = parser.parse_args()

    # API key
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        # Try reading from Deep Intelligence .env
        env_path = BASE.parent / 'Deep Intelligence' / '.env'
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith('ANTHROPIC_API_KEY='):
                    api_key = line.split('=', 1)[1].strip()
                    break
    if not api_key:
        print('Error: Set ANTHROPIC_API_KEY environment variable.')
        print('  export ANTHROPIC_API_KEY=sk-ant-...')
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Session setup
    if args.session:
        session_dir, idea = load_session(args.session)
        print(f'\n  Resuming session: {session_dir.name}')
        print(f'  Idea: {idea[:60]}')
    elif args.idea:
        idea = args.idea
        session_dir = create_session(idea)
        print(f'\n  New session: {session_dir.name}')
    else:
        print('Usage: python3 build.py "your product idea"')
        sys.exit(1)

    # Determine which roles to run
    if args.only:
        roles_to_run = [args.only] if args.only in ROLES else []
    elif args.from_role:
        start = ROLES.index(args.from_role) if args.from_role in ROLES else 0
        roles_to_run = ROLES[start:]
    else:
        # Skip roles already completed in this session
        meta_path = session_dir / 'meta.json'
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        completed = meta.get('roles_completed', [])
        roles_to_run = [r for r in ROLES if r not in completed]

    if not roles_to_run:
        print('All roles already completed for this session.')
        print(f'Use --from pm to re-run from the beginning.')
        sys.exit(0)

    print(f'\n  Running: {" → ".join(ROLE_LABELS[r] for r in roles_to_run)}\n')

    # Run each role
    roles_run = []
    for role in roles_to_run:
        try:
            output = run_role(client, session_dir, role, idea, model=args.model)
            save_artifact(session_dir, role, output)
            roles_run.append(role)

            # Update meta
            meta_path = session_dir / 'meta.json'
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            completed = meta.get('roles_completed', [])
            if role not in completed:
                completed.append(role)
            meta['roles_completed'] = completed
            meta_path.write_text(json.dumps(meta, indent=2))

        except KeyboardInterrupt:
            print(f'\n\n  Interrupted after {ROLE_LABELS[role]}')
            print(f'  Resume with: python3 build.py --session {session_dir.name} --from {role}')
            break
        except Exception as e:
            print(f'\n  Error in {role}: {e}')
            break

    print_summary(session_dir, idea, roles_run)

if __name__ == '__main__':
    main()
