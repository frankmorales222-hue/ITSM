# AssetPilot UI Standards

These rules apply to every new page and every modification. A change is not
complete until it follows this contract at desktop, laptop, tablet, and mobile
widths.

## Layout contract

- The application shell owns the viewport. The navigation and top bar remain
  fixed; only the central content pane scrolls.
- The page itself must never require horizontal scrolling.
- Every grid or flex child uses a shrinkable track such as
  `minmax(0, 1fr)` and must have `min-width: 0`.
- Do not use fixed minimum column widths whose combined width can exceed the
  content pane.
- Do not use `overflow-x: hidden` to conceal content that does not fit.
  Correct the layout. A complex table may use its own `.table-wrap` scroller
  only when a card/mobile transformation would lose essential information.
- Forms, buttons, images, SVGs, tables, cards, and panels cannot exceed the
  width of their parent.

## Responsive behavior

- Desktop: use the complete information layout without clipping.
- Narrow desktop/tablet: reduce columns or convert each record to a labeled
  summary grid.
- Mobile: use a single-column reading order with visible field labels.
- Navigation, page headings, filters, action areas, cards, tables, empty
  states, and validation messages must use the same spacing and breakpoint
  system already defined in `site.css`.

## Interaction and accessibility

- Interactive rows must be keyboard accessible.
- Expandable content uses native `details`/`summary` or an equivalent
  control with an accessible state.
- Important actions must have text labels; color cannot be the only signal.
- Truncated values must remain available after expanding the record or opening
  its detail page.

## Required validation

Before packaging a release:

1. Build and run the complete automated test suite.
2. Verify affected pages at wide desktop, 1366×768 laptop, tablet, and mobile
   widths.
3. Confirm the document has no horizontal overflow.
4. Confirm all fields, actions, and validation messages remain visible.
5. Confirm expanding, filtering, searching, and returning to the previous page
   preserve the user's context.
