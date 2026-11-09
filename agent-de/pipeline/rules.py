"""Persisted pipeline configuration and bounded business-rule evaluation."""
import json
import math
from pipeline.cities import CITIES
from pipeline.contracts import METRICS
from pipeline.events import write_json


def validate_config(config):
    if config.get('city') not in CITIES or config.get('frequency') not in ('hourly', 'daily'):
        raise ValueError('Choose a catalog city and hourly/daily schedule')
    hour, minute = map(int, config.get('at', '08:00').split(':'))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError('Invalid daily time')
    if not config.get('measurements') or set(config['measurements']) - set(METRICS):
        raise ValueError('Choose supported measurements')
    for rule in config.get('rules', []):
        if rule.get('metric') not in METRICS or rule.get('operator') not in ('above', 'below') or rule.get('action') not in ('flag', 'block'):
            raise ValueError('Unsupported rule')
        if not math.isfinite(float(rule['threshold'])):
            raise ValueError('Threshold must be finite')
    return config


def save_config(settings, config):
    write_json(settings.data_dir / 'pipeline-config.json', validate_config(config))


def load_config(settings):
    path = settings.data_dir / 'pipeline-config.json'
    return validate_config(json.loads(path.read_text())) if path.exists() else None


def evaluate_rules(frame, rules):
    results = []
    for rule in rules:
        values = frame[rule['metric']]
        mask = values.gt(rule['threshold']) if rule['operator'] == 'above' else values.lt(rule['threshold'])
        results.append({**rule, 'matches': int(mask.sum()), 'samples': len(frame), 'passed': not bool(mask.any()),
                        'records': frame.loc[mask].head(100).to_dict('records')})
    return results
