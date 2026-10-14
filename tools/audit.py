#!/usr/bin/env python3
"""Audit a bilingual course manual for internal consistency.

    python tools/audit.py            # audit the repo, print a report
    python tools/audit.py --quiet    # only print failures

Seven passes, ordered by how expensive the mistake is to find late:

  1  HTML validity      unclosed or mismatched tags in any page
  2  Links              every href="#…" resolves to an id, and every local
                        page-to-page link points at a file that exists
  3  Fact parity        the two language editions agree on section numbers,
                        identifiers, cross-references, level tags, stage numbers
                        and figure numbers — everything that names one reality
  4  Structural parity  a chapter with five table rows in one language and four
                        in the other is missing a row somewhere
  5  Identifier sweep   no source-language folder, file, column or value names
                        survive where they should be English (prose is fine —
                        only identifiers are checked)
  6  Cross-file         a value the manual quotes is byte-identical to the file
                        the reader downloads, and all copies of a file tree list
                        the same directories
  7  Level bands        data-level blocks are paired FR/EN, so a band hides the
                        same content in both editions

Exit code is the number of failing passes, so this works in CI unchanged.
Standard library only — no install step, runs in a couple of seconds.

────────────────────────────────────────────────────────────────────────────────
ADAPTING THIS TO A NEW COURSE
Everything course-specific lives in CONFIG below. Set the file names, then:
  · leave `bands` empty if the course has a single audience (pass 7 skips)
  · leave `template_root` None if there is no downloadable folder
  · `paired` is the general form of "the manual quotes something that also
    exists as a real file" — add one entry per such value
  · `banned_anywhere` / `banned_in_code` start empty. Fill them the first time
    you rename an identifier: add the OLD name, and the audit guarantees it
    never creeps back.
Prefer fixing the tool over contorting the prose when a check false-positives.
────────────────────────────────────────────────────────────────────────────────
"""
import io
import os
import re
import sys
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG = {
    # The manual itself — the file passes 3, 4, 6 and 7 read.
    "manual": "splatting_manuel-v1.html",

    # Every HTML page in the repo. Passes 1 and 2 read all of them.
    "pages": ["splatting_manuel-v1.html", "outils.html", "index.html"],

    # Extra text files the identifier sweep should also read (Markdown, CSV…).
    "also_sweep": ["README.md"],

    # Downloadable starter folder, relative to ROOT. None if the course has none.
    "template_root": None,

    # Cumulative level bands: data-level value → what it means. {} disables pass 7.
    # Keep it to two: a third band is a second manual pretending to be one.
    "bands": {},

    # Section ids that count as cross-references for parity. Widen as you add
    # reference sections.
    "xref_ids": r"ch\d+|faq|glossary|how",

    # Identifiers renamed at some point, which must never come back.
    # Distinctive enough that they cannot occur in ordinary prose:
    "banned_anywhere": [],
    # Column names and values that ARE ordinary words in the source language.
    # Only checked inside identifier-shaped strings, never in prose:
    "banned_in_code": [],

    # "The manual quotes this, and it is also a real file the reader downloads."
    #   find  — regex matching the canonical text inside the manual
    #   file  — the file that must agree, relative to ROOT
    #   lines — "first" compares the file's first line, "all" the whole file
    "paired": [],

    # Regex matching each copy of a file tree (one per language edition).
    # The directory sets must be identical. None disables the check.
    "tree": None,
}

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr", "circle", "ellipse", "line", "path",
        "polygon", "polyline", "rect", "use", "stop"}

QUIET = "--quiet" in sys.argv
FAILURES = []


def say(msg=""):
    if not QUIET:
        print(msg)


def fail(pass_name, detail):
    FAILURES.append(pass_name)
    print("  FAIL  " + detail)


def ok(detail):
    say("  ok    " + detail)


def rd(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace").read()


# ─────────────────────────────── language filter ───────────────────────────────

class LangFilter(HTMLParser):
    """Re-emit the document with every element carrying `drop` (and its subtree) gone.

    Regex cannot do this: the language wrappers nest, and a subtree has to leave
    with its parent. This is what makes it possible to audit each edition as if
    it were a separate document.
    """

    def __init__(self, drop):
        super().__init__(convert_charrefs=False)
        self.drop, self.out, self.skip = drop, [], 0

    def handle_starttag(self, tag, attrs):
        dropping = self.drop in (dict(attrs).get("class") or "").split()
        if self.skip:
            if tag not in VOID:
                self.skip += 1
            return
        if dropping:
            if tag not in VOID:
                self.skip = 1
            return
        self.out.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        if not self.skip and self.drop not in (dict(attrs).get("class") or "").split():
            self.out.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if self.skip:
            self.skip -= 1
            return
        self.out.append("</%s>" % tag)

    def handle_data(self, d):
        if not self.skip:
            self.out.append(d)

    def handle_entityref(self, n):
        if not self.skip:
            self.out.append("&%s;" % n)

    def handle_charref(self, n):
        if not self.skip:
            self.out.append("&#%s;" % n)


def view(html, keep):
    """The document as one language sees it. keep is "fr" or "en"."""
    p = LangFilter("en-only" if keep == "fr" else "fr-only")
    p.feed(html)
    return "".join(p.out)


def sections(html):
    return {m.group(1): m.group(2) for m in
            re.finditer(r'<section class="chap" id="([^"]+)"(.*?)</section>', html, re.S)}


# ───────────────────────────── 1 · HTML validity ─────────────────────────────

class Balance(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.err = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.err.append("line %d: stray </%s>" % (self.getpos()[0], tag))
        elif self.stack[-1][0] == tag:
            self.stack.pop()
        else:
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    unclosed = ["<%s> @%d" % x for x in self.stack[i + 1:]]
                    self.err.append("line %d: </%s> but unclosed %s"
                                    % (self.getpos()[0], tag, unclosed))
                    del self.stack[i:]
                    break
            else:
                self.err.append("line %d: </%s> never opened" % (self.getpos()[0], tag))


def pass_html():
    say("1 · HTML validity")
    for rel in CONFIG["pages"]:
        if not os.path.exists(os.path.join(ROOT, rel)):
            continue
        b = Balance()
        b.feed(rd(rel))
        if b.err or b.stack:
            fail("html", "%s: %s %s" % (rel, b.err[:3], [x[0] for x in b.stack]))
        else:
            ok("%-34s balanced" % rel)


# ─────────────────────────────── 2 · links ───────────────────────────────

def pass_links():
    say("\n2 · Links")
    for rel in CONFIG["pages"]:
        if not os.path.exists(os.path.join(ROOT, rel)):
            continue
        t = rd(rel)
        ids = set(re.findall(r'\bid="([^"]+)"', t))
        # skip hrefs built inside JS string concatenation
        hrefs = {h for h in re.findall(r'href="#([^"]+)"', t) if "'" not in h and "+" not in h}
        bad = sorted(hrefs - ids)
        if bad:
            fail("links", "%s: dangling anchor %s" % (rel, bad))

        # local page-to-page links: the file has to be there
        local = {h.split("#")[0] for h in re.findall(r'href="([^"#][^"]*)"', t)
                 if not re.match(r"https?:|mailto:|//", h)}
        missing = sorted(f for f in local if f and not os.path.exists(os.path.join(ROOT, f)))
        if missing:
            fail("links", "%s: links to missing file(s) %s" % (rel, missing))

        if not bad and not missing:
            ok("%-34s %d anchors + %d page links resolve" % (rel, len(hrefs), len(local)))


# ───────────────────────────── 3 · fact parity ─────────────────────────────

def facts(block):
    """Everything in a chapter that names one reality and must therefore match."""
    return {
        "sections": sorted(set(re.findall(r"<h3[^>]*>\s*(\d+\.\d+)", block))),
        "code": sorted({re.sub(r"\s+", " ", c).strip()
                        for c in re.findall(r"<code[^>]*>(.*?)</code>", block, re.S)
                        if re.search(r"[/._]|^[a-z_]+$", re.sub(r"<[^>]+>", "", c))}),
        "xref": sorted(set(re.findall(r'href="#(%s)"' % CONFIG["xref_ids"], block))),
        "tags": sorted(re.findall(r'lv-tag">([^<]+)<', block)),
        "stages": sorted(set(re.findall(
            r'class="hd">\s*(?:Étape|Stage|Step)\s*(\d+)', block))),
        "figs": sorted(set(re.findall(r"(?:Fig|Figure)\s*(\d+(?:\.\d+)?)", block))),
    }


def pass_fact_parity(fr, en):
    say("\n3 · Fact parity between editions")
    bad = 0
    for k in [x for x in fr if x in en]:
        f, e = facts(fr[k]), facts(en[k])
        for field in ("sections", "stages", "figs", "tags", "xref", "code"):
            only_fr = [x for x in f[field] if x not in e[field]]
            only_en = [x for x in e[field] if x not in f[field]]
            if only_fr or only_en:
                bad += 1
                fail("fact-parity", "[%s] %s  FR-only %s  EN-only %s"
                     % (k, field, only_fr or "-", only_en or "-"))
    if not bad:
        ok("%d sections agree on every identifier and number" % len(fr))


# ──────────────────────────── 4 · structural parity ────────────────────────────

def counts(b):
    pat = {"tables": r"<table", "rows": r"<tr", "callouts": r'class="callout',
           "prompts": r'class="pr"', "h3": r"<h3", "h4": r"<h4", "li": r"<li",
           "pre": r"<pre", "exercises": r'class="exercise"', "faq": r'details class="faq"'}
    return {k: len(re.findall(v, b)) for k, v in pat.items()}


def pass_structural_parity(fr, en):
    say("\n4 · Structural parity between editions")
    bad = 0
    for k in [x for x in fr if x in en]:
        cf, ce = counts(fr[k]), counts(en[k])
        diff = {f: (cf[f], ce[f]) for f in cf if cf[f] != ce[f]}
        if diff:
            bad += 1
            fail("structure", "[%s] %s" % (k, ", ".join(
                "%s FR%d/EN%d" % (f, a, b) for f, (a, b) in sorted(diff.items()))))
    if not bad:
        ok("%d sections have matching structure" % len(fr))


# ───────────────────────────── 5 · identifier sweep ─────────────────────────────

def literals(t):
    """Strings from a document that are *identifiers* rather than prose.

    Prompt blocks and body text are full of ordinary sentences, so a naive scan
    would flag every one of them. Only three shapes count as an identifier: an
    inline code span holding a single token, a backticked single token in
    Markdown, and a line of a file tree or a CSV row.
    """
    out = []
    for c in re.findall(r"<code[^>]*>(.*?)</code>", t, re.S):
        c = re.sub(r"<[^>]+>", "", c).strip()
        if c and " " not in c:
            out.append(c)
    for c in re.findall(r"`([^`\n]+)`", t):
        c = c.strip()
        if c and " " not in c:
            out.append(c)
    blocks = re.findall(r"<pre[^>]*>(.*?)</pre>", t, re.S) or [t]
    for blk in blocks:
        # A tree line is "path  <span class=cm>comment</span>", and that comment
        # is deliberately prose in the source language. Only the path counts as an
        # identifier, so drop the comment first. Nothing is lost: real file and
        # folder names are caught by banned_anywhere, which scans everything.
        blk = re.sub(r'<span class="cm">.*?</span>', "", blk, flags=re.S)
        for line in re.sub(r"<[^>]+>", "", blk).splitlines():
            s = line.strip()
            if any(g in line for g in ("├──", "└──", "│")) \
               or re.match(r"^[a-z_]+(,[a-z_]+){3,}", s) \
               or re.match(r"^[A-Z]\d\d,", s):
                out.append(line)
    return out


def pass_sweep():
    say("\n5 · Identifiers")
    if not CONFIG["banned_anywhere"] and not CONFIG["banned_in_code"]:
        ok("nothing banned yet — add renamed identifiers to CONFIG as you go")
        return
    scan = [os.path.join(ROOT, p) for p in CONFIG["pages"] + CONFIG["also_sweep"]]
    if CONFIG["template_root"]:
        for base, _, names in os.walk(os.path.join(ROOT, CONFIG["template_root"])):
            scan += [os.path.join(base, n) for n in names if n != ".gitkeep"]
    hits = 0
    for p in sorted(set(scan)):
        if not os.path.isfile(p):
            continue
        t = io.open(p, encoding="utf-8", errors="replace").read()
        rel = os.path.relpath(p, ROOT)
        for term in CONFIG["banned_anywhere"]:
            if term in t:
                fail("sweep", "%s: %r (%dx)" % (rel, term, t.count(term)))
                hits += 1
        for term in CONFIG["banned_in_code"]:
            where = [s for s in literals(t)
                     if re.search(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])", s)]
            if where:
                fail("sweep", "%s: %r used as an identifier — %s"
                     % (rel, term, where[0][:60]))
                hits += 1
    if not hits:
        ok("no renamed identifier has crept back")


# ───────────────────────────── 6 · cross-file ─────────────────────────────

def pass_crossfile(manual):
    say("\n6 · Manual vs downloadable files")
    checked = False

    for spec in CONFIG["paired"]:
        checked = True
        path = os.path.join(ROOT, spec["file"])
        if not os.path.exists(path):
            fail("crossfile", "missing file: %s" % spec["file"])
            continue
        content = io.open(path, encoding="utf-8").read()
        want = content.splitlines()[0].strip() if spec.get("lines") == "first" \
            else content.strip()
        found = re.findall(spec["find"], manual)
        if not found:
            fail("crossfile", "%s: the manual never quotes it" % spec["file"])
        elif found[0].strip() != want:
            fail("crossfile", "%s differs\n          manual %s\n          file   %s"
                 % (spec["file"], found[0].strip()[:90], want[:90]))
        else:
            ok("%s matches the manual" % spec["file"])

    if CONFIG["tree"]:
        checked = True
        trees = re.findall(CONFIG["tree"], manual, re.S)
        dirsets = [tuple(sorted(set(re.findall(r"\b[\w.-]+/", t)))) for t in trees]
        if not trees:
            fail("crossfile", "no file tree matched CONFIG['tree']")
        elif len(set(dirsets)) > 1:
            only = set(dirsets[0]) ^ set(dirsets[1])
            fail("crossfile", "the editions' trees differ: %s" % sorted(only))
        else:
            ok("all %d copies of the tree list the same %d directories"
               % (len(trees), len(dirsets[0])))

    if not checked:
        ok("nothing paired — add entries to CONFIG['paired'] when the manual "
           "starts quoting a downloadable file")


# ───────────────────────────── 7 · level bands ─────────────────────────────

def pass_bands(manual):
    say("\n7 · Level bands")
    if not CONFIG["bands"]:
        ok("single audience — no bands to check")
        return
    for lvl in CONFIG["bands"]:
        fr = en = 0
        for m in re.finditer(r'<div data-level="%s">' % lvl, manual):
            # Which language wrapper is this block sitting inside? Walk the div
            # stack from the top of the file: the innermost fr-only/en-only wins.
            stack = []
            for d in re.finditer(r"<div\b([^>]*)>|</div>", manual[:m.start()]):
                if d.group(0) == "</div>":
                    if stack:
                        stack.pop()
                else:
                    a = d.group(1) or ""
                    stack.append("fr" if 'class="fr-only"' in a
                                 else "en" if 'class="en-only"' in a else ".")
            langs = [x for x in stack if x in ("fr", "en")]
            cur = langs[-1] if langs else None
            if cur == "fr":
                fr += 1
            elif cur == "en":
                en += 1
            else:
                fail("bands", 'data-level="%s" block sits outside any language wrapper' % lvl)
        if fr != en:
            fail("bands", 'data-level="%s" unbalanced: FR %d, EN %d' % (lvl, fr, en))
        else:
            ok('data-level="%s"  FR %d = EN %d' % (lvl, fr, en))


# ─────────────────────────────────── main ───────────────────────────────────

def main():
    mpath = os.path.join(ROOT, CONFIG["manual"])
    if not os.path.exists(mpath):
        sys.exit("manual not found: %s\nSet CONFIG['manual'] in %s"
                 % (mpath, os.path.basename(__file__)))
    manual = rd(CONFIG["manual"])
    fr, en = sections(view(manual, "fr")), sections(view(manual, "en"))

    say("AUDIT · %s" % CONFIG["manual"])
    say("%d KB · %d sections\n" % (len(manual.encode()) // 1024, len(fr)))

    if not fr or not en:
        fail("setup", "no <section class=\"chap\" id=\"…\"> found in one edition — "
                      "check the wrapper classes")

    pass_html()
    pass_links()
    pass_fact_parity(fr, en)
    pass_structural_parity(fr, en)
    pass_sweep()
    pass_crossfile(manual)
    pass_bands(manual)

    distinct = sorted(set(FAILURES))
    print()
    if distinct:
        print("AUDIT FAILED · %d problem(s) across %d pass(es): %s"
              % (len(FAILURES), len(distinct), ", ".join(distinct)))
    else:
        print("AUDIT PASSED · 7 passes, no problems")
    sys.exit(len(distinct))


# Guarded so the passes can be imported and reused by other scripts without the
# whole audit running as a side effect of the import.
if __name__ == "__main__":
    main()
