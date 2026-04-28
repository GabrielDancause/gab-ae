from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak, Frame, PageTemplate
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import Flowable
from reportlab.pdfgen import canvas as pdfcanvas

# ── Palette ───────────────────────────────────────────────────────────────────
NOIR        = colors.HexColor("#0D0D0D")
DARK        = colors.HexColor("#1A1A1A")
CHARCOAL    = colors.HexColor("#2C2C2C")
CREAM       = colors.HexColor("#FAF8F4")
WARM_WHITE  = colors.HexColor("#F5F2EE")
GOLD        = colors.HexColor("#C9A96E")
GOLD_DARK   = colors.HexColor("#A07840")
GOLD_LIGHT  = colors.HexColor("#F5ECD8")
ROSE        = colors.HexColor("#B5546A")
ROSE_LIGHT  = colors.HexColor("#FAF0F2")
ROSE_MID    = colors.HexColor("#E8C4CC")
TEAL        = colors.HexColor("#3D7A8A")
TEAL_LIGHT  = colors.HexColor("#EAF4F7")
PLUM        = colors.HexColor("#6B3F7E")
PLUM_LIGHT  = colors.HexColor("#F2EAF7")
DANGER      = colors.HexColor("#B03A2E")
DANGER_BG   = colors.HexColor("#FDECEA")
MUTED       = colors.HexColor("#999999")
BORDER      = colors.HexColor("#E8E2DA")
WHITE       = colors.white

W, H = A4
MARGIN = 20 * mm
CONTENT_W = W - 2 * MARGIN


# ── Decorative Flowables ──────────────────────────────────────────────────────

class LeftBar(Flowable):
    """Colored left-border accent bar for section titles."""
    def __init__(self, title, subtitle="", bar_color=GOLD, title_color=NOIR,
                 bar_width=3, height=18*mm):
        super().__init__()
        self.title = title
        self.subtitle = subtitle
        self.bar_color = bar_color
        self.title_color = title_color
        self.bar_w = bar_width
        self.height = height
        self.width = CONTENT_W

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        # Left accent bar
        c.setFillColor(self.bar_color)
        c.rect(0, 0, self.bar_w, self.height, fill=1, stroke=0)
        # Title
        c.setFillColor(self.title_color)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(self.bar_w + 5*mm, self.height - 7*mm, self.title)
        # Subtitle
        if self.subtitle:
            c.setFont("Helvetica", 8)
            c.setFillColor(MUTED)
            c.drawString(self.bar_w + 5*mm, 4*mm, self.subtitle)


class ChapterHeader(Flowable):
    """Full-width chapter divider with colored background and top rule."""
    def __init__(self, label, sub="", bg=NOIR, fg=WHITE, accent=GOLD):
        super().__init__()
        self.label = label
        self.sub = sub
        self.bg = bg
        self.fg = fg
        self.accent = accent
        self.width = CONTENT_W
        self.height = 20 * mm

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        # Background
        c.setFillColor(self.bg)
        c.roundRect(0, 0, self.width, self.height, 5, fill=1, stroke=0)
        # Gold top rule
        c.setFillColor(self.accent)
        c.rect(0, self.height - 2, self.width, 2, fill=1, stroke=0)
        # Label
        c.setFillColor(self.fg)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(7*mm, self.height - 9*mm, self.label)
        # Sub
        if self.sub:
            c.setFont("Helvetica", 8)
            c.setFillColor(self.accent)
            c.drawString(7*mm, 5*mm, self.sub)


class StatCard(Flowable):
    """Row of stat cards with number + label."""
    def __init__(self, stats, bg=CREAM, accent=GOLD):
        super().__init__()
        self.stats = stats  # [(value, label), ...]
        self.bg = bg
        self.accent = accent
        self.width = CONTENT_W
        self.height = 20 * mm

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        n = len(self.stats)
        cell_w = self.width / n
        for i, (val, lbl) in enumerate(self.stats):
            x = i * cell_w
            # Card bg
            c.setFillColor(self.bg)
            c.roundRect(x + 1, 1, cell_w - 2, self.height - 2, 4, fill=1, stroke=0)
            # Top accent line
            c.setFillColor(self.accent)
            c.rect(x + 1, self.height - 3, cell_w - 2, 2, fill=1, stroke=0)
            # Value
            c.setFillColor(self.accent)
            c.setFont("Helvetica-Bold", 16)
            val_w = c.stringWidth(val, "Helvetica-Bold", 16)
            c.drawString(x + cell_w/2 - val_w/2, self.height/2 + 1, val)
            # Label
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 7)
            lbl_w = c.stringWidth(lbl, "Helvetica", 7)
            c.drawString(x + cell_w/2 - lbl_w/2, 5, lbl)


class AlertStrip(Flowable):
    """Alert box with left color bar."""
    def __init__(self, text, bar_color=DANGER, bg=DANGER_BG, text_color=DANGER,
                 height=13*mm):
        super().__init__()
        self.text = text
        self.bar_color = bar_color
        self.bg = bg
        self.text_color = text_color
        self.height = height
        self.width = CONTENT_W

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(self.bg)
        c.roundRect(0, 0, self.width, self.height, 3, fill=1, stroke=0)
        c.setFillColor(self.bar_color)
        c.roundRect(0, 0, 4, self.height, 2, fill=1, stroke=0)
        c.setFillColor(self.text_color)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(8*mm, self.height/2 - 4, self.text)


class GoldRule(Flowable):
    def __init__(self, width_pct=1.0):
        super().__init__()
        self.wp = width_pct
        self.width = CONTENT_W
        self.height = 1

    def wrap(self, *_):
        return self.width, 1

    def draw(self):
        c = self.canv
        rw = self.width * self.wp
        offset = (self.width - rw) / 2
        c.setStrokeColor(GOLD)
        c.setLineWidth(0.5)
        c.line(offset, 0, offset + rw, 0)


# ── Canvas callbacks for page backgrounds ────────────────────────────────────

def draw_cover_bg(c, doc):
    # White background — ink-friendly for B&W printing
    c.setFillColor(WHITE)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    # Top border rule (thin, black)
    c.setStrokeColor(NOIR)
    c.setLineWidth(2)
    c.line(0, H - 2, W, H - 2)
    c.setLineWidth(0.5)
    c.line(0, H - 5, W, H - 5)
    # Bottom rule + footer text
    c.setLineWidth(0.5)
    c.line(MARGIN, 10*mm, W - MARGIN, 10*mm)
    c.setFillColor(NOIR)
    c.setFont("Helvetica", 7)
    c.drawString(MARGIN, 6*mm, "CONFIDENTIAL — GAB & ALI  ·  APRIL 2026")
    page_w = c.stringWidth(f"{doc.page}", "Helvetica", 7)
    c.drawString(W - MARGIN - page_w, 6*mm, f"{doc.page}")


def draw_body_bg(c, doc):
    c.setFillColor(CREAM)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    # Bottom strip
    c.setFillColor(DARK)
    c.rect(0, 0, W, 8*mm, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.setFont("Helvetica", 7)
    c.drawString(MARGIN, 3*mm, "GAB & ALI  ·  SOCIAL MEDIA STRATEGY  ·  APRIL 2026")
    page_w = c.stringWidth(f"{doc.page}", "Helvetica", 7)
    c.drawString(W - MARGIN - page_w, 3*mm, f"{doc.page}")
    # Top gold hairline
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.5)
    c.line(MARGIN, H - MARGIN*0.5, W - MARGIN, H - MARGIN*0.5)


# ── Styles ────────────────────────────────────────────────────────────────────
def make_styles():
    def s(name, **kw):
        base = dict(fontName="Helvetica", fontSize=9.5, leading=14,
                    textColor=NOIR)
        return ParagraphStyle(name, **{**base, **kw})
    return {
        "body":       s("body", spaceAfter=3, leading=14),
        "body_cream": s("body_cream", spaceAfter=3, leading=14, textColor=NOIR),
        "small":      s("small", fontSize=8, textColor=MUTED),
        "todo":       s("todo", fontSize=8.5, textColor=NOIR, leading=13, leftIndent=3*mm),
        # Cover styles (dark bg)
        "cv_eyebrow": s("cv_eyebrow", fontSize=8, textColor=NOIR,
                        fontName="Helvetica-Bold", alignment=TA_CENTER,
                        spaceAfter=3),
        "cv_title":   s("cv_title", fontName="Helvetica-Bold", fontSize=40,
                        leading=44, textColor=NOIR, alignment=TA_CENTER,
                        spaceAfter=2),
        "cv_title2":  s("cv_title2", fontName="Helvetica-Bold", fontSize=40,
                        leading=44, textColor=NOIR, alignment=TA_CENTER,
                        spaceAfter=4),
        "cv_sub":     s("cv_sub", fontSize=11, textColor=MUTED,
                        alignment=TA_CENTER, spaceAfter=6),
        "cv_item":    s("cv_item", fontSize=9, textColor=NOIR, leading=14),
        "cv_cat":     s("cv_cat", fontName="Helvetica-Bold", fontSize=7,
                        textColor=NOIR, spaceAfter=2, spaceBefore=4),
        # Body page styles
        "prop_name":  s("prop_name", fontName="Helvetica-Bold", fontSize=12,
                        textColor=NOIR, spaceBefore=2, spaceAfter=1),
        "prop_sub":   s("prop_sub", fontSize=8.5, textColor=MUTED, spaceAfter=3),
        "label":      s("label", fontName="Helvetica-Bold", fontSize=7.5,
                        textColor=GOLD, spaceAfter=1),
        "stat_num":   s("stat_num", fontName="Helvetica-Bold", fontSize=20,
                        textColor=GOLD, alignment=TA_CENTER),
        "stat_lbl":   s("stat_lbl", fontSize=7, textColor=MUTED,
                        alignment=TA_CENTER),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────
def sp(n=3):
    return Spacer(1, n * mm)

def platform_table(rows, accent):
    header = ["Platform", "Handle / Link", "Notes"]
    data = [header] + rows
    col_w = [CONTENT_W * x for x in [0.18, 0.32, 0.50]]
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",      (0, 0), (-1, 0), accent),
        ("TEXTCOLOR",       (0, 0), (-1, 0), WHITE),
        ("FONTNAME",        (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",        (0, 0), (-1,  0), 7.5),
        ("TOPPADDING",      (0, 0), (-1,  0), 5),
        ("BOTTOMPADDING",   (0, 0), (-1,  0), 5),
        ("FONTSIZE",        (0, 1), (-1, -1), 8),
        ("FONTNAME",        (0, 1), (-1, -1), "Helvetica"),
        ("TEXTCOLOR",       (0, 1), (-1, -1), NOIR),
        ("ROWBACKGROUNDS",  (0, 1), (-1, -1), [WHITE, WARM_WHITE]),
        ("TOPPADDING",      (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING",   (0, 1), (-1, -1), 4),
        ("LEFTPADDING",     (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",    (0, 0), (-1, -1), 5),
        ("LINEBELOW",       (0, 0), (-1, -1), 0.25, BORDER),
        ("LINEAFTER",       (0, 0), (-2, -1), 0.25, BORDER),
    ]))
    return t


# ── Cover page ────────────────────────────────────────────────────────────────
def cover_page(story, styles):
    story.append(sp(22))
    story.append(Paragraph("GAB &amp; ALI", styles["cv_eyebrow"]))
    story.append(sp(3))
    story.append(HRFlowable(width="40%", thickness=1, color=NOIR, hAlign="CENTER"))
    story.append(sp(5))
    story.append(Paragraph("SOCIAL MEDIA", styles["cv_title"]))
    story.append(Paragraph("STRATEGY", styles["cv_title2"]))
    story.append(sp(3))
    story.append(Paragraph("April 2026", styles["cv_sub"]))
    story.append(sp(5))
    story.append(HRFlowable(width="40%", thickness=1, color=NOIR, hAlign="CENTER"))
    story.append(sp(8))

    story.append(StatCard([
        ("127K",  "Ali — YouTube"),
        ("34K",   "Ali — Facebook"),
        ("$15K",  "Monthly Revenue"),
        ("6",     "Properties"),
    ], bg=WARM_WHITE, accent=NOIR))

    story.append(sp(8))

    story.append(AlertStrip(
        "URGENT — @aliimperiale YouTube is ONE STRIKE from permanent termination.",
        bar_color=NOIR, bg=colors.HexColor("#F0F0F0"),
        text_color=NOIR
    ))
    story.append(sp(8))

    # Property index — two columns
    humans  = ["Ali Imperiale", "Olives Travel by Ali Imperiale", "Gab's Adventures"]
    brands  = ["The Nookie Nook  ·  by Ali Imperiale",
               "La Casita Hedonista  ·  by Ali Imperiale",
               "GAB News"]

    col_w = [CONTENT_W * 0.5] * 2
    def col_block(cat, items):
        out = [Paragraph(cat, styles["cv_cat"])]
        for item in items:
            out.append(Paragraph(f"  ·  {item}", styles["cv_item"]))
        return out

    tdata = [[col_block("HUMANS", humans), col_block("BRANDS", brands)]]
    t = Table(tdata, colWidths=col_w)
    t.setStyle(TableStyle([
        ("VALIGN",      (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING",(0,0), (-1,-1), 4*mm),
        ("TOPPADDING",  (0,0), (-1,-1), 0),
    ]))
    story.append(t)


# ── Section helpers ───────────────────────────────────────────────────────────
def human_section(story, styles, name, sub, desc, rows, accent):
    story.append(sp(5))
    story.append(LeftBar(name, sub, bar_color=accent))
    story.append(sp(2))
    story.append(Paragraph(desc, styles["body"]))
    story.append(sp(2))
    story.append(platform_table(rows, accent))


def brand_section(story, styles, name, sub, desc, rows, accent):
    story.append(sp(5))
    story.append(LeftBar(name, sub, bar_color=accent))
    story.append(sp(2))
    story.append(Paragraph(desc, styles["body"]))
    story.append(sp(2))
    story.append(platform_table(rows, accent))


# ── Ali Imperiale ─────────────────────────────────────────────────────────────
def section_ali(story, styles):
    story.append(ChapterHeader(
        "HUMANS",
        "Personal brands — content driven by real people and real life",
        bg=ROSE, accent=GOLD_LIGHT
    ))
    story.append(sp(4))
    story.append(AlertStrip(
        "One strike away from YouTube termination — audience migration is the #1 priority now."
    ))
    story.append(sp(3))
    story.append(LeftBar("ALI IMPERIALE",
                         "127K YouTube  ·  34K Facebook  ·  $15K/month revenue",
                         bar_color=ROSE))
    story.append(sp(2))
    story.append(Paragraph(
        "YouTube is the primary Patreon driver (~$10K/month). Facebook brings ~$2K/month "
        "and is a distant second. The remaining ~$3K comes from other sources. "
        "The channel is one strike from permanent termination — every video should push viewers "
        "to subscribe elsewhere.",
        styles["body"]
    ))
    story.append(sp(2))
    rows = [
        ["YouTube",   "@aliimperiale — 127K",       "AT RISK — one strike from termination"],
        ["Patreon",   "patreon.com/cw/aliimperiale", "~$10K/month — YouTube is main driver"],
        ["Facebook",  "Ali Imperiale — 34K",         "~$2K/month — distant second"],
        ["Instagram", "@aliimperiale",               "Active — low conversion value"],
        ["TikTok",    "@aliimperiale",               "Slowly growing"],
        ["Website",   "aliimperiale.com",            "GitHub Pages — repo on Desktop"],
    ]
    story.append(platform_table(rows, ROSE))


def section_olives(story, styles):
    story.append(sp(5))
    story.append(LeftBar("OLIVES TRAVEL  by Ali Imperiale",
                         "Rebrand of @olivetrvl  ·  899 existing subscribers",
                         bar_color=ROSE))
    story.append(sp(2))
    story.append(Paragraph(
        "Repurposed footage from Gab's Adventures featuring Ali — biking, walking, travel. "
        "Already has <b>899 legit subscribers</b> under @olivetrvl. "
        "Rebrand rather than start from zero. Acts as a fallback audience net "
        "if @aliimperiale is terminated.",
        styles["body"]
    ))
    story.append(sp(2))
    rows = [
        ["YouTube",   "@olivetrvl — 899 subs", "Rebrand to 'Olives Travel by Ali Imperiale'"],
        ["Instagram", "TBD",                   "Reels from existing footage"],
        ["TikTok",    "TBD",                   "Short clips"],
    ]
    story.append(platform_table(rows, ROSE))


def section_gab(story, styles):
    story.append(sp(5))
    story.append(LeftBar("GAB'S ADVENTURES  ·  Gab à l'aventure",
                         "Adventure vlogs — bike, walk, travel",
                         bar_color=TEAL))
    story.append(sp(2))
    story.append(Paragraph(
        "Adventure vlogs — bike, walk, travel. Much of the footage features Ali, "
        "which is the source material for Olives Travel by Ali Imperiale.",
        styles["body"]
    ))
    story.append(sp(2))
    rows = [
        ["YouTube",    "Gab's Adventures — 1,100 subs", "Adventure vlogs, French"],
        ["Instagram",  "@gabrieldancause",               ""],
        ["X / Twitter","@Gabdancause",                   ""],
        ["TikTok",     "@gabrieldancause",               ""],
    ]
    story.append(platform_table(rows, TEAL))


# ── Brands ────────────────────────────────────────────────────────────────────
def section_brands(story, styles):
    story.append(sp(6))
    story.append(ChapterHeader(
        "BRANDS / PROGRAMMATIC",
        "Concept-driven · AI-assisted · Brand-first",
        bg=PLUM, accent=GOLD_LIGHT
    ))
    story.append(sp(4))

    story.append(LeftBar("THE NOOKIE NOOK  ·  by Ali Imperiale",
                         "Sex education news site  ·  thenookienook.com",
                         bar_color=PLUM))
    story.append(sp(2))
    story.append(Paragraph(
        "Sex education news site. Same AI engine as gab.ae — auto-publishes articles continuously. "
        "<b>'by Ali Imperiale'</b> is the hook — her name gives it instant credibility.",
        styles["body"]
    ))
    story.append(sp(2))
    rows = [
        ["Website",   "thenookienook.com", "News site — same engine as gab.ae"],
        ["YouTube",   "@TheNookieNook",    "Starting to get views"],
        ["Instagram", "@thenookienook",    "Active"],
    ]
    story.append(platform_table(rows, PLUM))

    story.append(sp(5))
    story.append(LeftBar("LA CASITA HEDONISTA  ·  by Ali Imperiale",
                         "Mexico property  ·  hedonist lifestyle concept",
                         bar_color=GOLD_DARK))
    story.append(sp(2))
    story.append(Paragraph(
        "Property in Mexico. Previously jungle camping — now pivoting to a "
        "<b>hedonist lifestyle concept</b> under Ali's brand. "
        "Sensual, adult, lifestyle — distinct from The Nookie Nook but the same brand family. "
        "The dormant <b>@gabandali channel (1,140 subs)</b> will be repurposed.",
        styles["body"]
    ))
    story.append(sp(2))
    rows = [
        ["YouTube",   "@gabandali — 1,140 subs",    "Repurpose dormant Gab & Ali channel"],
        ["Facebook",  "Mexico Jungle Camping (old)", "Old brand — pivot or replace"],
        ["Instagram", "TBD",                         "New account for hedonist rebrand"],
    ]
    story.append(platform_table(rows, GOLD_DARK))

    story.append(sp(5))
    story.append(LeftBar("GAB NEWS",
                         "AI-powered news site  ·  gab.ae  ·  publishes every 5 minutes",
                         bar_color=TEAL))
    story.append(sp(2))
    story.append(Paragraph(
        "AI-powered news engine with real traffic. Auto-generates news Shorts "
        "(built this week — good results). <b>Currently runs on local machine — needs to move to cloud.</b>",
        styles["body"]
    ))
    story.append(sp(2))
    rows = [
        ["Website",   "gab.ae",  "Has traffic"],
        ["YouTube",   "TBD",     "Create channel for auto-published Shorts"],
        ["TikTok",    "TBD",     ""],
        ["Instagram", "TBD",     ""],
        ["Facebook",  "TBD",     ""],
    ]
    story.append(platform_table(rows, TEAL))


# ── Action Items ──────────────────────────────────────────────────────────────
def section_actions(story, styles):
    story.append(sp(6))
    story.append(ChapterHeader("ACTION ITEMS", "Prioritized next steps", bg=DARK))
    story.append(sp(4))

    story.append(AlertStrip(
        "URGENT — Actively push @aliimperiale's 127K YouTube audience to backup channels before termination.",
    ))
    story.append(sp(2))
    story.append(AlertStrip(
        "URGENT — Rebrand @olivetrvl to 'Olives Travel by Ali Imperiale'. Link from main channel.",
    ))
    story.append(sp(3))

    items = [
        ("Move shorts pipeline to cloud",
         "Currently dies when laptop closes. Move to GitHub Actions, VPS, or Cloudflare Workers cron."),
        ("La Casita Hedonista",
         "Define brand direction. Repurpose @gabandali. Create Instagram. Pivot old Mexico Jungle Camping Facebook."),
        ("Create GAB News social accounts",
         "YouTube, TikTok, Instagram, Facebook — for the auto-Shorts pipeline."),
        ("Full content strategy",
         "Establish posting cadence and content direction for each active property."),
    ]
    for i, (title, detail) in enumerate(items, 1):
        story.append(Paragraph(
            f"<b>{i}.  {title}</b> — {detail}",
            styles["todo"]
        ))
        story.append(sp(1.5))


# ── Summary ───────────────────────────────────────────────────────────────────
def section_summary(story, styles):
    story.append(sp(5))
    story.append(LeftBar("SUMMARY", "All properties at a glance", bar_color=GOLD))
    story.append(sp(3))

    header = ["Property", "Category", "Key Asset", "Risk / Status"]
    rows = [
        ["Ali Imperiale",                "Human",       "127K YT · $15K/month",          "ONE STRIKE from termination"],
        ["Olives Travel by Ali Imperiale","Human",      "899 subs + existing footage",    "Needs rebrand"],
        ["Gab's Adventures",             "Human",       "Adventure YT + socials",         "Low growth"],
        ["The Nookie Nook",              "Brand",       "Growing YT + Instagram",          "Early stage"],
        ["La Casita Hedonista",          "Brand",       "Mexico property + @gabandali",   "Needs rebrand"],
        ["GAB News",                     "Programmatic","Traffic + auto-Shorts pipeline",  "Pipeline on local machine"],
    ]
    col_w = [CONTENT_W * x for x in [0.28, 0.14, 0.32, 0.26]]
    data = [header] + rows
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1,  0), NOIR),
        ("TEXTCOLOR",      (0, 0), (-1,  0), GOLD),
        ("FONTNAME",       (0, 0), (-1,  0), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 8),
        ("FONTNAME",       (0, 1), (-1, -1), "Helvetica"),
        ("TEXTCOLOR",      (0, 1), (-1, -1), NOIR),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, WARM_WHITE]),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ("LEFTPADDING",    (0, 0), (-1, -1), 5),
        ("LINEBELOW",      (0, 0), (-1, -1), 0.25, BORDER),
        # Danger highlight on Ali row
        ("TEXTCOLOR",      (3, 1), (3, 1), DANGER),
        ("FONTNAME",       (3, 1), (3, 1), "Helvetica-Bold"),
    ]))
    story.append(t)


# ── Build ─────────────────────────────────────────────────────────────────────
def build():
    out = "/Users/gab/Desktop/gab-ae/socials-strategy.pdf"

    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN + 4*mm, bottomMargin=12*mm,
        title="Social Media Strategy — Gab & Ali",
        author="Gab",
    )

    styles = make_styles()
    story = []

    cover_page(story, styles)
    story.append(PageBreak())

    section_ali(story, styles)
    section_olives(story, styles)
    section_gab(story, styles)

    section_brands(story, styles)
    section_actions(story, styles)
    section_summary(story, styles)

    doc.build(
        story,
        onFirstPage=draw_cover_bg,
        onLaterPages=draw_body_bg,
    )
    print(f"PDF written to: {out}")


if __name__ == "__main__":
    build()
