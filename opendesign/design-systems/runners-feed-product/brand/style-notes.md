# Visual and interaction foundations

## Layout

- Use a centered shell capped at 1180px.
- Major workflow areas use grid layouts with 1px borders and shared edges.
- Separate major page sections with generous vertical space and a top rule.
- Collapse multi-column regions to one column below 800px.

## Components

- Panels and buttons are square. Circular geometry is reserved for step markers.
- Primary actions use a full lime fill with dark text.
- Secondary actions use transparent or dark surfaces with subtle borders.
- Dense data and identifiers use the monospace stack.
- Status is expressed through text and restrained color, not decorative badges.

## Background and depth

- Use the near-black page background and dark green-black surfaces.
- The existing top-right lime glow is the only background gradient treatment.
- Use borders and tonal surface changes instead of shadows.

## Motion

- Hover and focus transitions use approximately 160ms.
- Scrolling to newly available results may be smooth.
- Respect `prefers-reduced-motion` and remove non-essential transitions.

## Interaction

- Focus and hover states use the lime accent.
- Mobile touch targets are at least 44px high.
- Disabled actions retain their position and become muted rather than disappearing.
