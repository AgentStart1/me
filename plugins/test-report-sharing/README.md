# Test Report Sharing Plugin

Collect reports and code diffs, then share them via a public ngrok tunnel.

## Features

- **Report Collection**: Automatically discovers and collects test reports (JUnit XML, HTML, E2E) from standard project locations
- **Diff Report Generation**: Creates HTML diff reports with syntax highlighting from git changes
- **Static Site Generation**: Assembles all artifacts into a beautiful, responsive HTML report site
- **Ngrok Integration**: Exposes the report site via a public ngrok tunnel for easy sharing

## Quick Start

### Using the Agent (Recommended)

The `test-report-operator` agent coordinates the entire workflow automatically:

```bash
# The agent will:
# 1. Inspect your project structure
# 2. Collect reports from build/reports/
# 3. Generate diff report
# 4. Create static site
# 5. Start ngrok tunnel
# 6. Return public URL and summary
```

### Manual Script Execution

```bash
# 1. Collect reports
plugins/test-report-sharing/scripts/collect-test-results.sh

# 2. Generate diff report
plugins/test-report-sharing/scripts/generate-diff-report.sh

# 3. Generate static site
plugins/test-report-sharing/scripts/generate-report-site.sh

# 4. Start ngrok tunnel
plugins/test-report-sharing/scripts/start-ngrok.sh
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REPORT_OUTPUT_DIR` | Output directory for reports | `~/.cache/test-reports/<project-hash>` |
| `REPORT_DIRS` | Colon-separated list of report directories | Auto-detect (`build/reports/`) |
| `NGROK_AUTHTOKEN` | ngrok authentication token | (required for public tunnel) |
| `NGROK_PORT` | Local port to expose | `8080` |
| `GIT_BASE_REF` | Base git ref for diff comparison | `main` |
| `GIT_COMPARE_REF` | Compare git ref | `HEAD` |

### Command Line Options

Each script supports `--help` for detailed usage:

```bash
plugins/test-report-sharing/scripts/collect-test-results.sh --help
plugins/test-report-sharing/scripts/generate-diff-report.sh --help
plugins/test-report-sharing/scripts/generate-report-site.sh --help
plugins/test-report-sharing/scripts/start-ngrok.sh --help
```

## Supported Input Formats

### Reports
- JUnit XML reports (`*-tests.xml`, `TEST-*.xml`)
- HTML test reports (`*.html` in test output directories)
- E2E test reports with embedded video playback
- Gradle/Maven test output directories (`build/reports/`)

### Diff Reports
- Git diff output converted to HTML with syntax highlighting
- Supports comparison against any git ref (branch, commit, tag)

## Project Structure

```
plugins/test-report-sharing/
├── .claude-plugin/
│   └── plugin.json              # Claude Code plugin manifest
├── agents/
│   └── test-report-operator.md  # Agent for coordinating workflow
├── skills/
│   └── test-report-sharing/
│       └── SKILL.md             # Skill instructions
├── scripts/
│   ├── collect-test-results.sh  # Collect reports
│   ├── generate-diff-report.sh  # Generate diff report
│   ├── generate-report-site.sh  # Generate static site
│   └── start-ngrok.sh           # Start ngrok tunnel
├── templates/
│   ├── index.html               # HTML template
│   └── style.css                # Stylesheet
└── README.md                    # This file
```

## Requirements

- **Bash**: Scripts require bash 4.0+
- **jq**: JSON processing (usually pre-installed)
- **git**: For diff report generation
- **Python 3**: For local HTTP server (optional)
- **ngrok**: For public tunnel (optional, can use local server)

### Installing ngrok

```bash
# macOS
brew install ngrok

# Linux
snap install ngrok

# Windows
choco install ngrok

# Or download from: https://ngrok.com/download
```

### Setting up ngrok

1. Sign up at https://ngrok.com
2. Get your authtoken from https://dashboard.ngrok.com/get-started/your-authtoken
3. Set the environment variable:
   ```bash
   export NGROK_AUTHTOKEN="your_token_here"
   ```

## Examples

### Basic Usage

```bash
# Run the full workflow
cd /path/to/your/project
plugins/test-report-sharing/scripts/generate-report-site.sh
plugins/test-report-sharing/scripts/start-ngrok.sh
```

### Custom Configuration

```bash
# Custom report directories
export REPORT_DIRS="./build/reports:./app/build/reports"

# Custom base ref for diff
export GIT_BASE_REF="develop"

# Run with custom config
plugins/test-report-sharing/scripts/collect-test-results.sh
plugins/test-report-sharing/scripts/generate-diff-report.sh
plugins/test-report-sharing/scripts/generate-report-site.sh
```

### Viewing Reports Locally

```bash
# Generate report
plugins/test-report-sharing/scripts/generate-report-site.sh

# View in browser
open ~/.cache/test-reports/<project-hash>/index.html

# Or start local server
cd ~/.cache/test-reports/<project-hash>
python3 -m http.server 8080
# Open http://localhost:8080
```

## Troubleshooting

### No reports found
- Check that your test framework outputs to standard locations (`build/reports/`)
- Set `REPORT_DIRS` to point to your report directories
- Run your tests first to generate reports

### ngrok not working
- Verify ngrok is installed: `ngrok version`
- Check authtoken: `ngrok config check`
- Ensure port is not in use: `lsof -i :8080`
- Try a different port: `NGROK_PORT=9090 ./start-ngrok.sh`

### Diff generation failed
- Ensure you're in a git repository
- Check that the base ref exists: `git rev-parse main`
- Verify you have changes to compare

## License

This plugin is part of the me plugin collection.