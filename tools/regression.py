#!/usr/bin/env python3
"""Negative controls for the observer itself, including real empty/missing suites."""
import argparse, copy, json, tempfile
from pathlib import Path
from types import SimpleNamespace
from evidence import EXPECT, coverage, parse_tests
from verify import Session, runtime_checks, digest

CHECKS=[]

def rejected(action, name):
    try:
        action()
    except (ValueError, KeyError, FileNotFoundError):
        CHECKS.append(name)
        print('PASS reject ' + name)
        return
    raise AssertionError('incorrectly accepted ' + name)

def main():
    if not __debug__: raise SystemExit("Do not disable verification assertions")
    p=argparse.ArgumentParser()
    for key in ['compiler','evidence']: p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args(); source=json.loads((a.evidence/'results.json').read_text())
    s=SimpleNamespace(metadata=source['metadata'],records=source['records'],evidence=a.evidence)
    coverage(s)
    unit=next(r for r in s.records if r['name']=='mognitio-tests')
    def output(lines): return {'exit':0,'stderr':'','stdout':('\n'.join(lines)+'\n').encode().hex()}
    lines=bytes.fromhex(unit['result']['stdout']).decode().splitlines()
    rejected(lambda:parse_tests(output(['tests: total=0 passed=0 failed=0 errors=0 aborted=0 not_run=0'])),'empty summary')
    rejected(lambda:parse_tests(output(lines[1:])),'missing identity')
    rejected(lambda:parse_tests(output([lines[0]]+lines)),'duplicate identity')
    rejected(lambda:parse_tests(output([lines[0].replace('PASS ','FAIL ')]+lines[1:])),'failed individual test')
    for label,edit in [
        ('missing M execution',lambda r:[x for x in r if x['name']!='mognitio-tests']),
        ('missing external case',lambda r:[x for x in r if not (x['name']=='usage-escaped' and x['backend']=='native')]),
        ('missing measurement execution',lambda r:[x for x in r if x['name']!='text-measurements'])]:
        bad=SimpleNamespace(metadata=s.metadata,records=edit(copy.deepcopy(s.records)),evidence=s.evidence)
        rejected(lambda:coverage(bad),label)
    with tempfile.TemporaryDirectory(prefix='levi-evidence-negative-') as directory:
        target=Path(directory)
        for file in s.evidence.iterdir():
            if file.is_file() and file.name!='measurements.json': (target/file.name).symlink_to(file.resolve())
        bad=SimpleNamespace(metadata=s.metadata,records=s.records,evidence=target)
        rejected(lambda:coverage(bad),'missing measurement artifact')
        report=json.loads((s.evidence/'measurements.json').read_text());report['results'][0]['assertions_passed']=False
        (target/'measurements.json').write_text(json.dumps(report))
        rejected(lambda:coverage(bad),'failed measurement assertion')
    # Exercise compiler discovery on disposable source copies, not synthetic summaries alone.
    for mode in ['empty','missing-one']:
        session=Session(a.compiler,a.evidence/('negative-'+mode))
        try:
            session.slot.mkdir()
            files=sorted((session.project/'src/Tests').glob('*.mgn'))
            if mode=='empty':
                for file in files: file.write_text(file.read_text().replace('@test ',''))
            else:
                file=session.project/'src/Tests/parsing.mgn'
                file.write_text(file.read_text().replace('@test let usageDiagnostics','let usageDiagnostics'))
            session.metadata['negative_control']=mode
            session.metadata['modified_source_sha256']={str(p.relative_to(session.project)):digest(p.read_bytes()) for p in (session.project/'src').rglob('*.mgn')}
            session.save()
            rejected(lambda:runtime_checks(session),mode+' compiler suite')
            require_output=bytes.fromhex(session.last_command['stdout']).decode()
            expected=0 if mode=='empty' else len(EXPECT['tests'])-1
            assert f'total={expected} passed={expected} failed=0' in require_output
            (session.evidence/'discovery.json').write_text(json.dumps(session.last_command,indent=2)+'\n')
        finally:session.close()
    (a.evidence/'regression-results.json').write_text(json.dumps({'checks':CHECKS,'passed':len(CHECKS),'product_commit':s.metadata['levi_commit'],'compiler_commit':s.metadata['compiler_commit']},indent=2)+'\n')
    print(f'PASS negative controls ({len(CHECKS)})')

if __name__=='__main__':main()
