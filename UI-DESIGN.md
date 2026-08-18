# Sluice UI — Style Reference

> obsidian monolith in candlelight — a near-black canvas where a single warm
> champagne accent cuts like a blade through the darkness

**Theme:** dark only. There is no light mode, and adding one breaks the
system — the whole language depends on cream-on-black value contrast.

This document describes the interface built for **Sluice Transfer** (a macOS
Mac↔Android file transfer app). It's derived from the `DESIGN.md` brand sheet
but translated from *website* to *application chrome*: dense listings,
toolbars, progress, empty states — the things a marketing page never has.

Hand this to an agent building a different app and it should produce something
that looks like it shipped from the same studio. Tokens are given in CSS
custom properties and SwiftUI side by side; the numbers are the contract, the
syntax is not.

---

## 1. The one-paragraph brief

Near-total monochrome discipline. Pure black canvases carry warm cream type
and a single champagne accent. Color is never decoration — the palette is
cream for text, gold for emphasis, black for depth, and nothing else.
Surfaces are defined by **1px hairlines, never shadows**, which makes
everything feel cut from one sheet of machined material rather than stacked
in layers. Layout is compact, typographic, and grid-driven. Every element
reads as *placed*, not animated.

---

## 2. Color

| Name | Value | Role |
|------|-------|------|
| Obsidian Black | `#000000` | Every surface. Canvas, cards, toolbars, rows — all the same black. |
| Candlelight Cream | `#FFF7DD` | All primary text, icon strokes, hairline borders. |
| Champagne Gold | `#C8AD86` | The only chromatic color. Accent, emphasis, active state, progress fill. |
| Ember Ash | `#66635F` | Muted fill for the rare secondary zone. Used sparingly. |

Everything else is one of those four at reduced opacity:

| Token | Value | Used for |
|-------|-------|----------|
| `--text-primary` | cream 100% | File names, headings, values |
| `--text-secondary` | cream 62% | Supporting text, inactive breadcrumb segments |
| `--text-faint` | cream 34% | Sizes, timestamps, column headers, hints |
| `--hairline` | cream 20% | Default border between everything |
| `--hairline-bright` | cream 34% | Border needing slightly more presence |
| `--gold-line` | gold 65% | Accent border: hover, focus, drop target |
| `--fill-selected` | gold 13% | Selected row wash |
| `--fill-hover` | cream 5.5% | Hover row wash |
| `--fill-drop` | gold 7% | Active drag-and-drop target |

**The rule that keeps this coherent:** gold is never a surface. It appears as
1px strokes, 10px text, small glyphs, and a 2px progress fill. The moment a
button gets a solid gold background, the system reads as a different brand.

```css
:root {
  --color-black:  #000000;
  --color-cream:  #fff7dd;
  --color-gold:   #c8ad86;
  --color-ash:    #66635f;

  --text-primary:     rgb(255 247 221 / 1);
  --text-secondary:   rgb(255 247 221 / 0.62);
  --text-faint:       rgb(255 247 221 / 0.34);
  --hairline:         rgb(255 247 221 / 0.20);
  --hairline-bright:  rgb(255 247 221 / 0.34);
  --gold-line:        rgb(200 173 134 / 0.65);
  --fill-selected:    rgb(200 173 134 / 0.13);
  --fill-hover:       rgb(255 247 221 / 0.055);
  --fill-drop:        rgb(200 173 134 / 0.07);
}
```

```swift
enum Theme {
    static let canvas = Color(hex: 0x000000)
    static let cream  = Color(hex: 0xFFF7DD)
    static let gold   = Color(hex: 0xC8AD86)
    static let ash    = Color(hex: 0x66635F)

    static let textPrimary   = cream
    static let textSecondary = cream.opacity(0.62)
    static let textFaint     = cream.opacity(0.34)
    static let hairline      = cream.opacity(0.20)
    static let goldLine      = gold.opacity(0.65)
    static let selectedFill  = gold.opacity(0.13)
    static let hoverFill     = cream.opacity(0.055)
    static let dropFill      = gold.opacity(0.07)
}
```

---

## 3. Typography

**Switzer**, a geometric sans with tight tracking. Substitutes, in order:
Inter → General Sans → Satoshi → system sans. Only weights **400** and **500**
exist in this system; there is no bold.

| Style | Size | Weight | Tracking | Used for |
|-------|------|--------|----------|----------|
| `display` | 44px | 400 | −1.85px | Hero statement in empty states only |
| `title` | 16px | 500 | −0.5px | App wordmark, section titles |
| `body` | 14px | 400 | 0 | File names, primary content |
| `small` | 12px | 400 | 0 | Paths, device names, supporting text |
| `caption` | 10px | 500 | +0.18px | **Uppercased.** Labels, pills, buttons, column headers |

Two rules do most of the work:

1. **Negative tracking above 16px, positive below 12px.** Display type
   tightens into compact machined forms; caption type opens up so 10px
   uppercase stays legible.
2. **Never letter-space body text.** 14px content is set at 0.

`caption` is the workhorse of application chrome. Every button label, every
tag, every column header is 10px/500 uppercase with +0.18 tracking. That one
choice is most of what makes the UI look designed rather than assembled.

Numeric columns (sizes, timestamps, percentages) use **tabular figures**
(`font-variant-numeric: tabular-nums` / `.monospacedDigit()`) so digits don't
jitter as values change.

```swift
struct TypeStyle {
    let size: CGFloat; let weight: Font.Weight; let tracking: CGFloat
    static let display = TypeStyle(size: 44, weight: .regular, tracking: -1.85)
    static let title   = TypeStyle(size: 16, weight: .medium,  tracking: -0.5)
    static let body    = TypeStyle(size: 14, weight: .regular, tracking: 0)
    static let small   = TypeStyle(size: 12, weight: .regular, tracking: 0)
    static let caption = TypeStyle(size: 10, weight: .medium,  tracking: 0.18)
}
```

---

## 4. Space and shape

Spacing scale: **4, 6, 8, 10, 16, 20, 24, 36, 40, 56, 80**. Density is
compact — 8–16px between related elements, 80px only between major sections
on a page (rare in an app).

| Element | Radius |
|---------|--------|
| Buttons, cards, inputs, panels | **4px** |
| Pills and tags | **100px** (fully rounded) |
| Everything else | 0 |

There is no 8px, 12px, or 16px radius anywhere. Rectangles are 4px; pills are
capsules; nothing is in between.

**Fixed heights** keep dense chrome on a rhythm:

| Element | Height |
|---------|--------|
| App header bar | 52px |
| Pane header | 40px |
| List row | 26px |
| Column header row | 22px |
| Action bar / footer | 52px |
| Status rail (idle) | 44px |
| Icon button | 22 × 22px |
| Progress bar | 2px |

---

## 5. Elevation — read this before drawing anything

**There are no shadows in this system. None. Not soft ones.**

Every boundary is a 1px hairline in cream 20%. A panel does not sit *above*
the canvas; it sits *beside* it, separated by a line. This is the single
easiest rule to break by accident, because most component libraries ship
shadows by default and most agents reach for `box-shadow` when asked to
"separate" two areas.

Also banned: blur/frosted-glass backdrops, glows, gradient fills on surfaces,
and any `background` on a card. Cards are `#000` on `#000`, defined purely by
their border.

Draw hairlines at true device-pixel width (`1px` CSS, or `1 / displayScale`
in SwiftUI) — a 1pt line on a Retina display straddles two pixels and reads
as a soft grey smudge, which is exactly the softness the system is avoiding.

---

## 6. Components

### 6.1 Tag pill
Fully rounded, 1px gold border, **transparent fill**, 10px/500 gold uppercase
at +0.18 tracking, padding `4px 10px`. Used for status ("ADB"), source labels
("THIS MAC"), and category marks.

Variant: cream border + cream text at 45–70% opacity for a secondary or
inactive pill.

### 6.2 Pill button (quick-jump chip)
Same geometry as the tag pill, but interactive. Three states:

| State | Border | Text |
|-------|--------|------|
| Rest | hairline (cream 20%) | cream 62% |
| Hover | gold 45% | gold |
| Active / current | gold 65% | gold |

### 6.3 Ghost button — the primary control
Flat, 4px radius, **1px border, no fill**, 10px/500 uppercase label, padding
`8px 16px`. Optional arrow glyph (`→` / `←`) before or after the label.

| State | Border | Text |
|-------|--------|------|
| Rest | cream 20% | cream |
| Rest, emphasized | gold 45% | gold |
| Hover | gold 65% | gold |
| Disabled | cream 10% | cream 34% |

There is no filled "primary" button. Emphasis is carried by gold stroke and
gold text — a solid CTA color is explicitly not part of this system.

### 6.4 Icon button
22 × 22px square, 4px radius, 1px hairline border, 10px glyph centered.
Cream at rest, gold on hover, gold when toggled on. Toggle state is carried by
the glyph color, not by a fill.

### 6.5 List row
26px tall. Left to right: 2px selection rule · 16px icon · name (`body`) ·
flexible gap · size (`small`, faint, tabular, right-aligned, 66px) ·
timestamp (`small`, faint, tabular, right-aligned, 120px).

| State | Treatment |
|-------|-----------|
| Rest | transparent |
| Hover | cream 5.5% wash |
| Selected | gold 13% wash **and** a 2px gold rule on the leading edge |

The leading rule is what makes selection readable at 13% opacity. Don't drop
it and raise the wash instead — a gold-filled row turns gold into a surface.

Icons: folders gold, files cream 62%. Never introduce a third color, and never
use multicolor system icon sets.

### 6.6 Column header
22px tall, 10px/500 uppercase. Faint by default; the active sort column turns
gold and gains a `↑` / `↓` glyph. Clicking re-sorts, clicking again flips.

### 6.7 Progress
A 2px bar. Track cream 12%, fill gold. No radius, no gradient, no stripe.
Percentage is shown as 10px gold tabular text beside it, not inside it.
For unknown-duration work, a 25%-width gold shuttle slides across on a 1.1s
ease loop — the one animation the system permits, because it's reporting
state rather than decorating.

### 6.8 Empty and error states
The only place `display` type appears. Vertically centered stack:

```
[ brand mark, 56px, gold 85% ]
[ 26px cream headline, tracking −1.0 ]
[ 12px secondary body, max-width 380px, 4px line spacing ]
[ optional ghost button ]
```

Write the body copy as **instructions, not diagnostics**. "Look for the
'Allow USB debugging?' prompt on its screen and accept it" — not "Device
state: unauthorized."

### 6.9 Header bar
52px tall, black, hairline along the bottom. Brand mark + wordmark
(`title`, uppercase) on the left, status pills on the right. On macOS, hide
the native title bar and reserve **82px** of leading padding so the header
draws behind the traffic lights without colliding with them.

---

## 7. Layout

Two-pane split with a full-height 1px vertical hairline between. Panes are
equal width, each `maxWidth: .infinity`, and internally identical:

```
┌──────────────────────────────────────────────────────────────┐
│ ▚ WORDMARK                              Android 16 ( ADB )   │ 52
├──────────────────────────────┬───────────────────────────────┤
│ (THIS MAC)  device name      │ (ANDROID)  device name        │ 40
│ ─────────────────────────────┼────────────────────────────── │
│ (pill)(pill)(pill)(pill)     │ (pill)(pill)(pill)            │
│ [↑]  ~ / Downloads    [◉][⟳] │ [↑] Internal storage  [◉][⟳]  │
│ ─────────────────────────────┼────────────────────────────── │
│ NAME ↑              SIZE  MODIFIED                            │ 22
│ ─────────────────────────────┼────────────────────────────── │
│ ▸ rows                       │ ▸ rows                        │
│ ─────────────────────────────┼────────────────────────────── │
│ [SELECT ALL] 16 items        │  [← COPY]  [SELECT ALL]       │ 52
├──────────────────────────────┴───────────────────────────────┤
│ → filename.zip                    64%  [CANCEL]              │
│ ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬───────────────────────────────────────  │
└──────────────────────────────────────────────────────────────┘
```

Mirror the transfer actions to the **inner edge** of each pane — left pane's
button on its right, right pane's on its left — so the two controls sit either
side of the divider and point across it. Symmetry here is the whole metaphor.

The status rail collapses to a single 44px hint row when idle. It never grows
into a panel that competes with the listings.

---

## 8. Motion

Effectively none. No entrance animations, no scale or position transitions,
no fades on load. Elements are placed.

Permitted:
- state color changes on hover (instant is fine, ≤120ms if eased)
- the indeterminate progress shuttle (§6.7)
- determinate progress advancing

Not permitted: animated page transitions, staggered list reveals, parallax,
spring physics, skeleton shimmer.

---

## 9. Iconography

Thin-stroke line icons only, drawn in cream or gold, never both in one glyph
and never a third color. On Apple platforms, SF Symbols at `.regular` weight,
10–11px in chrome and 11px in rows.

Arrows are typographic: use the literal glyphs `→` `←` `↑` `↓` inline with
text rather than icon components. They inherit color and optical size for
free, which is why the system leans on them so heavily.

The brand mark is a monochrome line redraw of the app icon, in gold. When an
app icon is a full-color gradient, **do not put the icon itself inside the
window** — redraw its motif as a single-color line mark. The palette allows
one chromatic color, and a gradient logo isn't it.

---

## 10. Do / Don't

**Do**
- Use `#FFF7DD` for all primary text and all hairlines
- Reserve `#C8AD86` for accents, active states, and 1px strokes
- Separate every region with a 1px hairline
- Set all chrome labels in 10px/500 uppercase at +0.18 tracking
- Keep rectangles at 4px radius and pills at 100px
- Use tabular figures in every numeric column
- Write empty-state copy as the next action to take

**Don't**
- Don't use shadows, glows, blurs, or frosted-glass backdrops — ever
- Don't use pure `#FFFFFF` for text; cream is warmer and on-brand
- Don't fill any surface with gold, including buttons and selected rows
- Don't introduce blue, green, or red — including system focus rings
  (disable them; carry focus with gold borders instead) and including
  "just for the error state"
- Don't add background fills to cards or panels; they're black on black
- Don't use 8/12/16px radii
- Don't letter-space 14px body text
- Don't animate anything on load

---

## 11. Porting checklist

Applying this to a new app, in the order that matters:

1. Paint every surface `#000000` and all text `#FFF7DD`. Resist adding a
   second surface tone.
2. Delete every shadow. Replace each one with a 1px cream-20% border.
3. Rebuild the type scale on the five styles in §3, and uppercase every
   label, button, and column header at 10px/500/+0.18.
4. Strip color from controls: no filled buttons, no colored badges, no
   system accent color. Disable the platform focus ring.
5. Reintroduce gold in exactly four places — accent borders, active states,
   caption-size emphasis text, and the progress fill.
6. Set radii to 4px and 100px. Nothing else.
7. Fix chrome heights to the table in §4 so density is consistent.
8. Rewrite empty and error states as instructions with a gold brand mark.

If the result still looks like a default component library, the cause is
almost always one of: a lingering shadow, a filled primary button, or
sentence-case labels at 13px.
