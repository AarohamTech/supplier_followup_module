---
name: Industrial Control Tower
colors:
  surface: '#fff8f7'
  surface-dim: '#f1d3d0'
  surface-bright: '#fff8f7'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#fff0ef'
  surface-container: '#ffe9e7'
  surface-container-high: '#ffe2de'
  surface-container-highest: '#f9dcd9'
  on-surface: '#271816'
  on-surface-variant: '#5b403d'
  inverse-surface: '#3e2c2a'
  inverse-on-surface: '#ffedeb'
  outline: '#8f6f6c'
  outline-variant: '#e4beba'
  surface-tint: '#ba1a20'
  primary: '#af101a'
  on-primary: '#ffffff'
  primary-container: '#d32f2f'
  on-primary-container: '#fff2f0'
  inverse-primary: '#ffb3ac'
  secondary: '#546067'
  on-secondary: '#ffffff'
  secondary-container: '#d7e4ec'
  on-secondary-container: '#5a666d'
  tertiary: '#565858'
  on-tertiary: '#ffffff'
  tertiary-container: '#6e7070'
  on-tertiary-container: '#f4f4f4'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffdad6'
  primary-fixed-dim: '#ffb3ac'
  on-primary-fixed: '#410003'
  on-primary-fixed-variant: '#930010'
  secondary-fixed: '#d7e4ec'
  secondary-fixed-dim: '#bbc8d0'
  on-secondary-fixed: '#111d23'
  on-secondary-fixed-variant: '#3c494f'
  tertiary-fixed: '#e2e2e2'
  tertiary-fixed-dim: '#c6c6c7'
  on-tertiary-fixed: '#1a1c1c'
  on-tertiary-fixed-variant: '#454747'
  background: '#fff8f7'
  on-background: '#271816'
  surface-variant: '#f9dcd9'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-lg:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  xs: 4px
  sm: 12px
  md: 24px
  lg: 32px
  xl: 48px
  gutter: 24px
  margin: 32px
  max_width: 1440px
---

## Brand & Style

This design system is engineered to bridge the gap between heavy industrial manufacturing and high-performance SaaS. The aesthetic is defined as a "Control Tower"—a centralized, high-visibility interface designed for precision, oversight, and rapid decision-making in procurement and supply chain management.

The brand personality is **authoritative, systematic, and resilient**. It avoids unnecessary decorative elements in favor of functional clarity and "information density without clutter." By utilizing high whitespace and a structured grid, the design system ensures that critical industrial data—stock levels, lead times, and procurement bottlenecks—is immediately actionable. The visual tone balances the grit of the Zanvar Group’s industrial roots with a modern, digital-first sophistication.

## Colors

The palette is rooted in an "Industrial Professional" logic. 

- **Primary Branding:** Industrial Red (#D32F2F) is used sparingly for primary actions, branding elements, and critical highlights to maintain its psychological impact without overwhelming the user.
- **Surface & Architecture:** Clean white backgrounds provide a sterile, high-contrast canvas. Charcoal Dark Grey (#263238) is utilized for sidebars and primary navigation to create a strong structural frame, anchoring the interface.
- **Functional Status:** This design system employs a strict semantic color language. 
    - **Green:** On-time shipments and healthy inventory.
    - **Yellow:** Expedited orders or low stock warnings.
    - **Red:** Delayed shipments or contract breaches.
    - **Black:** Total line stoppages or critical failures requiring immediate executive intervention.

## Typography

This design system uses **Inter** for its exceptional legibility in data-heavy environments. The typographic hierarchy is designed to guide the eye through complex procurement workflows.

- **Headlines:** Set with tighter letter-spacing and heavier weights to provide clear section anchoring.
- **Data Labels:** Use `label-md` with a slight uppercase transformation and letter-spacing for secondary metadata and table headers, ensuring they are distinguishable from primary data.
- **Numerical Data:** For dashboards featuring heavy metrics, use tabular figures (monospaced numbers) to ensure columns of figures align perfectly for quick scanning.
- **Readability:** High line-heights are maintained across body copy to prevent "visual fatigue" during long periods of administrative use.

## Layout & Spacing

The layout follows a **Fixed-Fluid Hybrid Grid**. The primary sidebar is fixed at 280px to maintain a constant "Control Tower" navigation, while the main content area utilizes a 12-column fluid grid.

- **The 8px Rhythm:** All spacing, padding, and margins are multiples of 8px. This creates a predictable, rhythmic flow that mirrors industrial precision.
- **Whitespace Strategy:** This design system prioritizes "Negative Space as a Tool." By providing generous 24px gutters between data cards, we reduce the cognitive load associated with traditional, cramped ERP systems.
- **Breakpoints:** 
    - **Desktop (1200px+):** Full 12-column visibility with persistent sidebar.
    - **Tablet (768px - 1199px):** Sidebar collapses to icons; grid shifts to 6 columns.
    - **Mobile (<767px):** Single column stack; margins reduced to 16px.

## Elevation & Depth

To maintain a "Premium SaaS" feel, elevation is used to signify interactivity and information hierarchy rather than just decoration.

- **Surface Tiers:** The main background is pure white (#FFFFFF). Cards and containers use a very subtle light grey surface (#F8F9FA) with a clean 1px border (#ECEFF1).
- **Soft Shadows:** This design system avoids heavy dropshadows. Instead, it uses ultra-diffused "Ambient Shadows"—a 10% opacity charcoal tint with a high blur radius (12-16px) to lift active cards or modals off the page.
- **Interactive Depth:** Buttons and clickable cards should exhibit a subtle "lift" on hover, increasing the shadow spread slightly to provide tactile feedback without utilizing skeuomorphism.

## Shapes

The shape language reflects the "Modern Industrial" theme through the use of **Standardized Radii**.

- **Containers & Cards:** Use a consistent 8px to 12px corner radius. This softens the "engineered" feel of the data without appearing too casual or consumer-focused.
- **Buttons & Inputs:** Fixed at 8px to maintain a sharp, professional alignment with the grid.
- **Data Tags:** Status chips and badges may use a "pill" shape (fully rounded) to differentiate them from structural components like cards and buttons.

## Components

- **Buttons:** Primary buttons are Solid Industrial Red with white text. Secondary buttons are ghost-style with Charcoal borders. The "Critical" action button uses a Solid Black background.
- **Input Fields:** Clean, 1px bordered boxes with 8px rounding. Active states use a 2px Industrial Red bottom border or subtle glow to indicate focus.
- **Data Tables:** High-density but legible. Rows have a 56px minimum height. On-hover highlights use a very pale grey. Headers are sticky and use the `label-md` typographic style.
- **Status Chips:** Small, semi-transparent background versions of the status colors (e.g., light green background with dark green text) for readability.
- **Control Cards:** The primary dashboard unit. Must include a title, a primary metric (Display LG), and a trend indicator (Sparkline or percentage).
- **Side Navigation:** Dark Charcoal background (#263238). Active links use a left-hand Industrial Red accent border (4px) and a subtle opacity shift.