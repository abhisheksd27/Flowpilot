# Live frontend

Start `streamlit run app.py`. Select the built-in engine or a configured model, enter the city request, and choose **Run real pipeline**. A background thread runs the actual graph; a queue carries real events to a 200 ms Streamlit fragment. One persistent Mermaid SVG updates node states with smooth CSS transitions on a dark background, without re-rendering the graph for each event.

Result tabs show plan, executable transformation, validation checks, anomaly charts, downloadable report, warehouse tables, read-only SQL, run history and schema changes. **Load latest scheduled result** reads the latest persisted run. The sidebar shows daily service status and next execution time. The UI can close without stopping the separate scheduler.

Source: ui_assets/flow.js; checked-in bundle: ui_assets/flow.bundle.js. Rebuild using the package.json scripts when changing its JavaScript. Animations honor reduced-motion preferences. Actual frame smoothness depends on the browser/device; no artificial pipeline successes are shown.
