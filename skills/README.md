# pysepal skills

Claude Code skills for building SEPAL apps with pysepal.

| skill                        | what it does                                                                                      |
| ---------------------------- | ------------------------------------------------------------------------------------------------- |
| [`pysepal`](pysepal)         | Component discovery, Solara and Earth Engine patterns, error diagnosis, and audits of stale code. |
| [`pysepal-app`](pysepal-app) | Scaffold or restructure a pysepal Solara or Voila app.                                            |

## Install

This repository is a Claude Code plugin marketplace. Add it once and both skills
stay current: Claude Code checks installed plugins for updates once per session.

```bash
claude plugin marketplace add openforis/pysepal
claude plugin install pysepal@pysepal
```

The skills load as `pysepal:pysepal` and `pysepal:pysepal-app`. The plugin version
is the pysepal release it documents, and each skill compares that against the
pysepal installed in the app's environment before relying on API details.

## Contributing

Symlink the skill directories into `~/.claude/skills/` instead of installing the
plugin, so edits are live without a reinstall:

```bash
ln -s "$PWD/skills/pysepal" ~/.claude/skills/pysepal
ln -s "$PWD/skills/pysepal-app" ~/.claude/skills/pysepal-app
```

Validate the manifests and skills before opening a pull request:

```bash
claude plugin validate .
```

The version stamps in `.claude-plugin/` and in each `SKILL.md` are bumped by
`cz bump` together with the package version. Do not edit them by hand.
