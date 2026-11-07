# Stable flow animation

`flow.js` renders the trusted Mermaid architecture once per mounted component.
Subsequent events update SVG node attributes; `flow.css` handles 500 ms color
transitions and moving connection dashes without changing layout. Reduced-motion
preferences disable animation. The viewport and status area keep fixed heights.

The checked-in bundle includes Mermaid so runtime rendering needs no CDN or Node
installation. Python loads it through Streamlit's persistent v2 component API.
The fragment in `app.py` advances events without replacing the diagram container.

To rebuild after changing JavaScript, run from this directory:

```bash
npm ci
npm run build
```

The Mermaid source is `../docs/architecture.mmd`. Reload the browser after changing
the diagram topology; live status events intentionally do not recompute layout.

`flow.bundle.js.LEGAL.txt`, `MERMAID-LICENSE`, and `THIRD_PARTY_LICENSES.txt` retain
third-party license notices. Existing pipeline and result-panel logic is separate
from this animation component.
