"""
ProductOS — Agent and Orchestrator classes
Supports Anthropic (Claude) and OpenAI providers.
"""

from pathlib import Path
from typing import Iterator

BASE    = Path(__file__).parent
PROMPTS = BASE / 'prompts'

ROLES = ['pm', 'system_architect', 'software_architect', 'launch_engineer']

ROLE_META = {
    'pm': {
        'label':       'Product Manager',
        'artifact':    'PRD',
        'color':       '#FB923C',
        'num':         '01',
        'prompt_file': 'pm_agent.md',
        'max_tokens':  1500,
        # Needs only the raw idea — PRD is the starting artifact
        'context_from': [],
    },
    'system_architect': {
        'label':       'System Architect',
        'artifact':    'HLD',
        'color':       '#2DD4BF',
        'num':         '02',
        'prompt_file': 'system_architect.md',
        'max_tokens':  2500,
        # Needs PRD to design around scope and constraints
        'context_from': ['pm'],
    },
    'software_architect': {
        'label':       'Software Architect',
        'artifact':    'LLD',
        'color':       '#A78BFA',
        'num':         '03',
        'prompt_file': 'software_architect.md',
        'max_tokens':  3500,
        # Needs PRD (scope) + HLD (architecture to implement)
        'context_from': ['pm', 'system_architect'],
    },
    'launch_engineer': {
        'label':       'Launch Engineer',
        'artifact':    'Plan',
        'color':       '#4ADE80',
        'num':         '04',
        'prompt_file': 'launch_engineer.md',
        'max_tokens':  3500,
        # Needs PRD (scope) + LLD (what to build) — HLD decisions are already
        # captured in LLD's pushback and tech stack sections, no need to re-read it
        'context_from': ['pm', 'software_architect'],
    },
}


class Agent:
    def __init__(self, role: str, client, provider: str = 'anthropic', model: str = 'claude-sonnet-4-6'):
        self.role     = role
        self.meta     = ROLE_META[role]
        self.client   = client
        self.provider = provider
        self.model    = model
        prompt_path   = PROMPTS / self.meta['prompt_file']
        self.system   = prompt_path.read_text() if prompt_path.exists() else f'You are a world-class {self.meta["label"]}.'

    def stream(self, context: str) -> Iterator[dict]:
        user_msg = context + f'\n\nNow produce your {self.meta["artifact"]}. Be sharp, specific, and push back if needed.'
        full = ''

        if self.provider in ('openai', 'ollama'):
            yield from self._stream_openai(user_msg)
        else:
            yield from self._stream_anthropic(user_msg)

    def _stream_anthropic(self, user_msg: str) -> Iterator[dict]:
        full = ''
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=self.meta['max_tokens'],
                system=self.system,
                messages=[{'role': 'user', 'content': user_msg}]
            ) as s:
                for text in s.text_stream:
                    full += text
                    yield {'type': 'token', 'role': self.role, 'text': text}
        except Exception as e:
            print(f'[Agent:{self.role}] Anthropic error: {e}')
            raise
        yield {'type': 'agent_done', 'role': self.role, 'content': full}

    def _is_reasoning_model(self) -> bool:
        """o1, o3, o4-mini etc. use max_completion_tokens and developer role."""
        import re
        return bool(re.match(r'^o\d', self.model))

    def _stream_openai(self, user_msg: str) -> Iterator[dict]:
        full    = ''
        is_reas = self._is_reasoning_model()

        # Reasoning models: 'developer' role instead of 'system',
        #                   'max_completion_tokens' instead of 'max_tokens'
        sys_role   = 'developer' if is_reas else 'system'
        token_key  = 'max_completion_tokens' if is_reas else 'max_tokens'

        stream = self.client.chat.completions.create(
            model=self.model,
            **{token_key: self.meta['max_tokens']},
            messages=[
                {'role': sys_role, 'content': self.system},
                {'role': 'user',   'content': user_msg}
            ],
            stream=True
        )
        for chunk in stream:
            text = chunk.choices[0].delta.content or ''
            if text:
                full += text
                yield {'type': 'token', 'role': self.role, 'text': text}
        yield {'type': 'agent_done', 'role': self.role, 'content': full}


class Orchestrator:
    def __init__(self, client, provider: str = 'anthropic', model: str = 'claude-sonnet-4-6'):
        self.client   = client
        self.provider = provider
        self.model    = model
        self.agents   = {r: Agent(r, client, provider, model) for r in ROLES}

    def build_context(self, idea: str, role: str, done: dict) -> str:
        """Build context for a role using only the artifacts it actually needs."""
        ctx = f'## Product Idea\n{idea}\n\n'
        for prev_role in ROLE_META[role]['context_from']:
            if prev_role in done:
                m = ROLE_META[prev_role]
                ctx += f'## {m["artifact"]} — {m["label"]}\n{done[prev_role]}\n\n'
        return ctx

    def run(self, idea: str) -> Iterator[dict]:
        done = {}
        for role in ROLES:
            m = ROLE_META[role]
            # Keepalive before context build + API call — prevents browser SSE timeout
            # during the silent gap between agents (context assembly + first roundtrip)
            yield {'type': 'keepalive'}
            yield {'type': 'agent_start', 'role': role, 'label': m['label'],
                   'artifact': m['artifact'], 'color': m['color'], 'num': m['num']}
            ctx     = self.build_context(idea, role, done)
            content = ''
            for ev in self.agents[role].stream(ctx):
                if ev['type'] == 'agent_done':
                    content = ev['content']
                    done[role] = content
                yield ev
            # Keepalive after agent finishes — gap before next agent starts
            yield {'type': 'keepalive'}
