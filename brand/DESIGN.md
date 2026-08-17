---
version: 1.0
name: Brian Newman
description: Deep-navy editorial and technical identity for the portfolio and Newman Labs.
colors:
  primary: "#1A4164"
  primary-raised: "#23587C"
  secondary: "#286291"
  secondary-hover: "#23587C"
  secondary-graphic: "#4987AE"
  tertiary: "#6B7E8F"
  tertiary-graphic: "#D8D4CB"
  neutral: "#F6F2EF"
  surface: "#FAF8F3"
  surface-raised: "#FFFFFF"
  text: "#1A4164"
  text-muted: "#5B6B77"
  border: "#D8D4CB"
  control-border: "#6B7E8F"
  success: "#147A5A"
  warning: "#A15C00"
  danger: "#B42318"
  dark-text: "#FFFFFF"
  dark-text-muted: "#B8C4CC"
  dark-border: "#31485A"
  dark-control-border: "#B8C4CC"
  dark-secondary: "#8AB6D1"
  dark-secondary-hover: "#A7C4D8"
  dark-tertiary: "#D8D4CB"
typography:
  display-xl:
    fontFamily: Newsreader, Georgia, serif
    fontSize: 120px
    fontWeight: 400
    lineHeight: 0.92
    letterSpacing: -0.045em
  display-lg:
    fontFamily: Newsreader, Georgia, serif
    fontSize: 88px
    fontWeight: 400
    lineHeight: 0.96
    letterSpacing: -0.04em
  heading-1:
    fontFamily: Manrope, system-ui, sans-serif
    fontSize: 64px
    fontWeight: 600
    lineHeight: 1.02
    letterSpacing: -0.035em
  heading-2:
    fontFamily: Manrope, system-ui, sans-serif
    fontSize: 48px
    fontWeight: 600
    lineHeight: 1.08
    letterSpacing: -0.025em
  heading-3:
    fontFamily: Manrope, system-ui, sans-serif
    fontSize: 32px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: -0.015em
  lead:
    fontFamily: Manrope, system-ui, sans-serif
    fontSize: 21px
    fontWeight: 400
    lineHeight: 1.65
  body:
    fontFamily: Manrope, system-ui, sans-serif
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.65
  small:
    fontFamily: Manrope, system-ui, sans-serif
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.5
  label:
    fontFamily: Manrope, system-ui, sans-serif
    fontSize: 12px
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: 0.08em
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  base: 16px
  lg: 24px
  xl: 32px
  2xl: 48px
  3xl: 64px
  section: 96px
  section-lg: 128px
  section-xl: 160px
  gutter-mobile: 20px
  gutter: 24px
  gutter-desktop: 40px
rounded:
  sm: 6px
  md: 10px
  lg: 16px
  full: 999px
---

# Brian Newman design system

## Overview

The Brian Newman identity combines editorial restraint with engineering
instrumentation. It should feel calm, capable, technical, and human. It borrows
principles from Apple and Linear, such as hierarchy, precision, consistency, and
quiet surfaces, without imitating either brand.

**Position:** Practical engineering for real systems.

**Personality:** Precise, grounded, direct, curious, and quietly confident.

Three principles resolve visual ambiguity:

1. **Clarity before decoration.** Content and task hierarchy lead. Every effect
   must support structure.
2. **Evidence over theater.** Show real work, environments, diagrams, and outcomes.
   Avoid generic technology spectacle.
3. **One identity, two modes.** Portfolio is spacious and editorial. Labs is denser
   and operational. Both use this file, the same logo, and the same tokens.

### Product modes

**Portfolio:** Full-bleed editorial photography, a deep navy hero, Newsreader for
major narrative statements, generous space, and a white geometric wordmark.

**Labs:** A deep navy-to-blue product opening, subtle data-field linework, Newsreader
display type, and denser grids, tables, filters, logs, and technical panels.
Product naming follows the master identity, such as `Brian Newman / Labs`; Labs
does not invent a new logo.

The Labs index may use one approved opening gradient from Primary through Primary
Raised to Secondary, with a Secondary Graphic radial field and restrained
isometric linework anchored away from copy. Navigation remains a flat Primary
band, and product workspaces do not inherit the gradient.

### Social banners

Use the same approved technical banner composition across GitHub, LinkedIn, and
X. The GitHub artwork is the visual master, but each platform uses its own
centered crop so the wordmark remains sharp, complete, and safely positioned.

- GitHub: `social-banner-master-1280x400.png`
- LinkedIn: `social-banner-linkedin-1584x396.png`
- X: `social-banner-x-1500x500.png`

Never regenerate, typeset, or redraw the wordmark inside a social banner. Keep
the name centered and preserve the original white lettering, navy background,
and blue technical linework.

### Voice

Write like a strong engineer explaining a real decision to another capable
person. Use plain language, concrete nouns, active voice, and specific outcomes.
Avoid hype, inflated claims, unexplained jargon, and empty adjectives such as
revolutionary, seamless, or world-class. Headings use sentence case. Buttons are
short and verb-led. Errors say what happened and what to do next. Never use an em
dash.

## Colors

Deep navy and warm neutral carry most of the interface. Blue owns identity and
interaction. Cool gray supplies restrained contrast inside data and editorial
details.

- **Primary:** Navy 950 is default ink and the dark canvas.
- **Secondary:** Blue 700 is the primary action, link, focus, and brand color.
- **Tertiary:** Slate gray is supporting structure, comparison data, and quiet
  editorial detail. It is not a competing call-to-action color.
- **Neutral:** Canvas, white surfaces, raised surfaces, muted text, and borders
  establish the quiet working field.
- **Semantic:** Success, warning, and danger retain their conventional meanings
  and always appear with text or an icon.

### Approved contrast

| Foreground | Background | Ratio | Use |
| --- | --- | --- | --- |
| Primary | Neutral | 9.51:1 | Body and display text |
| Text muted | Neutral | 4.95:1 | Secondary text |
| Secondary | Surface | 6.10:1 | Links, buttons, focus |
| Surface | Secondary | 6.10:1 | Primary button text |
| Secondary graphic | Neutral | 3.52:1 | Large graphics only |
| Control border | Neutral | 3.77:1 | Required control boundary |
| Dark text | Primary | 10.58:1 | Dark sections |
| Dark secondary | Primary | 4.89:1 | Dark-theme links and focus |
| Dark control border | Primary raised | 4.28:1 | Dark control boundary |

Secondary Graphic and Tertiary Graphic are decorative on light backgrounds. Do
not use them for small text. Test any unlisted pair before release.

### Light and dark themes

Light is the default reading and application theme. Dark is approved for hero
sections, technical workspaces, and media. Dark uses navy, not pure black. Do not
simply invert colors. Use the dark tokens for surface, text, border, interaction,
and accent roles.

## Typography

**Manrope** is the primary family for UI, navigation, controls, body copy, and
labels. Use weights 400, 500, 600, and 700. Never use thin weights for live text.
The wordmark is custom artwork and is never recreated with a font, redrawn, or
traced. The supplied colored transparent PNG is the geometry master. The white
version preserves its alpha mask exactly and changes only the visible color.

**Newsreader** is reserved for editorial display, article leads, portfolio
statements, and occasional section headings. Use weights 400 and 500.

**System monospace** is reserved for code, commands, timestamps, metrics,
identifiers, and compact metadata. Never use it for long paragraphs.

The YAML sizes are maximum design values. Implement responsive display and
heading sizes with `clamp()` bounded by those values. Body text remains at least
16px. Keep prose between 55 and 75 characters per line, normally 42rem to 46rem.
Use balanced wrapping for display headings, not body text. Use tabular figures in
tables, metrics, logs, and dashboards.

Labs is primarily Manrope. Portfolio may use Newsreader for expressive display.
No screen uses more than these two families plus monospace.

## Layout

Use the 4px spacing scale in the YAML frontmatter. Do not add an almost-matching
gap. The standard layout values are:

- Mobile page gutter: 20px, increasing to 24px when space permits
- Desktop page gutter: 40px
- Portfolio content maximum: 1280px
- Labs shell maximum: 1440px when a bounded shell is useful
- Reading column maximum: 736px
- Major section space: 96px mobile and 128px desktop
- Card padding: 24px mobile and 32px desktop

Use a 12-column grid on wide layouts and collapse by content need, not named
device models. Prefer CSS Grid and `minmax(0, 1fr)`. Avoid fixed content heights.
Support 320px viewports, 200 percent text zoom, long content, and keyboard use
without lost content or function.

Hierarchy comes from scale, spacing, alignment, and weight before color or depth.
Let whitespace do real work.

## Elevation & Depth

Depth is quiet and functional. A bordered card normally needs no shadow.

- Low shadow: `0 1px 2px rgb(7 27 46 / 0.06)`
- Overlay shadow: `0 16px 48px rgb(7 27 46 / 0.16)`
- Decorative divider: 1px Border
- Required control boundary: 1px Control Border with at least 3:1 contrast

Use one depth cue at a time. Avoid nested floating cards, heavy blur, glass, and
shadows without structural purpose.

### Navigation surfaces

Global navigation is a flat horizontal band, never a floating glass capsule.
Portfolio overlays the band on the hero with a quiet bottom rule. Labs uses an
opaque or nearly opaque Primary band with the same rule. A small background blur
is acceptable only to protect legibility while content scrolls beneath the band.

- Keep the navigation edge to edge and square.
- Use the white wordmark over dark or photographic backgrounds.
- Use one 1px divider. Do not add an inset highlight or large shadow.
- Do not use Liquid Glass sweeps, refraction, floating rounded shells, or
  decorative gradients in navigation.
- Preserve 44px targets, visible focus, and a solid Primary fallback.

### Motion

Motion communicates cause, state, and continuity. It is never ambient filler.

- Fast feedback: 120ms
- Standard transition: 180ms
- Overlay or page transition: 280ms
- Easing: `cubic-bezier(0.2, 0.8, 0.2, 1)`
- Entrance travel: 8px maximum
- Hover lift: 2px maximum, only when depth is meaningful

Prefer opacity and transform. Avoid parallax, scroll hijacking, looping motion,
and large background movement. Under `prefers-reduced-motion: reduce`, remove
movement and smooth scrolling while preserving immediate state feedback.

## Shapes

Use Small radius for code, compact controls, and chips; Medium for inputs and
buttons; Large for cards, menus, and media. Full radius is limited to avatars,
status dots, tags, and deliberately pill-shaped primary actions.

Do not nest rounded containers without a real hierarchy. Icons use round caps and
joins, but interface geometry stays precise rather than playful.

### Geometric pattern

Isometric triangles and cubes are the supporting graphic language. They represent
layers, systems, and transformation. They are never a substitute for the
wordmark or BN mark.

- Construct patterns on one 60-degree isometric grid.
- Anchor one or two clusters to composition edges and preserve the content field.
- Use Primary, Primary Raised, Secondary, Secondary Graphic, and Tertiary Graphic.
- Keep at least half of a decorative composition visually quiet.
- Use complete cubes sparingly and standalone triangles as small rhythm accents.
- Do not scatter shapes as confetti, mix perspective systems, add shadows, or
  place the pattern behind body copy.

## Components

### Navigation

Use one stable flat header pattern across portfolio and Labs. The white wordmark
is left aligned. Primary destinations are text links. Show the current location
with weight or underline in addition to color. Mobile navigation must not hide
essential destinations behind an unlabeled icon.

### Buttons and links

Use one primary action per region. Primary buttons use Secondary with white text.
Secondary buttons use a Surface background, Primary text, and Control Border.
Quiet actions use a text label with clear hover and focus states. Danger styling
is reserved for a real destructive action.

Body links use Secondary and a visible underline. Navigation and button-like links
may omit the underline when shape, position, and state make interaction clear.

### Cards and forms

Cards group related content or define an interaction boundary. They are not the
default container for every block. Use Surface, Border, Large radius, and no
shadow. Interactive cards need visible focus and a modest border or surface change
on hover.

Labels remain visible above controls. Inputs are at least 44px tall and use
Control Border. Helper and error text sits next to the field it describes. Errors
use icon, text, and color. Placeholder text never replaces a label.

### Data and state

Use tables for exact comparison, charts for patterns, and prose for conclusions.
Align numbers right and use tabular figures. Keep gridlines quiet. Secondary is the
default series; Tertiary is the selected or compared series. Semantic colors are
only for semantic state. Every chart needs an accessible label and text summary.

Empty, loading, and error states state the condition plainly, explain the next
useful action, and preserve context. Use skeletons only when the layout is known.
Avoid indefinite spinners without text.

### Logo system

The primary identity is Brian's original thin geometric wordmark. Its open `A`,
linear `N`, and wide tracking are distinctive brand features, not typography
choices to approximate with live text. The default website treatment is white
over deep navy or photography. The blue gradient version is approved on light
surfaces.

The companion symbol is the `BN` icon cut directly from the wordmark's exact
letterforms. Use it for compact identity contexts at 24px and larger. It is not
placed beside the wordmark in routine navigation. Canonical files live in
`brand/assets`:

| Asset | Use |
| --- | --- |
| `brian-newman-wordmark-color.png` | Canonical supplied colored wordmark on light backgrounds |
| `brian-newman-wordmark-white.png` | Exact white recolor of the colored wordmark on dark backgrounds |
| `brian-newman-icon-color.png` | Exact colored BN letters for compact light-background use |
| `brian-newman-icon-white.png` | Exact white BN letters for compact dark-background use |

Clear space is at least one quarter of the mark height or one half of the
wordmark letter height. Minimum digital size is 24px for a standalone icon and
132px wide for the wordmark. Use the canonical PNG files directly in product
interfaces.

Navigation and footers use the wordmark without the mark. Use the reversed
version on Primary or a photograph with a quiet dark region. Use the blue version
on Neutral, Surface, or white. Never stretch, rotate, redraw, shadow, recolor, or
recreate the wordmark or icon as live text. The favicon treatment below is the
only approved container for the icon.

Browser favicons use the approved optical `BN` redraw centered inside a Primary
circle. It preserves the custom open `B`, linear `N`, proportions, and spacing,
but uses a heavier uniform stroke so the mark remains legible at 16px and 32px.
This redraw is limited to browser favicon derivatives and never replaces the
canonical icon or wordmark. The browser favicon is transparent outside the
circle. The Apple touch icon continues to use the exact canonical icon on
Neutral. Browser-sized PNG and ICO derivatives are generated inside the
consuming app. Set browser theme color to Primary.

### Interface icons

Use one established outline family per product. Standard control icons are 20px,
dense metadata icons are 16px, and standalone actions are 24px. Default stroke is
1.75px with round caps and joins. Custom icons are SVG and match the same optical
weight. Pair unfamiliar or consequential icons with text. Icon-only buttons need
an accessible name and tooltip.

### Photography and generated images

Images make invisible systems tangible. Favor candid editorial photographs of
real work, tools, environments, and people; close details of operations and field
notes; natural expressions; useful negative space; cool neutral daylight; deep
navy shadows; and one restrained warm detail.

Use approved real photography for Brian. Do not generate his likeness. Avoid
glowing brains, robots, floating code, holographic dashboards, circuit faces,
generic server rooms, fake UI, watermarks, stock-photo handshakes, neon cyberpunk,
and imagery that implies unsupported access or accomplishments.

Use this prompt structure when generation is appropriate:

```text
Use case: photorealistic-natural | stylized-concept | infographic-diagram
Asset type: project hero | article cover | social graphic | technical illustration
Primary request: [specific subject and purpose]
Scene/backdrop: [credible environment with only needed details]
Subject: [one clear focal subject]
Style/medium: restrained editorial photography or crisp technical illustration
Composition/framing: [aspect ratio], clear hierarchy, negative space at [side]
Lighting/mood: natural, calm, capable, cool-neutral light with one warm detail
Color palette: Neutral, Primary, Secondary, restrained Tertiary; no blue wash
Text: none unless exact copy is required
Constraints: evidence-safe, realistic materials, accessible focal contrast
Avoid: generic AI imagery, fake UI, neon, holograms, watermark, extra text, logos
```

Review subject accuracy, composition, faces, hands, text, artifacts, evidence
risk, crop safety, and palette. Keep the final prompt with the asset or pull
request. Prefer AVIF or WebP for photography. Use the canonical transparent PNG
files for the wordmark and BN icon. Set intrinsic image dimensions and useful alt text. Social previews are
1200 by 630 with essential content at least 72px from each edge.

## Do's and Don'ts

### Do

- Treat the YAML tokens as normative and the prose as usage guidance.
- Meet WCAG 2.2 AA: 4.5:1 normal text, 3:1 large text and essential UI graphics.
- Preserve visible focus and use 44px targets where practical, with 24px as the
  absolute WCAG minimum.
- Use color with labels, icons, shape, or position when it communicates state.
- Reuse an existing component before creating a visual variant.
- Keep private workspace and career-search material out of public examples and media.
- Test light and dark states, 320px width, 200 percent zoom, keyboard flow, long
  content, and reduced motion before release.

### Don't

- Add an almost-matching color, spacing value, radius, shadow, or logo variant.
- Use gradients, floating glass shells, shadows, pills, or animation as default
  decoration in the content layer.
- Use an icon when a short text label is clearer.
- Recreate the BN monogram with live text or use the mark as a decorative
  background pattern.
- Mix filled, outlined, hand-drawn, 3D, and emoji icon styles in one surface.
- Create a separate Labs identity, palette, or typography system.

### Implementation

1. Read this file before frontend, logo, icon, image, or social work.
2. Map product framework tokens directly from the YAML values when implementation
   begins. Do not maintain a second hand-edited token source.
3. If a new token is necessary, add its role to the YAML and explain it in the
   matching canonical section.
4. Keep the complete `brand/` directory identical in personal-brand and
   newman-labs.

### Research basis

- [Google DESIGN.md specification](https://github.com/google-labs-code/design.md/blob/main/docs/spec.md)
- [Design Tokens Format Module 2025.10](https://www.designtokens.org/tr/2025.10/format/)
- [Apple design principles](https://developer.apple.com/design/human-interface-guidelines/design-principles)
- [Apple typography guidance](https://developer.apple.com/design/human-interface-guidelines/typography)
- [Apple color guidance](https://developer.apple.com/design/human-interface-guidelines/color)
- [Apple icon guidance](https://developer.apple.com/design/human-interface-guidelines/icons)
- [GitHub Primer color tokens](https://primer.style/product/getting-started/foundations/color-usage/)
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/)
- [W3C target size guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum)
- [W3C reduced motion technique](https://www.w3.org/WAI/WCAG22/Techniques/css/C39)
- [WHATWG icon link standard](https://html.spec.whatwg.org/multipage/links.html)
