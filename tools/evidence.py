"""Fail-closed checks for observed test identities and acceptance artifacts."""
from pathlib import Path
import hashlib, json, re

ROOT = Path(__file__).resolve().parent
EXPECT = json.loads((ROOT / 'expectations.json').read_text())

def require(condition, message):
    if not condition:
        raise ValueError(message)

def parse_tests(result):
    require(result['exit'] == 0 and not result['stderr'], 'test process failed')
    lines = bytes.fromhex(result['stdout']).decode('utf-8').splitlines()
    require(bool(lines), 'missing test output')
    match = re.fullmatch(r'tests: total=(\d+) passed=(\d+) failed=0 errors=0 aborted=0 not_run=0', lines[-1])
    require(match is not None, 'missing or unsuccessful test summary')
    identities = []
    for line in lines[:-1]:
        require(line.startswith('PASS '), 'non-passing or unknown test result')
        identities.append(line[5:])
    require(len(identities) == len(set(identities)), 'duplicate test identity')
    require(set(identities) == set(EXPECT['tests'].values()), 'missing or unexpected test identity')
    require(int(match[1]) == int(match[2]) == len(identities), 'test count mismatch')
    return {name: {'identity': identity, 'result': 'pass'}
            for name, identity in EXPECT['tests'].items()}

def measurements(session):
    path = session.evidence / 'measurements.json'
    require(path.is_file(), 'missing measurement artifact')
    report = json.loads(path.read_text())
    for name in ['model.mgn', 'text.mgn']:
        require(report['module_sha256'][name] == session.metadata['source_sha256']['src/Core/' + name], 'measurement source mismatch')
    cells = report['results']
    expected = {(kind, shape, size) for kind in ['scan-control', 'scan', 'join-control', 'join']
                for shape in ['ascii', 'unicode'] for size in [256, 1024, 4096]}
    require(len(cells) == len(expected), 'measurement count mismatch')
    require({(c['kind'], c['shape'], c['scalars']) for c in cells} == expected, 'measurement cell missing')
    for cell in cells:
        require(cell['assertions_passed'] is True and cell['iterations'] == 4, 'measurement assertion missing')
        require(len(cell['samples']) == 5, 'measurement sample missing')
        for sample in cell['samples']:
            require(sample['process_elapsed_seconds'] >= 0 and sample['process_peak_memory_kib'] > 0, 'invalid process measurement')
        driver = session.evidence / (cell['kind'] + '.mgn')
        require(driver.is_file() and hashlib.sha256(driver.read_bytes()).hexdigest() == cell['entry_sha256'], 'measurement driver mismatch')
    return {'artifact': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'cells': len(cells)}

def coverage(session):
    observed = {}
    for row in session.records:
        key = (row['name'], row['backend'])
        require(key not in observed, 'duplicate external record: ' + str(key))
        require(row.get('passed') is True, 'external case not passed: ' + str(key))
        require(row['result']['exit'] == EXPECT['case_exits'].get('|'.join(key)), 'external exit mismatch: ' + str(key))
        for name in row.get('trace_files', []):
            path = session.evidence / name
            require(path.is_file() and path.stat().st_size > 0, 'missing syscall trace: ' + name)
        observed[key] = row
    unit = observed.get(('mognitio-tests', 'mgn-test'))
    require(unit is not None, 'missing Mognitio test execution')
    tests = parse_tests(unit['result'])
    require(unit.get('tests') == tests, 'test identity evidence mismatch')
    for project in ['levi', 'compiler']:
        require(re.fullmatch('[0-9a-f]{40}', session.metadata.get(project + '_commit', '')) is not None, 'missing revision: ' + project)
        require(bool(session.metadata.get(project + '_files_sha256')), 'missing source manifest: ' + project)
    require(bool(session.metadata.get('initial_v013_trial')), 'missing initial baseline disposition')
    require(session.metadata['build']['exit'] == 0 and re.fullmatch('[0-9a-f]{64}', session.metadata['executable_sha256']) is not None, 'missing successful native build')
    rows = []
    for cl, obligation in EXPECT['conformance'].items():
        for name in obligation['tests']:
            require(name in tests, 'missing required Mognitio test: ' + name)
        for pair in obligation['cases']:
            key = tuple(pair)
            require(key in observed and cl in observed[key]['cl'], 'missing required external case: ' + str(pair))
        rows.append({'id': cl, 'm_scope': obligation['m_scope'], 'mognitio_tests': obligation['tests'],
                     'external_cases': obligation['cases'], 'result': 'pass', 'required_unverified': []})
    require(('text-measurements', 'native-measurement') in observed, 'missing measurement execution')
    measurement = measurements(session)
    designs = []
    for dl, names in EXPECT['design'].items():
        require(all(name in tests for name in names), 'missing design test: ' + dl)
        designs.append({'id': dl, 'mognitio_tests': names, 'artifact': measurement if dl == 'DL001-12' else 'mognitio-tests', 'result': 'pass'})
    return {'conformance': rows, 'design': designs,
            'scope_limits': ['Fixed Linux amd64 environment; no TOCTOU protection.',
                             'Injected failures are artificial; skipped close does not prove descriptor release.',
                             'Measurements include startup/setup/assertions/GC; no time or memory bound.']}
