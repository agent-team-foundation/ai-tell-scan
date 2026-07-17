# Composite signal reference

Each rule requires several co-located primitives. The agent still reviews
visibility, prominence, repetition, product genre, and brand intent.

| Rule | Required composite | Important rejection case |
| --- | --- | --- |
| `ats.gradient-display-heading` | Display-scale h1/h2 + multicolor accent gradient + text clipping + transparent fill | Small logo/accent text, solid display heading, or unrelated gradient selector |
| `ats.aurora-centered-hero` | Tall centered hero + primary h1/CTA + absolute blurred multicolor gradient layer | Centered content without atmospheric decoration, or decoration outside the hero |
| `ats.glass-floating-nav` | Fixed/sticky top nav + capsule radius + translucency + backdrop blur + border/shadow + action | Rectangular sticky bar or blur used only to preserve legibility |
| `ats.icon-card-triptych` | Three-column block + at least three uniform framed cards + headings/descriptions + three tinted square icon tiles | Pricing/data cards without icon tiles, or heterogeneous content shapes |
| `ats.repeated-section-kickers` | At least three uppercase tracked micro-labels directly preceding h2s | One editorial/category label with real information |
| `ats.round-metric-proof-row` | Three-up proof layout + at least three generic round proof values | Specific measured values with dates/sources |
| `ats.glass-card-field` | Four or more translucent blurred framed panels + atmospheric background + marketing h1/action | Dashboard/analytics data surfaces where depth communicates state |
| `ats.pill-role-overload` | Seven or more capsules across at least three semantic roles, including multiple actions | Many tags/chips that all share one semantic role |
| `ats.spring-hover-everywhere` | Four or more interactive surfaces repeat `transition-all` plus scale/lift hover | One or two emphasized controls, or property-specific state motion |
| `ats.multicolor-card-wash` | Three/four-column framed card family + at least three cards each pairing its own tint and same-family foreground/border | Semantic status colors, tinted child icons on neutral cards, or non-grid status rows |

## Review questions

1. Can a user actually reach this component in the shipped product?
2. Do all required primitives appear in the same visual composition?
3. Is the combination prominent or repeated enough to shape first impression?
4. Is it a deliberate brand/product decision rather than a generic default?
5. Would the stated minimal fix preserve meaning and behavior?

Reject if any answer is no or cannot be established from source context. Never
upgrade a weak candidate because several unrelated minor patterns exist.
