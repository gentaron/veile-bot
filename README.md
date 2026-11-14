# veile-bot

> A Jupyter Notebook project by gentaron

## Overview

This is a Jupyter Notebook project. Please see the source code for details.

## Tech Stack

- Language: Jupyter Notebook, JSON, Python
- Architecture: flat

## Getting Started

```bash
git clone https://github.com/gentaron/veile-bot.git
cd veile-bot
```

## License

MIT

## LINE credentials

The committed `info.json` was removed. Treat its token as compromised: revoke it in LINE Developers and issue a new one. Removing a file from the current branch does not remove it from Git history.

For local use, set `LINE_CHANNEL_ACCESS_TOKEN` and `LINE_USER_ID` in the process environment before running `python main.py`. Do not commit their values.

For GitHub Actions, add repository secrets with those two names. The `chatbot` workflow runs only when started manually from the Actions tab; it no longer sends a LINE message on every push.
