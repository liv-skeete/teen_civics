# TeenCivics v2 — Research Briefs

Compiled 2026-05-17 from background research agents. These are reference
material for v2 planning (design overhaul, Civi, social automation).
Treat each section as **opinionated input, not commitment** — pick what
fits, defer what doesn't, ignore what feels wrong.

---

## 1. UI / Design Direction — escaping the "AI-generated" look

### What reads as AI-generated in 2026

A skeptical viewer pattern-matches on a consistent fingerprint:

- Purple-to-indigo or blue-to-violet gradients on hero backgrounds and CTAs
  (the `from-indigo-500 to-purple-600` Tailwind UI lineage).
- **Inter** as body type (or Söhne, Geist, Poppins) — the single loudest
  "vibe-coded" signal.
- Glassmorphism / `backdrop-blur` cards floating on those gradients.
- `rounded-2xl` + `shadow-2xl` applied uniformly to every card, button, image.
- Sparkle ✨ emoji anywhere near "AI" mentions.
- Microcopy verbs: "Unlock," "Discover," "Supercharge," "Empower."
- Generic vector illustration packs: Storyset, unDraw, Lottie 3D blobs.
- Heroicons / Phosphor used decoratively, one per card heading.
- Faux-3D blob / mesh-gradient backgrounds.
- Slate-50 / zinc-100 surface + indigo-500 accent (default shadcn untouched).
- Symmetrical three-card feature rows with identical icon-headline-paragraph rhythm.
- Centered hero, 64px headline, 18px subhead, two CTAs (filled + ghost), emoji.

### What works for civic/young-audience editorial

Best-in-class references with what's worth stealing from each:

| Site | Visual move worth stealing |
|---|---|
| GOV.UK / GDS | Transport-derived sans, near-black on near-white, no decoration, content-first |
| USWDS / USAFacts | Restricted palette, charts as visual hero, slab-serif for trust |
| GovTrack | Tabular density, no illustration |
| Ballotpedia | Wiki-grade information density; visuals subordinated to facts |
| Pudding.cool | Editorial display serifs on plain backgrounds, scroll-driven graphics |
| NYT / WaPo / Politico interactives | Cheltenham/Imperial serifs, muted accent + one editorial red/blue |
| The Cut (Hearst) | Tight headline ladders, mixed serif+grotesque, asymmetric grids |
| Defector / Read Max / 404 Media | Personality-forward, chunky logo, two-color systems |
| 18by.vote / Run for Something | Editorial-poster look (bold flat color blocks) |
| iCivics | Illustrated, but owned illustration system — not unDraw |

**Pattern**: trust comes from typographic discipline, not chrome. Type does the
work; cards/shadows/gradients barely exist. TeenCivics should sit closer to
Pudding/Defector — opinionated, magazine-feeling — not gov.uk-austere.

### Recommendations, ranked impact-to-effort

[SURFACE] = 1-day fix · [SYSTEM] = design-token-level / multi-day

1. [SURFACE] **Strip the purple/blue gradient from every hero and CTA.**
   Gradients are the #1 AI tell.
2. [SURFACE] **Remove every sparkle, lightbulb, rocket emoji** from
   hero/CTA/Civi-intro copy.
3. [SYSTEM] **Replace Inter with a serif body** (Source Serif 4 or Newsreader at
   17–18px / 1.55) — the NYT/Defector/Pudding move.
4. [SURFACE] **Drop `rounded-2xl` and `shadow-2xl` on bill cards** for a 1px
   hairline border + zero shadow.
5. [SURFACE] **Rewrite hero microcopy off the "Unlock/Discover" axis** — declarative
   beats aspirational. "This week the House voted on 47 bills. Tell us what you
   think." beats "Discover civic engagement."
6. [SYSTEM] **Two-color system: one ink + one accent**, not the Tailwind default.
   Pick an owned accent (oxblood / ink blue / civic green).
7. [SURFACE] **Replace decorative icon-per-card with a single editorial device**
   (a numeral, a date stamp, or a section rule).
8. [SYSTEM] **Rebuild the bill card as a magazine item**: dateline + kicker +
   serif headline + dek + vote tally, on a hairline-ruled list.
9. [SURFACE] **Delete any generic vector illustration**. Replace with a single
   editorial mark (halftone Capitol photo, hand-drawn Civi, or nothing).
10. [SYSTEM] **Give Civi a typographic voice, not a chatbot UI** — pull-quote
    treatment, monospace tag ("CIVI →"), set in a different family from body.
    Like Genius annotations, not Intercom.
11. [SURFACE] **Tighten headline tracking to -0.02em, bump display size to
    56–80px** in a real display serif (GT Sectra Display, Fraunces, Newsreader Display).
12. [SYSTEM] **Build poll component as a newspaper graphic**: horizontal bar,
    percentage in display serif, n-count in small caps.
13. [SURFACE] **Swap pure #FFFFFF for newsprint off-white** (#FAFAF7) on all surfaces.
14. [SYSTEM] **Introduce a small-caps utility label style** (12px, +0.08em, all caps)
    for kickers, metadata, section eyebrows.
15. [SURFACE] **Cap border-radius at 4px globally**.
16. [SYSTEM] **Add real photography or risograph illustration** of Capitol scenes,
    visible grain — photographic specificity is the strongest anti-AI signal.

### Anti-patterns to avoid

- Purple / indigo / violet on hero or primary CTA
- Inter / Poppins / Geist / Söhne as body face
- Glassmorphism / backdrop-blur
- Sparkle / magic-wand / brain / rocket emoji in product copy
- Three identical feature cards with one icon each
- Generic 3D / isometric illustration (Storyset, unDraw, Lottie blobs)
- `shadow-2xl` and `rounded-2xl` defaults left untouched
- Aspirational verb-led headlines ("Unlock civic power")
- Pastel rainbow gradient on CTA buttons
- Centered hero with two side-by-side CTAs + emoji badge above H1

### Suggested opinionated system

**Type**
- Display: **Fraunces** (free, Google Fonts) at 64–88px, weight 600, optical size 144, `-0.02em` tracking
- Body: **Newsreader** (free, Google Fonts) at 17px / 1.55, weight 400
- UI / labels / data: **JetBrains Mono** at 11–12px, all caps, +0.08em tracking

**Palette**
- Ground: `#FAF7F0` (newsprint cream)
- Ink: `#111111` (near-black)
- Rule / hairline: `#D8D2C2`
- Muted text: `#5B564B`
- Accent (primary): `#1A3A5C` (deep ink-blue — civic, not patriotic-cliché)
- Action / vote: `#B5301F` (oxblood, used sparingly)
- Highlight: `#E8C547` (mustard, for poll bars and pull-quote underlines)

**Point of view**: TeenCivics looks like a young person's print quarterly that
happens to live on the web — Defector meets Pudding meets a civics zine. Cream
ground, sharp Fraunces headlines, Newsreader body, oxblood action color,
hairline rules instead of cards, mono labels, zero gradients, zero stock
illustration, one strong owned photograph or hand-drawn mark per feature. Civi
reads as a margin annotation in a different type family — not a chat widget.

---

## 2. Civi Video Pipeline — short-form video automation

### Recommendation

**Hedra Character-3 (avatar/lip-sync) + ElevenLabs (voice) + Submagic API
(captions/B-roll) + Claude (script).**

Hedra is the only tool that combines:
1. A documented Platform API (since Feb 2026)
2. Reusable character-image consistency for a recurring host
3. Stylized/non-human characters (Synthesia and HeyGen are stock-actor-shaped
   and political-content-restricted)
4. Hobby-tier pricing ($10–$30/mo) that holds at 1 video/day

### Why not HeyGen (which was the user's first guess)

- **ToS bans "political campaigning or lobbying"** — moderation aggressive,
  line fuzzy for legislative explainers. One incident from suspension.
- **Stock-actor aesthetic** — wrong vibe for "smart AP Gov friend" aimed at teens.
- **No native stylized/illustrated character animation.**
- **API scales ungenerously**: $1/min Avatar III, $5/min Avatar IV 4K — at
  20 videos/day of 45-sec, $225–$1,125/mo just on rendering vs Hedra Pro's $75 flat.

### Tool table (2026)

| Tool | Role | Hobby price | Political content |
|---|---|---|---|
| **Hedra Character-3** | Avatar/lip-sync, stylized characters | $10 Basic / $30 Creator / $75 Pro | AUP bans election interference + disinfo only — civic ed OK |
| **HeyGen** | Photoreal talking head | $24/mo Creator; API $1–$5/min | **Banned** for political campaigning/lobbying |
| **Synthesia** | Enterprise talking head | $29/mo Starter | **Banned** on Starter/Creator; enterprise-only |
| **D-ID** | Photo-to-talking-head, real-time API | $4.70/mo Lite | More permissive but photoreal only |
| **Runway Gen-4 Turbo** | B-roll, no avatar | $15/mo Standard, $0.05/sec API | No restrictions |
| **Sora 2 (OpenAI)** | Text-to-video, B-roll | $0.10–$0.50/sec | OpenAI moderation strict on political |
| **ElevenLabs** | Voice/TTS | $22 Creator / $99 Pro | No political restrictions |
| **Submagic** | Captions, B-roll, auto-zoom | $41/mo Business (API) | Direct-post to TikTok/IG/Shorts |

### Pipeline architecture

```
bill JSON + plain-English summary
   ↓
Claude (Anthropic API) — script + on-screen text + caption hooks
   ↓
ElevenLabs TTS — "Civi" voice (cloned/designed once, reused)
   ↓
Hedra Character-3 API — Civi portrait + audio → talking-head MP4 (9:16)
   ↓  [optional]
Runway Gen-4 Turbo — B-roll cutaways (Capitol, gavel)
   ↓
Submagic API — burn-in captions, auto-zoom, music bed
   ↓
Buffer / Metricool / native APIs — schedule to Reels, TikTok, Shorts
```

### Cost at cadence

| Cadence | Hedra | ElevenLabs | Submagic | Runway | Claude | **Total** |
|---|---|---|---|---|---|---|
| 1/day | $10 | $22 | $24 | $15 | ~$2 | **~$73/mo** |
| 5/day | $30 | $22 | $41 | $15 | ~$10 | **~$118/mo** |
| 20/day | $75 | $99 | $41+ | $35 | ~$40 | **~$290/mo** |

### Operational rule

**Never put a real legislator's likeness or voice into any generation pipeline.**
Stick to the Civi avatar plus B-roll of public buildings.

---

## 3. Civi Image Consistency + Bill Cards

### Recommendation

- **Civi character**: Bootstrap a 20-image Civi reference set in Midjourney v7
  (Omni Reference) or Flux 1.1 Pro, then run all production generations through
  **Nano Banana 2** (Gemini 3.1 Flash Image, `gemini-3.1-flash-image-preview`)
  with the canonical reference image + per-post scene prompt.
- **Bill cards**: **Do NOT use AI.** Render templated HTML/SVG with Playwright
  (or Satori + Resvg for serverless) → PNG at 1080×1080. AI fails the
  determinism and typography contract; HTML is free, pixel-perfect,
  version-controllable.

### Why Nano Banana 2 for Civi

Character consistency is its headline feature. The API accepts a reference
image directly. ~$0.07/image at 2K. No fine-tune to maintain, no LoRA
versioning, no GPU bills. Escalate to a Flux LoRA only if consistency drift
appears after a few hundred posts.

### Why HTML render (not AI) for bill cards

- Every AI model still misspells multi-word titles some fraction of the time
- Status badges must be pixel-identical across posts; AI cannot guarantee that
- Playwright + a React/HTML template = $0/image, <1s, unit-testable
- Brand mark stays vector-crisp
- Drop a pre-rendered Civi PNG into a corner slot

### Civi reference set recipe

1. Write a one-paragraph character bible: species/age, palette, clothing,
   line weight, vibe
2. Generate 20 images in Midjourney v7 (Omni Reference) or Flux 1.1 Pro:
   5 neutral portraits (front/3-4/profile/back/¾), 5 emotions, 5 poses,
   5 scene contexts
3. Pick the canonical "hero" image. Show the 20 to 3 people, ask "is this the
   same character?" Need ≥90% agreement
4. Use hero image as the persistent reference passed to Nano Banana on every
   generation. Re-evaluate consistency every 50 posts

### Cost

| Volume/day | Civi (Nano Banana 2) | Bill cards (HTML render) |
|---|---|---|
| 1/day | ~$2/mo | $0 |
| 5/day | ~$10/mo | $0 |
| 20/day | ~$40/mo | $0 (or ~$5 compute) |

Bootstrap reference set: ~$10 one-time (Midjourney Basic) or ~$2 (Replicate).

### Why not Qwen (user's other guess)

Qwen Image 2.0 is technically impressive (open weights, best-in-class
typography). But the API is invite-only on Alibaba Cloud BaiLian, latency from
the US is poor, and an Alibaba dependency for a US civic-ed brand is an
optics liability.

### Watch-outs

- Google AUP forbids political disinfo, deceptive content about
  elections/officials. **Civic education about bills is fine; do not generate
  fake quotes from real legislators.**
- OpenAI usage policy similarly bans deceptive political content
- Midjourney has no sanctioned public API in 2026 — every "Midjourney API" is
  a TOS violator. Use only for the one-time reference set via your account
- Flux dev weights are non-commercial; use Flux 1.1 Pro / Schnell / Kontext Pro
- Label AI-generated imagery on social posts (CA, TX state laws now require it
  for political-adjacent content)

---

## 4. Distribution Stack — social, newsletter, RSS

### Top-line recommendations

- **Newsletter**: **Beehiiv** (real REST API, free tier up to 2,500 subs, RSS-to-email
  built in)
- **Video Reels/Shorts/TikTok**: keep going direct-per-platform; add Instagram
  Graph (Reels) and YouTube Data API v3 first. Defer TikTok until after the
  Content Posting API audit (~2–6 weeks)
- **Cross-poster**: add **Postiz** (self-hosted, MIT, public API, 14 platforms
  incl. TikTok/IG/YouTube Shorts) only if direct-per-platform code becomes a
  maintenance burden. Buffer and Hootsuite are dead ends in 2026
- **RSS**: serve **RSS 2.0 + Atom self-link + media:thumbnail + dc:creator +
  content:encoded**, plus parallel **JSON Feed 1.1**

### Video upload APIs (2026)

| Platform | Audit needed? | Quota | Hobby-friendliness |
|---|---|---|---|
| YouTube Data API v3 (Shorts) | No (standard Google OAuth) | 10k units/day = ~6 uploads | **Best** |
| Instagram Graph (Reels) | No, but needs IG Business linked to FB Page | 25 published posts / 24h | Medium |
| TikTok Content Posting API | **Yes**, 2–6 week audit; unaudited = private posts only | 25 vids/24h post-audit | Hardest |

### Cross-poster comparison

| Service | 2026 API status | Hobby price | Verdict |
|---|---|---|---|
| Buffer | Public beta but **not accepting new third-party app registrations** | $6/channel/mo | Dead for new projects |
| Hootsuite | Partner-only API | n/a | Dead |
| Publer / Metricool / SocialPilot | API behind $20–$50/mo plans | not hobby-friendly | Skip |
| **Postiz** (OSS) | Full REST API + MCP, OAuth2 SDK | **Free, self-hosted** | **Pick if needed** |
| n8n / Make.com | Glue only; still need per-platform OAuth | Free self-host / $0–$10 hobby | Useful as orchestration |

### Newsletter platforms

| Platform | Real API? | Free tier | Portability |
|---|---|---|---|
| **Beehiiv** | **Yes**, REST + webhooks, posts:write + Send API | Free up to 2,500 subs | Full CSV/HTML export |
| Substack | **No write API in 2026** (read-only Developer API only); writes via brittle cookie-jar clients | Free + 10% rev share | Email export only |
| Ghost | Yes, mature Admin API | Self-host free; Pro $15–$29/mo + Mailgun | Best — you own it |
| Kit (ex-ConvertKit) | Yes, broad API | Free 10K subs | Good |
| Buttondown | API-first, formerly $9/mo gated, now free tier | Free 100 subs | Excellent (Markdown + Git) |

**Beehiiv** wins for TeenCivics: real `POST /publications/{id}/posts` with
scheduling, 2,500-sub free tier, full HTML export = portable. Ghost is purer
but $15–$29/mo + Mailgun overhead is wasted at hobby scale. Substack is
disqualified by lack of write API. Buttondown is the strong runner-up.

### RSS spec — recommended item shape

```xml
<item>
  <title>HR-1234 — Teen Civic Engagement Act</title>
  <link>https://teencivics.org/bills/hr-1234</link>
  <guid isPermaLink="false">teencivics:bill:hr-1234-119</guid>
  <pubDate>Sat, 17 May 2026 14:00:00 +0000</pubDate>
  <description>Plain-text 1–2 sentence teen summary…</description>
  <content:encoded><![CDATA[ full HTML summary ]]></content:encoded>
  <dc:creator>TeenCivics</dc:creator>
  <category domain="bill-status">passed-house</category>
  <category domain="chamber">house</category>
  <category domain="topic">education</category>
  <media:thumbnail url="https://teencivics.org/img/hr-1234.png" width="1200" height="630"/>
  <tc:billId>hr-1234-119</tc:billId>
  <tc:congress>119</tc:congress>
  <tc:status>passed-house</tc:status>
  <tc:voteFor>234</tc:voteFor>
  <tc:voteAgainst>198</tc:voteAgainst>
</item>
```

Namespaces: `xmlns:content`, `xmlns:dc`, `xmlns:media`, plus custom
`xmlns:tc="https://teencivics.org/ns/rss"` for bill-specific fields.
Include `<atom:link rel="self">` per RSS Best Practices Profile.

Mirror at `/feed.json` as JSON Feed 1.1.

### RSS → social pipelines

IFTTT (free tier still works for X), Make.com, n8n's "RSS Feed Trigger" →
Postiz / direct publisher nodes. Cheapest "newsletter → Twitter" pipeline =
RSS feed + n8n cron.

### Watch-outs

- **TikTok** community guidelines actively suppress unlabeled political
  content; civic-ed framing should be safe but expect reduced reach and
  possible "ineligible for FYP" flagging
- **Meta (IG/Facebook)** ads policy doesn't apply to organic posts, but
  accounts publishing legislative content occasionally trip automated political
  classifier; may need to complete Meta's Political Issue verification for the FB Page
- **Buffer / Hootsuite / SocialPilot** all require paid tiers for API access;
  Buffer additionally stopped accepting new third-party developer apps
- **Substack** "API" workflows depend on cookie auth and can break without notice
- **Ghost self-host**: Mailgun Flex (pay-as-you-go) was discontinued Dec 2025;
  budget for Mailgun Foundation tier

---

## Quick "what would I build first" v2 roadmap

If I were sequencing v2 across these four areas, ranked by leverage:

1. **Design system overhaul** (1) — biggest visual leverage, blocks the "looks
   AI-generated" criticism. Do on localhost behind a flag; ship when olivia approves.
2. **Bill cards via HTML render** (3) — unblocks Instagram/TikTok image posting,
   sets up the visual brand mark, doesn't need AI.
3. **Beehiiv newsletter + RSS feed** (4) — the cheapest distribution wins.
   `weekly_digest.py` already exists; this is wiring.
4. **Civi character image system** (3) — Nano Banana 2 with a hero reference.
   Needed before video pipeline because Civi's visual identity has to be locked
   first.
5. **Hedra video pipeline** (2) — last because it depends on (4) for Civi's
   look and (1) for brand identity.
6. **TikTok audit submission** in parallel with (5) since it takes 2–6 weeks.

---

*Sources: research agents 2026-05-17. All pricing and policy citations
verifiable against vendor docs as of that date.*
