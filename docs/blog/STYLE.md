# JunoGuard blog house style — citations & figures

## Citations: Chicago 17 (notes and bibliography)

Use the **notes and bibliography** system from *The Chicago Manual of Style*, 17th edition (often labeled `chicago17b` / `chicago-notes-bibliography` in CSL).

### In-body

- Prefer superscript endnotes (`[^n]` in Markdown) at the end of the clause that carries the claim.
- First citation: full note. Later citations of the same work: short form (author last name, shortened title, locator if needed).
- Do not invent page numbers, download counts, or ASR percentages. If a paper reports a figure, quote it and cite the paper.

### Bibliography

- Alphabetical by author (or title if no author).
- Corporate authors allowed (CISA, NIST, Modal Labs, HeySalad).
- Web pages with no publication date: use “Accessed Month Day, Year.”
- Include stable URLs; prefer NVD/GHSA/CISA/vendor advisory over secondary blogs for CVE claims.
- Same-author successive entries: use 3-em dash (`———.`).

### CSL (optional CMS tooling)

```yaml
# citation-style: chicago-notes-bibliography (CMOS 17)
# locale: en-US
```

### Do not cite as primary

- Secondary roundups that paraphrase Helicone status, competitor pricing, or attack counts without linking the primary.
- Internal product intent not yet shipping (e.g. £1 lifetime checkout) — mark as conditional in prose, do not footnote as fact.

---

## Figures & illustrations

### Visual system

- Off-white ground (`#F7F5F0`), charcoal ink (`#1A1A1A`), one muted teal accent (`#2F6F6A`).
- Flat, Swiss-clear, diagrammatic. No gradients, glow, purple, emoji, paper grain, or multi-layer shadows.
- Every figure needs: filename, Markdown image, bold **Figure N.** caption, alt text in the `![...]()`.

### Image QA gate (reject and regenerate if any fail)

- [ ] Palette matches the three tokens above (no forest-green drift, no multi-color outcome row)
- [ ] ALLOW / FLAG / BLOCK are visually distinct (teal check · caution · solid block) — never all green
- [ ] Product strings match demo truth (`@ossprey/test-package`, Ossprey verdict line, real credential *names*)
- [ ] Agent names are text-only (Cursor · Claude Code · Codex) — no trademark logos
- [ ] No duplicate stamps / redundant “BLOCKED” chrome
- [ ] Spelling clean; even column alignment; solid background (no texture)

### Standard figure set (reuse across posts)

| Asset | Use in |
|---|---|
| `assets/jg-blast-radius.png` | Problem / JTBD posts |
| `assets/jg-dual-lane.png` | Architecture / value posts |
| `assets/jg-refusal-panel.png` | Proof / demo posts |
| `assets/jg-install-path.png` | Install-path posts |

### Per-title illustration plan

| # | Title angle | Figures |
|---|---|---|
| 1 | Problem / blast radius | Figs 1–4 (shipped) |
| 2 | Job to be done | Blast radius + dual-lane |
| 3 | Value (time/money/credentials) | Blast radius + spend lane callout |
| 4 | Proof / demo story | Refusal panel + dual-lane + optional screenshot of live feed |
| 5 | Install path | Install-path + terminal screenshot |
| 6 | Honest limits | Dual-lane with “bypass” dashed path annotation (new) |
| 7 | No LLM on hot path | Dual-lane with “0 LLM” stamp on decision node (new) |
| 8 | MCP / tools.lock | New: tool-metadata → model trust diagram + lockfile hash strip |

### Screenshots (when available)

Prefer real product UI over mock chrome. Redact project keys. Caption with date and environment (`mock` vs live).

---

## Checklist before publish

- [ ] Every external factual claim has a note
- [ ] Bibliography complete and alphabetized
- [ ] Figures have captions and alt text
- [ ] No poetry/uv gating, anomaly ML, or default project keys claimed
- [ ] CTAs: junoguard.com + `npx @heysalad/junoguard init`
