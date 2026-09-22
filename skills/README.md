# pysepal skills

Claude Code skills for building SEPAL apps with pysepal.

| skill                        | what it does                                                                                      |
| ---------------------------- | ------------------------------------------------------------------------------------------------- |
| [`pysepal`](pysepal)         | Component discovery, Solara and Earth Engine patterns, error diagnosis, and audits of stale code. |
| [`pysepal-app`](pysepal-app) | Scaffold or restructure a pysepal Solara or Voila app.                                            |

## Install

This repository is a Claude Code plugin marketplace. Install the plugin at project
scope, from inside the app repository:

```bash
claude plugin marketplace add openforis/pysepal --scope project
claude plugin install pysepal@pysepal --scope project
```

That writes the marketplace and the plugin into the app's `.claude/settings.json`,
so commit it: every developer who opens the repo gets the skills, Claude Code
checks them for updates once per session, and no other repository sees them.
These patterns are for standalone pysepal apps, not for the SEPAL platform
codebase, so do not install the plugin at user scope.

```json
{
  "extraKnownMarketplaces": {
    "pysepal": { "source": { "source": "github", "repo": "openforis/pysepal" } }
  },
  "enabledPlugins": { "pysepal@pysepal": true }
}
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
