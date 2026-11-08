"""Process untrusted issue text as data, never as shell or Python source."""
import json
import os
from pathlib import Path
from config import Settings
from pipeline.cities import CITIES, run_city
from pipeline.contracts import default_plan


def main():
    settings = Settings.from_env()
    settings.prepare()
    response = settings.data_dir / 'public-response.md'
    try:
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        request = event['issue']['body'].strip()
        if not 1 <= len(request) <= 600:
            raise ValueError('Please submit a request between 1 and 600 characters.')
        plan = default_plan(request)
        city = next((c for c in CITIES if c.casefold() == plan['city'].casefold()), None)
        if city is None:
            raise ValueError('Choose one of: ' + ', '.join(CITIES))
        result = run_city(city, settings, request=request)
        response.write_text('## Pipeline ' + result['status'] + '\n\n' + result.get('final_report', 'See the downloadable results for the report.'))
        return 0 if result['status'] == 'success' else 1
    except Exception as error:
        response.write_text('## Request could not complete\n\n' + str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
