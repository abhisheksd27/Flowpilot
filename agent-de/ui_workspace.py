"""Operational workspace built on real persisted warehouse data and bounded actions."""
from datetime import datetime, timedelta, timezone
import json
import pandas as pd
import streamlit as st
from dataclasses import replace
from pipeline.cities import CITIES, LOCATIONS, city_request, run_city
from pipeline.contracts import METRICS
from pipeline.analytics import records, ask_saved, explain_anomaly
from pipeline.operations import (health, check_alerts, load_runs, run_metrics, lineage,
                                 daily_summary, retention_candidates, apply_retention)
from pipeline.rules import load_config, save_config, evaluate_rules


def action(label, fn):
    """Expose errors at the point of action instead of breaking unrelated panels."""
    try:
        with st.spinner(label):
            return fn()
    except Exception as error:
        st.error(str(error))
        return None


def render_workspace(settings, city):
    st.subheader('Weather and pipeline workspace')
    tabs = st.tabs(['Explore data', 'Operations', 'Pipeline builder', 'Recovery', 'Storage & API'])
    today = pd.Timestamp.now(tz=LOCATIONS[city]['timezone']).date()
    with tabs[0]:
        with st.form('saved-question'):
            question = st.text_input('Ask saved data', 'How many hours exceeded 30°C last week?')
            if st.form_submit_button('Query saved data'):
                result = action('Querying warehouse…', lambda: ask_saved(question, city, settings))
                if result:
                    st.write(result['answer'])
                    st.dataframe(result['days'], hide_index=True)
                    if result.get('sql'):
                        st.code(result['sql'], language='sql')
                        st.caption('Bound parameters: ' + str(result['params']))
        st.caption('Supported history questions count temperature exceedances over the previous seven complete local dates, or compare today with yesterday. Coverage is disclosed.')
        a, b = st.columns(2)
        start = a.date_input('From local date', today - timedelta(days=7), key='export-start')
        end = b.date_input('To local date', today, key='export-end')
        if st.button('Load filtered records'):
            data = action('Loading…', lambda: records(settings, city, start, end))
            if data is not None:
                st.session_state['filtered-export'] = {'city': city, 'start': str(start), 'end': str(end), 'frame': data}
        saved = st.session_state.get('filtered-export')
        if saved and saved['city'] == city:
            st.caption(f"Loaded {saved['start']} to {saved['end']} · {len(saved['frame'])} rows · UTC timestamps")
            st.dataframe(saved['frame'], hide_index=True)
            st.download_button('Download filtered CSV', saved['frame'].to_csv(index=False), file_name=f'{city}-{saved["start"]}-{saved["end"]}.csv', mime='text/csv')
        st.divider()
        other = st.selectbox('Compare with city', [c for c in CITIES if c != city])
        if st.button('Compare current conditions'):
            from pipeline.current_weather import answer_temperature
            from tools.api_tool import APITool
            from pipeline.contracts import AIR
            def compare():
                rows = []
                for name in (city, other):
                    weather = answer_temperature('weather in ' + name, settings)
                    loc = LOCATIONS[name]
                    air = APITool(settings).call_api(AIR, {'latitude': loc['latitude'], 'longitude': loc['longitude'], 'current': 'pm2_5', 'timezone': loc['timezone']}, refresh=True)
                    current = weather['current']
                    rows.append({'city': name, 'temperature_c': current['temperature_2m'], 'rain_mm': current.get('rain'),
                                 'showers_mm': current.get('showers'), 'pm25_ug_m3': air['current'].get('pm2_5'),
                                 'weather_time': weather['time'], 'air_time': air['current']['time'], 'timezone': loc['timezone']})
                return pd.DataFrame(rows)
            data = action('Fetching both cities…', compare)
            if data is not None:
                st.dataframe(data, hide_index=True)
                st.caption('Current modeled intervals; weather and air timestamps are shown separately.')
        with st.expander('Explain an unusual reading'):
            metric = st.selectbox('Measurement to explain', METRICS)
            if st.button('List flagged readings'):
                from tools.anomaly_tool import detect_anomalies
                detected = action('Finding flagged readings…', lambda: detect_anomalies('silver_environment', metric, settings.db_path, location_id=str(LOCATIONS[city]['id'])))
                if detected is not None:
                    st.session_state['flagged-readings'] = {'city': city, 'metric': metric, 'records': detected['records']}
            stamp = st.text_input('Reading timestamp (UTC)', datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0).replace(tzinfo=None).isoformat())
            flags = st.session_state.get('flagged-readings', {})
            if flags.get('city') == city and flags.get('metric') == metric:
                if flags['records']:
                    selected_row = st.dataframe(flags['records'], hide_index=True, on_select='rerun', selection_mode='single-row')
                    if selected_row.selection.rows:
                        stamp = flags['records'][selected_row.selection.rows[0]]['time']
                        st.caption('Selected flagged reading: ' + str(stamp))
                else:
                    st.info('No readings are flagged under the current baseline.')
            if st.button('Explain reading'):
                result = action('Inspecting baseline…', lambda: explain_anomaly(settings, city, metric, stamp))
                if result:
                    st.write({k: v for k, v in result.items() if k != 'surrounding'})
                    st.dataframe(result['surrounding'], hide_index=True)
                    st.caption('Flags use |Z-score| > 3 or 1.5-IQR bounds. The baseline is current retained history; seasonality is not removed.')
        with st.expander('Additional source: NASA solar-energy context'):
            st.caption('Daily solar radiation complements weather. It is not electricity demand. Dates use NASA local solar time.')
            solar_start = st.date_input('Solar start', today - timedelta(days=14))
            solar_end = st.date_input('Solar end', today - timedelta(days=7))
            if st.button('Fetch solar context'):
                from pipeline.solar import fetch_solar
                result = action('Fetching NASA POWER…', lambda: fetch_solar(settings, city, solar_start, solar_end))
                if result:
                    st.write(result['unit'], result['meaning'])
                    solar = pd.DataFrame(result['rows'])
                    st.dataframe(solar, hide_index=True)
                    weather = action('Joining saved daily context…', lambda: records(settings, city, solar_start, solar_end))
                    if weather is not None and not weather.empty:
                        weather['date'] = pd.to_datetime(weather.time, utc=True).dt.tz_convert(LOCATIONS[city]['timezone']).dt.strftime('%Y-%m-%d')
                        daily = weather.groupby('date', as_index=False).agg(temperature_c=('temperature_c', 'mean'), pm25=('pm2_5_ug_m3', 'mean'))
                        st.dataframe(daily.merge(solar, on='date', how='outer'), hide_index=True)
                        st.caption('Date alignment is approximate because city civil time and NASA solar time differ; no causal claim is made.')
    with tabs[1]:
        state = action('Checking health…', lambda: check_alerts(settings, city))
        if state:
            st.json(state)
            if state['stale']:
                st.warning('Data is stale or missing. Refresh this city or check the background watcher.')
        alerts = []
        for path in sorted((settings.data_dir / 'alerts').glob('*.json'), reverse=True)[:30]:
            try:
                alerts.append(json.loads(path.read_text()))
            except ValueError:
                pass
        if alerts:
            st.error(f'{len(alerts)} retained alert(s). Failures remain in history; stale alerts clear after recovery.')
            st.dataframe(alerts, hide_index=True)
            newest = alerts[0]['key']
            if st.session_state.get('last-alert') != newest:
                st.toast(alerts[0]['message'][:300], icon='⚠️')
                st.session_state['last-alert'] = newest
        st.caption('Alerts are saved locally and shown in the dashboard. External email/SMS is not configured.')
        metrics = action('Loading metrics…', lambda: run_metrics(settings))
        if metrics is not None and not metrics.empty:
            st.dataframe(metrics, hide_index=True)
            st.line_chart(metrics.set_index('run_id')[['failed_checks', 'validation_failures', 'missing_count', 'duplicate_count']].iloc[::-1])
            options = metrics.run_id.tolist()
            left = st.selectbox('First run', options)
            right = st.selectbox('Second run', options, index=min(1, len(options)-1))
            st.dataframe(metrics[metrics.run_id.isin([left, right])], hide_index=True)
            if st.button('Inspect selected run lineage'):
                result = action('Loading lineage…', lambda: lineage(settings, left))
                if result:
                    st.json({k: v for k, v in result.items() if k != 'code'})
                    st.code(result['code'] or '', language='python')
        if st.button('Generate daily summary'):
            result = action('Summarizing saved data…', lambda: daily_summary(settings, city))
            if result:
                st.text(result)
                st.download_button('Download daily summary', result, file_name=f'{city}-daily-summary.md')
    with tabs[2]:
        config = action('Reading configuration…', lambda: load_config(settings)) or {}
        with st.form('pipeline-builder'):
            target = st.selectbox('Pipeline city', CITIES, index=CITIES.index(config.get('city', city)))
            measurements = st.multiselect('Report measurements', METRICS, default=config.get('measurements', METRICS))
            frequency = st.selectbox('Collection frequency', ['hourly', 'daily'], index=0 if config.get('frequency', 'hourly') == 'hourly' else 1)
            at = st.text_input('Daily time (Asia/Kolkata)', config.get('at', '08:00'))
            st.caption('Core types, completeness, freshness and source reconciliation always remain enabled. Report measurement selection does not remove canonical warehouse columns.')
            enable_rule = st.checkbox('Enable a custom rule', value=bool(config.get('rules')))
            existing = (config.get('rules') or [{}])[0]
            metric = st.selectbox('Rule measurement', METRICS, index=METRICS.index(existing.get('metric', METRICS[0])))
            operator = st.selectbox('Rule condition', ['above', 'below'], index=0 if existing.get('operator', 'above') == 'above' else 1)
            threshold = st.number_input('Threshold', value=float(existing.get('threshold', 30)))
            rule_action = st.selectbox('When matched', ['flag', 'block'], index=0 if existing.get('action', 'flag') == 'flag' else 1)
            if st.form_submit_button('Save pipeline configuration'):
                result = action('Saving…', lambda: (save_config(settings, {'city': target, 'measurements': measurements,
                    'frequency': frequency, 'at': at, 'rules': [{'metric': metric, 'operator': operator, 'threshold': threshold, 'action': rule_action}] if enable_rule else []}), True)[1])
                if result:
                    st.success('Saved. New pipeline runs use these rules. The watcher adopts the schedule at its next run; no watcher is started by saving.')
        if st.button('Evaluate saved rules on selected city'):
            def evaluate():
                selected = load_config(settings)
                if not selected or selected['city'] != city:
                    raise ValueError('Select the configured city first')
                frame = records(settings, city, today-timedelta(days=7), today)
                return evaluate_rules(frame, selected['rules'])
            results = action('Evaluating…', evaluate)
            if results is not None:
                st.json(results)
    with tabs[3]:
        st.caption('These actions run real Docker jobs. Wait for active collection to finish before starting recovery.')
        start_date = st.date_input('Backfill UTC start date', today-timedelta(days=10))
        end_date = st.date_input('Backfill UTC end date', today-timedelta(days=6))
        if st.button('Run validated backfill'):
            from agent.graph import run_pipeline
            start = pd.Timestamp(start_date)
            end = pd.Timestamp(end_date) + pd.Timedelta(hours=23)
            result = action('Running backfill…', lambda: run_pipeline(city_request(city), replace(settings, provider='builtin', demo_mode=False),
                              window=(start, end), refresh=True))
            if result:
                st.write(result['status'])
                st.markdown(result['final_report'])
        if st.button('Run incremental collection now'):
            result = action('Collecting new hours…', lambda: run_city(city, replace(settings, provider='builtin', demo_mode=False), refresh=True, incremental=True))
            if result:
                st.write(result['status'], result.get('published'))
        runs = load_runs(settings)
        failures = [r['run_id'] for r in runs if r['status'] != 'success']
        if failures:
            selected = st.selectbox('Failed run to replay', failures)
            if st.button('Replay original snapshots in separate warehouse'):
                from pipeline.recovery import replay
                result = action('Verifying snapshots and replaying…', lambda: replay(settings, selected))
                if result:
                    st.markdown(result['final_report'])
        scenario = st.selectbox('Failure to inject', ['missing_field', 'timeout', 'null_value'])
        persistent = st.checkbox('Keep the injected failure on every attempt')
        if st.button('Run isolated failure simulation'):
            from pipeline.recovery import simulate
            result = action('Establishing baseline and testing failure recovery…', lambda: simulate(settings, city, scenario, persistent))
            if result:
                st.write({k: v for k, v in result.items() if k != 'result'})
                st.markdown(result['result']['final_report'])
    with tabs[4]:
        days = st.number_input('Retention days', min_value=7, max_value=3650, value=90)
        auto_archive = st.checkbox('Enable automatic archiving after scheduled runs')
        if st.button('Save retention policy'):
            from pipeline.events import write_json
            write_json(settings.data_dir / 'retention-policy.json', {'enabled': auto_archive, 'days': days})
            st.success('Retention policy saved for the hourly watcher. Existing archives remain recoverable.')
        st.caption('Preview first. Applying retention moves old run files, logs, reports and raw snapshots to retention-trash. The warehouse and latest city results are protected. Moving files reduces active history but does not reclaim disk space until you remove the trash yourself.')
        if st.button('Preview retention candidates'):
            result = action('Scanning…', lambda: retention_candidates(settings, days))
            if result is not None:
                st.write([str(p) for p in result])
        confirm = st.checkbox('I want to archive these old artifacts')
        if st.button('Move old artifacts to recoverable trash', disabled=not confirm):
            result = action('Archiving…', lambda: apply_retention(settings, days))
            if result is not None:
                st.success(f'Moved {len(result)} artifacts into data/retention-trash; they can be restored from there.')
        st.write('Local read-only API')
        st.code('python -m pipeline.read_api --port 8765\n# Open http://127.0.0.1:8765/health\n# GET /v1/weather?city=Bengaluru&start=2026-11-01&end=2026-11-09', language='bash')
        st.caption('Binds to localhost. Date ranges are limited to 366 days and responses to 1,000 rows. It provides validated saved data; it does not execute arbitrary SQL or pipeline code.')
