# Second Brain

A local, file-based AI memory layer for **Claude Code, Codex, and OpenCode** that works across all of your projects.

You keep running each agent inside your normal project directories. The central vault stays separate and provides shared memory, session capture, historical transcript import, and a provenance-aware Markdown wiki that works well with Obsidian.

## Features

- Shared central memory for Claude Code, Codex, and OpenCode
- Live checkpoints (default: every 10 minutes)
- Session-end and pre-compaction capture
- Historical Claude/Codex JSONL import
- Lossless raw transcript backup under `raw/history/`
- Active history compilation into projects, entities, concepts, decisions, syntheses, rules, and threads
- Plain Markdown + Obsidian-friendly wikilinks
- Local-first and Git-versioned
- No database required
- No extra API key required when a supported authenticated CLI is available

## Install

```bash
git clone https://github.com/dogankoc/SecondBrain.git
cd SecondBrain
./install.sh
```

Default vault: `~/Documents/Second Brain`

Optional:

```bash
./install.sh \
  --name "Alex" \
  --path "$HOME/Documents/Second Brain" \
  --language en \
  --checkpoint-minutes 10
```

Upgrade:

```bash
./install.sh --path "$HOME/Documents/Second Brain" --upgrade
```

## Normal usage

```bash
cd ~/Projects/my-project
claude
```

or `codex` / `opencode`. You do **not** need to run an agent inside the vault.

## Import old conversations

```bash
./import-history.sh "$HOME/Documents/Second Brain"
```

Then compile durable knowledge from imported history:

```bash
./compile-history.sh "$HOME/Documents/Second Brain" --limit 5
./compile-history.sh "$HOME/Documents/Second Brain"
```

## Obsidian

Open `~/Documents/Second Brain` as a vault. Obsidian is optional; the memory engine itself uses the filesystem.

## Safety model

- `raw/` is immutable.
- Imported JSONL files are preserved unchanged.
- Durable claims preserve source links.
- Contradictions are surfaced instead of silently overwritten.
- Project-local files remain authoritative for project-specific facts.
- Do not store secrets, passwords, tokens, or credentials in the vault.
- No Git remote is created automatically.

## Verify

```bash
./verify.sh
```

## License

MIT

---

_Authored and maintained by [Doğan Koç](https://github.com/dogankoc)._
