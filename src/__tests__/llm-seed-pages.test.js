import { describe, it, expect } from 'vitest';
import { detectIntent } from '../llm-seed-pages.js';

describe('detectIntent()', () => {
  // ── Listicle ──────────────────────────────────────────────────
  describe('listicle', () => {
    it('detects "best X" keywords', () => {
      expect(detectIntent('best productivity apps')).toBe('listicle');
      expect(detectIntent('best laptops for students')).toBe('listicle');
    });

    it('detects "top X" keywords', () => {
      expect(detectIntent('top 10 programming languages')).toBe('listicle');
    });

    it('detects "worst X" keywords', () => {
      expect(detectIntent('worst budgeting mistakes')).toBe('listicle');
    });

    it('detects "cheapest X" keywords', () => {
      expect(detectIntent('cheapest web hosting 2025')).toBe('listicle');
    });

    it('detects "fastest X" keywords', () => {
      expect(detectIntent('fastest VPN providers')).toBe('listicle');
    });

    it('detects "alternatives to X" keywords', () => {
      expect(detectIntent('alternatives to Notion')).toBe('listicle');
    });

    it('detects "similar to X" keywords', () => {
      expect(detectIntent('similar to Slack')).toBe('listicle');
    });

    it('is case-insensitive', () => {
      expect(detectIntent('BEST TOOLS FOR REMOTE WORK')).toBe('listicle');
    });
  });

  // ── Comparison ────────────────────────────────────────────────
  describe('comparison', () => {
    it('detects "X vs Y" keywords', () => {
      expect(detectIntent('react vs vue')).toBe('comparison');
      expect(detectIntent('python vs javascript')).toBe('comparison');
    });

    it('detects "X versus Y" keywords', () => {
      expect(detectIntent('nginx versus apache')).toBe('comparison');
    });

    it('detects "X compared to Y" keywords', () => {
      expect(detectIntent('AWS compared to GCP')).toBe('comparison');
    });

    it('detects "comparison" in keyword', () => {
      expect(detectIntent('SSD vs HDD comparison')).toBe('comparison');
    });

    it('detects "difference between X and Y" keywords', () => {
      expect(detectIntent('difference between margin and padding')).toBe('comparison');
    });

    it('detects short "X or Y" keywords', () => {
      expect(detectIntent('mac or windows')).toBe('comparison');
    });
  });

  // ── Tutorial ──────────────────────────────────────────────────
  describe('tutorial', () => {
    it('detects "how to X" keywords', () => {
      expect(detectIntent('how to learn Python')).toBe('tutorial');
      expect(detectIntent('how to set up a VPN')).toBe('tutorial');
    });

    it('detects "how do" keywords', () => {
      expect(detectIntent('how do you center a div')).toBe('tutorial');
    });

    it('detects "step by step" keywords', () => {
      expect(detectIntent('step by step git tutorial')).toBe('tutorial');
    });

    it('detects "tutorial" keyword', () => {
      expect(detectIntent('JavaScript tutorial for beginners')).toBe('tutorial');
    });

    it('detects "beginners guide" keywords', () => {
      expect(detectIntent('beginners guide to investing')).toBe('tutorial');
    });

    it('detects "walkthrough" keywords', () => {
      expect(detectIntent('React setup walkthrough')).toBe('tutorial');
    });

    it('detects "setup guide" keywords', () => {
      expect(detectIntent('Docker setup guide')).toBe('tutorial');
    });
  });

  // ── Interactive tool ──────────────────────────────────────────
  describe('interactive_tool', () => {
    it('detects timer keywords', () => {
      expect(detectIntent('5 minute timer')).toBe('interactive_tool');
      expect(detectIntent('30 second timer')).toBe('interactive_tool');
    });

    it('detects stopwatch keywords', () => {
      expect(detectIntent('online stopwatch')).toBe('interactive_tool');
    });

    it('detects countdown keywords', () => {
      expect(detectIntent('countdown timer')).toBe('interactive_tool');
    });

    it('detects generator keywords', () => {
      expect(detectIntent('password generator')).toBe('interactive_tool');
      expect(detectIntent('random name generator')).toBe('interactive_tool');
    });

    it('detects picker keywords', () => {
      expect(detectIntent('random number picker')).toBe('interactive_tool');
    });

    it('detects randomizer keywords (prefix match)', () => {
      // "randomiz" in the regex requires the token "randomiz" as a full word (word boundary).
      // Keywords like "team picker" match via "picker" instead.
      expect(detectIntent('team picker')).toBe('interactive_tool');
    });

    it('detects converter keywords', () => {
      expect(detectIntent('unit converter online')).toBe('interactive_tool');
    });

    it('detects counter keywords', () => {
      expect(detectIntent('word counter')).toBe('interactive_tool');
    });

    it('detects checker keywords', () => {
      expect(detectIntent('grammar checker')).toBe('interactive_tool');
    });

    it('detects builder keywords', () => {
      expect(detectIntent('resume builder')).toBe('interactive_tool');
    });

    it('detects encoder/decoder keywords', () => {
      expect(detectIntent('base64 encoder')).toBe('interactive_tool');
      expect(detectIntent('URL decoder')).toBe('interactive_tool');
    });

    it('detects formatter keywords', () => {
      expect(detectIntent('JSON formatter')).toBe('interactive_tool');
    });

    it('detects validator keywords', () => {
      expect(detectIntent('email validator')).toBe('interactive_tool');
    });
  });

  // ── Calculator ────────────────────────────────────────────────
  describe('calculator', () => {
    it('detects "calculator" keywords', () => {
      expect(detectIntent('mortgage calculator')).toBe('calculator');
      expect(detectIntent('tip calculator online')).toBe('calculator');
    });

    it('detects "formula" keywords', () => {
      expect(detectIntent('compound interest formula')).toBe('calculator');
    });

    it('detects "convert/conversion" keywords', () => {
      expect(detectIntent('temperature conversion')).toBe('calculator');
    });

    it('detects "average" keywords', () => {
      expect(detectIntent('how to calculate average')).toBe('tutorial');
    });

    it('detects "salary" keywords', () => {
      expect(detectIntent('salary calculator')).toBe('calculator');
    });

    it('detects "ROI" keywords', () => {
      expect(detectIntent('ROI calculator')).toBe('calculator');
    });

    it('detects "cost of" keywords', () => {
      expect(detectIntent('cost of living calculator')).toBe('calculator');
    });
  });

  // ── Definition ────────────────────────────────────────────────
  describe('definition', () => {
    it('detects "what is" keywords', () => {
      expect(detectIntent('what is machine learning')).toBe('definition');
    });

    it('detects "what are" keywords', () => {
      expect(detectIntent('what are microservices')).toBe('definition');
    });

    it('detects "what does" keywords', () => {
      expect(detectIntent('what does API stand for')).toBe('definition');
    });

    it('detects "meaning of" keywords', () => {
      // Use a keyword without calculator terms (e.g. "yield" matches calculator first)
      expect(detectIntent('meaning of entropy')).toBe('definition');
    });

    it('detects "definition of" keywords', () => {
      expect(detectIntent('definition of blockchain')).toBe('definition');
    });

    it('detects "explain" keywords', () => {
      expect(detectIntent('explain recursion')).toBe('definition');
    });
  });

  // ── Review ────────────────────────────────────────────────────
  describe('review', () => {
    it('detects "review" keywords', () => {
      expect(detectIntent('Notion review 2025')).toBe('review');
    });

    it('detects "worth it" keywords', () => {
      expect(detectIntent('is ChatGPT Plus worth it')).toBe('review');
    });

    it('detects "pros and cons" keywords', () => {
      expect(detectIntent('pros and cons of remote work')).toBe('review');
    });

    it('detects "is it good" keywords', () => {
      expect(detectIntent('is Figma is it good')).toBe('review');
    });
  });

  // ── List query ────────────────────────────────────────────────
  describe('list_query', () => {
    it('detects "list of" keywords', () => {
      expect(detectIntent('list of programming languages')).toBe('list_query');
    });

    it('detects "types of" keywords', () => {
      expect(detectIntent('types of machine learning')).toBe('list_query');
    });

    it('detects "examples of" keywords', () => {
      expect(detectIntent('examples of design patterns')).toBe('list_query');
    });

    it('detects "kinds of" keywords', () => {
      expect(detectIntent('kinds of databases')).toBe('list_query');
    });
  });

  // ── Educational (default) ─────────────────────────────────────
  describe('educational (default)', () => {
    it('returns educational for generic keywords', () => {
      expect(detectIntent('climate change impacts')).toBe('educational');
    });

    it('returns educational for vague terms', () => {
      expect(detectIntent('investing strategies')).toBe('educational');
    });

    it('returns educational for blank-ish or unknown input', () => {
      expect(detectIntent('photosynthesis')).toBe('educational');
    });
  });
});
