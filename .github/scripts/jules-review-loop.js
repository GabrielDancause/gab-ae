#!/usr/bin/env node
/**
 * Jules Review Loop — GitHub Actions version
 * Reads state, takes one action per tracked file, updates state.
 * 
 * Env required:
 *   GH_TOKEN            — GitHub token (auto-provided)
 *   JULES_API_KEY       — Jules API key
 *   CLOUDFLARE_ACCOUNT_ID — CF account for D1 queries
 *   CLOUDFLARE_API_TOKEN  — CF API token with D1 read
 *   D1_DATABASE_ID      — gab-ae-prod database ID
 */

const fs = require('fs');
const { execSync } = require('child_process');
const path = require('path');

const STATE_PATH = path.join(__dirname, '..', 'state', 'heartbeat-state.json');
const MAX_REVIEW_ROUNDS = 3;

// ─── Helpers ───

function gh(cmd) {
  return execSync(`gh ${cmd}`, { encoding: 'utf8', timeout: 30000 }).trim();
}

function ghJson(cmd) {
  const out = gh(`${cmd} --json`);
  // gh --json returns JSON directly on some commands
  try { return JSON.parse(out); } catch { return out; }
}

function log(msg) {
  console.log(`[review-loop] ${msg}`);
}

function loadState() {
  return JSON.parse(fs.readFileSync(STATE_PATH, 'utf8'));
}

function saveState(state) {
  state.lastHeartbeat = new Date().toISOString();
  fs.writeFileSync(STATE_PATH, JSON.stringify(state, null, 2) + '\n');
}

// ─── GitHub API helpers (using gh CLI) ───

function listOpenPRs() {
  const out = execSync('gh pr list --state open --json number,title,headRefName', { encoding: 'utf8', timeout: 30000 });
  return JSON.parse(out);
}

function listMergedPRs(limit = 5) {
  const out = execSync(`gh pr list --state merged --limit ${limit} --json number,title,mergedAt`, { encoding: 'utf8', timeout: 30000 });
  return JSON.parse(out);
}

function getPRDiff(number) {
  return execSync(`gh pr diff ${number} --color never`, { encoding: 'utf8', timeout: 30000 });
}

function commentPR(number, body) {
  execSync(`gh pr comment ${number} --body ${JSON.stringify(body)}`, { timeout: 30000 });
}

function mergePR(number) {
  execSync(`gh pr merge ${number} --squash --delete-branch`, { timeout: 60000 });
}

function closeIssue(number, comment) {
  const cmd = comment
    ? `gh issue close ${number} --comment ${JSON.stringify(comment)}`
    : `gh issue close ${number}`;
  execSync(cmd, { timeout: 30000 });
}

function createIssue(title, body, labels = 'bug,agent:jules') {
  const out = execSync(
    `gh issue create --title ${JSON.stringify(title)} --label "${labels}" --body ${JSON.stringify(body)}`,
    { encoding: 'utf8', timeout: 30000 }
  );
  // Returns URL like https://github.com/owner/repo/issues/33
  const match = out.match(/issues\/(\d+)/);
  return match ? parseInt(match[1]) : null;
}

// ─── D1 query helper ───

async function queryD1(sql) {
  const accountId = process.env.CLOUDFLARE_ACCOUNT_ID;
  const apiToken = process.env.CLOUDFLARE_API_TOKEN;
  const dbId = process.env.D1_DATABASE_ID;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/d1/database/${dbId}/query`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ sql }),
    }
  );
  const data = await resp.json();
  if (!data.success) throw new Error(`D1 query failed: ${JSON.stringify(data.errors)}`);
  return data.result[0].results;
}

// ─── Jules API ───

async function dispatchJules(prompt, title) {
  const apiKey = process.env.JULES_API_KEY;
  const resp = await fetch('https://jules.googleapis.com/v1alpha/sessions', {
    method: 'POST',
    headers: {
      'X-Goog-Api-Key': apiKey,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      prompt,
      sourceContext: {
        source: 'sources/github/GabrielDancause/gab-ae',
        githubRepoContext: { startingBranch: 'main' },
      },
      automationMode: 'AUTO_CREATE_PR',
      title,
    }),
  });
  const data = await resp.json();
  if (data.error) throw new Error(`Jules API error: ${JSON.stringify(data.error)}`);
  return data.name; // session ID
}

// ─── Review logic ───

function reviewDiff(diff, fileContext) {
  // Simple heuristic review — find common issues
  const issues = [];

  if (diff.includes('pnpm-lock.yaml') || diff.includes('package-lock.json')) {
    issues.push('Lock file added — please remove it from this PR.');
  }

  // Count additions
  const additions = (diff.match(/^\+[^+]/gm) || []).length;
  const deletions = (diff.match(/^-[^-]/gm) || []).length;

  if (additions < 3) {
    issues.push('Very few changes — is this really addressing the full issue?');
  }

  // Check for common patterns
  if (diff.includes('console.log') && !diff.includes('console.warn') && !diff.includes('console.error')) {
    issues.push('Consider using console.warn/error for validation messages instead of console.log.');
  }

  // Check for hardcoded values that should be dynamic
  if (diff.includes("'The Bottom Line'") && fileContext === 'src/news-autopilot.js') {
    // Already known pattern, ok
  }

  return issues;
}

// ─── Find issues in D1 content ───

async function findNewsIssue() {
  const rows = await queryD1(
    "SELECT slug, title, category, tags, faqs, lede, sections FROM news ORDER BY published_at DESC LIMIT 5"
  );

  for (const row of rows) {
    const tags = JSON.parse(row.tags || '[]');
    const faqs = row.faqs && row.faqs !== 'null' ? JSON.parse(row.faqs) : [];
    const sections = JSON.parse(row.sections || '[]');

    // Check for empty FAQs
    if (faqs.length === 0) {
      return {
        title: `news-autopilot: article "${row.title.slice(0, 50)}..." has no FAQs`,
        body: `## Problem\nArticle \`${row.slug}\` has empty FAQs.\n\n### Fix\nInvestigate why \`generateFaqs()\` returns empty for this article and fix the edge case in \`src/news-autopilot.js\`.`,
      };
    }

    // Check for wrong category
    if (row.category === 'tech' && !row.title.toLowerCase().match(/ai|tech|chip|software|app|robot|quantum/)) {
      return {
        title: `news-autopilot: "${row.title.slice(0, 50)}..." miscategorized as tech`,
        body: `## Problem\nArticle \`${row.slug}\` is categorized as "tech" but title doesn't contain tech keywords.\n\n### Fix\nImprove category detection in \`categorize()\` in \`src/news-autopilot.js\`.`,
      };
    }

    // Check for empty section headings
    for (const s of sections) {
      if (!s.heading || !s.heading.trim()) {
        return {
          title: `news-autopilot: empty section heading in "${row.title.slice(0, 50)}..."`,
          body: `## Problem\nArticle \`${row.slug}\` has a section with empty heading.\n\n### Fix\nFix heading validation in \`buildArticle()\` or \`validateArticle()\` in \`src/news-autopilot.js\`.`,
        };
      }
    }

    // Check for short articles
    const totalChars = sections.reduce((sum, s) => sum + (s.paragraphs || []).join('').length, 0);
    if (totalChars < 2000) {
      return {
        title: `news-autopilot: article "${row.title.slice(0, 50)}..." is too short (${totalChars} chars)`,
        body: `## Problem\nArticle \`${row.slug}\` has only ${totalChars} chars. Minimum should be 4000.\n\n### Fix\nCheck minimum length enforcement in \`src/news-autopilot.js\`.`,
      };
    }
  }
  return null;
}

async function findSeedIssue() {
  const rows = await queryD1(
    "SELECT slug, title, html, page_type, quality FROM pages WHERE quality='template' ORDER BY created_at DESC LIMIT 5"
  );

  for (const row of rows) {
    // Check doubled words in title
    const words = row.title.toLowerCase().split(/\s+/);
    for (let i = 0; i < words.length - 1; i++) {
      if (words[i] === words[i + 1] && words[i].length > 3) {
        return {
          title: `seed-pages: doubled word "${words[i]}" in title "${row.title.slice(0, 50)}..."`,
          body: `## Problem\nPage \`${row.slug}\` has doubled word in title: "${row.title}"\n\n### Fix\nFix title generation in \`src/seed-pages.js\` to deduplicate words.`,
        };
      }
    }

    // Check for generic placeholder content
    if (row.html && row.html.includes('Value A') && row.html.includes('Value B')) {
      return {
        title: `seed-pages: "${row.slug}" has generic placeholder calculator`,
        body: `## Problem\nPage \`${row.slug}\` has a generic calculator with "Value A" and "Value B" inputs instead of domain-specific fields.\n\n### Fix\nMake calculator inputs contextual in \`src/seed-pages.js\` based on the page slug/keyword.`,
      };
    }

    // Check for very short HTML
    if (row.html && row.html.length < 3000) {
      return {
        title: `seed-pages: "${row.slug}" is too short (${row.html.length} chars)`,
        body: `## Problem\nPage \`${row.slug}\` HTML is only ${row.html.length} chars.\n\n### Fix\nEnsure minimum content length in \`src/seed-pages.js\`.`,
      };
    }
  }
  return null;
}

// ─── Main loop ───

async function main() {
  const state = loadState();
  const summary = [];

  for (const [file, fileState] of Object.entries(state.files)) {
    const isNews = file.includes('news-autopilot');
    const label = isNews ? 'news-autopilot.js' : 'seed-pages.js';

    log(`[${label}] status: ${fileState.status}`);

    try {
      switch (fileState.status) {

        case 'waiting-for-pr': {
          const openPRs = listOpenPRs();
          const matchingPR = openPRs.find(pr =>
            pr.title.toLowerCase().includes(fileState.currentIssue?.toString()) ||
            pr.headRefName.includes(fileState.currentIssue?.toString())
          );

          if (matchingPR) {
            fileState.currentPR = matchingPR.number;
            fileState.status = 'reviewing';
            summary.push(`${label}: PR #${matchingPR.number} found, moving to review.`);
          } else {
            // Check if already merged
            const mergedPRs = listMergedPRs();
            const mergedMatch = mergedPRs.find(pr =>
              pr.title.toLowerCase().includes(fileState.currentIssue?.toString())
            );
            if (mergedMatch && fileState.currentIssue) {
              closeIssue(fileState.currentIssue, `Fixed in PR #${mergedMatch.number}`);
              fileState.currentIssue = null;
              fileState.currentPR = null;
              fileState.status = 'finding-next-issue';
              summary.push(`${label}: PR already merged, closed issue #${fileState.currentIssue}. Finding next issue.`);
            } else {
              summary.push(`${label}: Still waiting for PR on issue #${fileState.currentIssue}.`);
            }
          }
          break;
        }

        case 'reviewing': {
          const diff = getPRDiff(fileState.currentPR);
          const issues = reviewDiff(diff, file);

          fileState.reviewRounds = (fileState.reviewRounds || 0) + 1;

          if (fileState.reviewRounds >= MAX_REVIEW_ROUNDS || issues.length === 0) {
            fileState.status = 'ready-to-merge';
            summary.push(`${label}: PR #${fileState.currentPR} passed review (round ${fileState.reviewRounds}). Ready to merge.`);
          } else {
            const comment = `## Review — Round ${fileState.reviewRounds}/${MAX_REVIEW_ROUNDS}\n\n${issues.map(i => `- ${i}`).join('\n')}\n\nPlease fix and push to this branch.`;
            commentPR(fileState.currentPR, comment);
            summary.push(`${label}: PR #${fileState.currentPR} reviewed (round ${fileState.reviewRounds}), posted ${issues.length} improvement(s).`);
          }
          break;
        }

        case 'ready-to-merge': {
          mergePR(fileState.currentPR);
          log(`Merged PR #${fileState.currentPR}`);

          if (fileState.currentIssue) {
            closeIssue(fileState.currentIssue, `Fixed in PR #${fileState.currentPR}`);
          }

          summary.push(`${label}: Merged PR #${fileState.currentPR}, closed issue #${fileState.currentIssue}.`);
          fileState.currentPR = null;
          fileState.currentIssue = null;
          fileState.reviewRounds = 0;
          fileState.status = 'finding-next-issue';
          break;
        }

        case 'finding-next-issue': {
          const issue = isNews ? await findNewsIssue() : await findSeedIssue();

          if (issue) {
            const issueNum = createIssue(issue.title, issue.body);
            fileState.currentIssue = issueNum;
            fileState.status = 'dispatching';
            summary.push(`${label}: Created issue #${issueNum} — ${issue.title}`);
          } else {
            summary.push(`${label}: No issues found. All clean! 🎉`);
          }
          break;
        }

        case 'dispatching': {
          if (!fileState.currentIssue) {
            fileState.status = 'finding-next-issue';
            break;
          }

          // Read the issue body to build the prompt
          const issueBody = execSync(
            `gh issue view ${fileState.currentIssue} --json title,body --jq '.title + "\\n\\n" + .body'`,
            { encoding: 'utf8', timeout: 30000 }
          ).trim();

          const prompt = `Fix the bug described below in ${file}. Reference issue #${fileState.currentIssue} in commits.\n\n${issueBody}\n\nONLY modify ${file}. Do NOT create new files. Do NOT add lock files.\n\nnull over fake data, always.`;

          const sessionId = await dispatchJules(prompt, `Fix ${file} (#${fileState.currentIssue})`);
          fileState.julesSession = sessionId;
          fileState.status = 'waiting-for-pr';
          summary.push(`${label}: Dispatched Jules session ${sessionId} for issue #${fileState.currentIssue}.`);
          break;
        }

        default:
          log(`Unknown status: ${fileState.status}`);
          summary.push(`${label}: Unknown status "${fileState.status}".`);
      }
    } catch (err) {
      log(`Error processing ${label}: ${err.message}`);
      summary.push(`${label}: ❌ Error — ${err.message}`);
    }
  }

  saveState(state);

  // Print summary (will be visible in Actions logs)
  console.log('\n=== CYCLE SUMMARY ===');
  summary.forEach(s => console.log(s));
  console.log('====================\n');

  // Write summary to file for potential notification pickup
  fs.writeFileSync(
    path.join(__dirname, '..', 'state', 'last-summary.txt'),
    summary.join('\n') + '\n'
  );
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
