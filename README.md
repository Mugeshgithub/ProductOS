# ProductOS — 4-Role Agentic Product Builder

ProductOS turns a one-line product idea into a full engineering plan in under two minutes. Four AI agents run in sequence, each building on the previous one's output, streamed live to the browser.

---

## How It Works

```
Your Idea  →  PM  →  System Architect  →  Software Architect  →  Launch Engineer
              PRD        HLD                    LLD                  Build Plan
```

| Agent | Artifact | What it produces |
|---|---|---|
| Product Manager | PRD | Problem, users, competitors, monetization, core tech bet, privacy risks |
| System Architect | HLD | Architecture overview, API audit, cost projection, failure modes |
| Software Architect | LLD | Tech stack, data model, folder structure, security & rate limiting |
| Launch Engineer | Build Plan | Build sequence, Day 1 prompt, hard problems, deployment path |

Each agent receives only the artifacts it needs — keeping token usage tight without losing context.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Mugeshgithub/ProductOS
cd ProductOS

# 2. Install dependencies
pip install flask flask-cors anthropic openai python-dotenv

# 3. Set your API key (or enter it in the UI settings panel)
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# 4. Run
python app.py
# Open http://localhost:5002
```

---

## Providers

### Anthropic
Set `ANTHROPIC_API_KEY` in `.env` or paste it in the settings panel.
Models: `claude-sonnet-4-5`, `claude-opus-4-5`, `claude-haiku-4-5`

### OpenAI
Set `OPENAI_API_KEY` in `.env` or paste it in the settings panel.
Models: `gpt-4o`, `o4-mini`, `o3`

### Ollama (free, runs locally — no API key needed)

```bash
# Install: https://ollama.com
ollama serve
ollama pull llama3.2
```

Select **Ollama** in the settings panel and pick your model.

---

## Customising the Prompts

> **Do this before deploying.** The prompts define what each agent produces. Tuning them for your domain makes a significant difference in output quality.

Prompts live in `prompts/` as plain Markdown files:

```
prompts/
  pm_agent.md           ← Product Manager instructions
  system_architect.md   ← System Architect instructions
  software_architect.md ← Software Architect instructions
  launch_engineer.md    ← Launch Engineer instructions
```

**What to change:**
- Add domain constraints (e.g. "always include HIPAA compliance notes for health apps")
- Adjust mandatory sections (add regulatory requirements, remove sections you don't need)
- Change output format (more tables, less prose, specific section order)
- Tune tone (startup-lean vs enterprise-formal)

No code changes needed — edit the `.md` files directly.

---

## Deployment

> Vercel serverless functions have a 10-second timeout. For SSE streaming, deploy to a platform that supports long-running connections: **Railway**, **Render**, or **Fly.io**.

```bash
# Procfile (Railway / Render)
web: python app.py
```

Set API keys as environment variables in the platform dashboard. Never commit `.env`.

For production, replace SQLite with a hosted database and set `SECRET_KEY` for session signing.

---

## Project Structure

```
ProductOS/
  app.py              Flask server + SSE streaming
  agents.py           Agent and Orchestrator logic
  index.html          Single-page UI (no build step)
  prompts/            Agent system prompts — customise these
  build.py            CLI runner (terminal mode)
```

---

## Stack

- **Backend**: Python / Flask with SSE (`text/event-stream`)
- **Frontend**: Vanilla JS — no framework, no build step
- **DB**: SQLite (sessions + artifacts)
- **AI**: Anthropic, OpenAI, or Ollama — switchable at runtime

---

## License

MIT
