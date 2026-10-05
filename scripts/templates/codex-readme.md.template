# me.codex

Generated Codex plugins from [storytellerF/me](https://github.com/storytellerF/me). Edit the source repository; synchronization pull requests are produced only by its GitHub Actions workflow.

## Installation

Add the generated Codex repository as a plugin marketplace:

```bash
codex plugin marketplace add https://github.com/storytellerF/me.codex.git
```

Install plugins from the marketplace:

```bash
codex plugin add android-emulator-profile@me
codex plugin add android-device-lock@me
codex plugin add recyclerview-best-practice@me
codex plugin add general-coding-practices@me
codex plugin add kotlin-coding-practices@me
codex plugin add client-ui-best-practices@me
codex plugin add test-report-sharing@me
codex plugin add diff-sharing@me
codex plugin add qemu-alpine-docker@me
```

Start a new Codex thread after installation so its plugin skills and MCP tools are loaded.

All plugins are listed in `.agents/plugins/marketplace.json`. Source skills are copied unchanged from the portable repository; Claude agent prompts and routing are omitted from Codex packages.

## Migration from storytellerF/me

Remove the old marketplace:

```bash
codex plugin marketplace remove me
```

Then follow the installation steps above to add `storytellerF/me.codex` and reinstall the plugins you use. The marketplace name remains `me`.
