# Gab-ae Workflow Guide

## Repository Overview
- **Main Application**: Cloudflare Worker handling routing and cron jobs (`src/worker.js`)
- **Key Components**:
  - `src/llm-news.js`: Automated news generation from RSS feeds (primary pipeline)
  - `src/llm-seed-pages.js`: Seed page generator (deprecated)
  - `src/engines/`: Page renderers (news, calculator, changelog)
  - `templates/layout.js`: HTML layout structure
  - `database/`: D1 database schema and queries

## Essential Tools & Commands
- `git`: Version control (add, commit, push, branch)
- `gh`: GitHub CLI for PR creation and management
- `exec`: Shell command execution (when needed)
- `write`/`edit`/`read`: File operations via OpenClaw tools

## Git Workflow for Changes
1. **Create Feature Branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**: Modify files in the workspace

3. **Stage Changes**:
   ```bash
   git add <files>
   ```

4. **Commit**:
   ```bash
   git commit -m "Descriptive message following conventional commits"
   ```

5. **Push**:
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Create Pull Request**:
   ```bash
   gh pr create --title "PR Title" --body "PR Description" --base main --head feature/your-feature-name
   ```

## Pull Request Best Practices
- Keep PRs focused on a single concern
- Include clear description of what/why changes were made
- Reference related issues if applicable
- Ensure CI/CD passes (if configured)
- Request review from relevant team members

## Model/Agent Guidelines
When modifying this repository as an automated agent:

### Before Making Changes
1. Review `MEMORY.md` and recent daily memory files for context
2. Check current branch status: `git status`
3. Verify you're working from an updated main branch

### During Development
1. Always create a feature branch for changes
2. Make small, atomic commits with clear messages
3. Test changes locally when possible
4. Follow existing code style and patterns

### PR Creation
1. Push feature branch to origin
2. Create PR using `gh pr create` with descriptive title/body
3. Reference this guidelines file if helpful for reviewers
4. Respond to review comments promptly

### After Merge
1. Delete local feature branch: `git branch -d feature/name`
2. Pull updated main: `git checkout main && git pull`
3. Clean up any temporary files

## Common File Locations
- **News Worker**: `src/llm-news.js`
- **Seed Pages**: `src/llm-seed-pages.js`
- **Calculator Engine**: `src/engines/calculator.js`
- **Layout/Templates**: `src/templates/`
- **Database Schema**: `schema.sql`
- **Configuration**: `wrangler.toml`

## Environment Variables
- `DB`: D1 database binding
- `OPENROUTER_API_KEY`: Primary LLM API key
- `ANTHROPIC_API_KEY`: Fallback LLM API key

## Coding Standards
- JavaScript/TypeScript with ESLint
- Descriptive variable and function names
- Comments for complex logic
- Consistent indentation (2 spaces)
- Error handling with try/catch where appropriate

## Getting Help
- Check `MEMORY.md` for recent context and decisions
- Review daily memory files in `memory/YYYY-MM-DD.md`
- Consult `SOUL.md` for core principles and boundaries
- Refer to `USER.md` for user-specific preferences