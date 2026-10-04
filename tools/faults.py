"""Externally calibrated syscall failures, never compiler-private test hooks."""
from pathlib import Path
import re, subprocess
from verify import snapshot

LINE=re.compile(r'^(\d+)\s+(\w+)\(')
def syscalls(text):
    counts={};rows=[];pending={}
    for line in text.splitlines():
        resumed=re.match(r'^(\d+)\s+<\.\.\. (\w+) resumed>(.*)',line)
        if resumed:
            pid,call,rest=resumed.groups()
            if (pid,call) in pending:
                ordinal,prefix=pending.pop((pid,call));rows.append((pid,call,ordinal,prefix+rest))
            continue
        found=LINE.match(line)
        if not found: continue
        pid,call=found.groups();key=(pid,call);counts[key]=counts.get(key,0)+1
        if '<unfinished ...>' in line: pending[key]=(counts[key],line.split('<unfinished ...>')[0])
        else: rows.append((pid,call,counts[key],line))
    return rows

def kept(p,reference): reference(p);(p/'public').mkdir();(p/'public/keep').write_bytes(b'unchanged')
def three(p,reference):
    reference(p);(p/'content/z.page').write_text('title=Later\n\nNever write this')

def inject(s,name,setup,selector,errno,code,category,fields,unchanged=False,partial=False):
    observed=[]
    for backend in ['run','native']:
        s.prepare(setup);before=snapshot(s.slot)
        trace=s.evidence/(name+'-'+backend+'-baseline.trace')
        command=s.argv(backend,['build','site.cfg'])
        filters=[]
        if partial:
            for file in ['about.html','home.html','z.html']: filters+=['-P',s.slot/'public'/file]
        elif name=='stderr': filters=['--trace-fds=2']
        baseline=s.command(['strace','-f','-yy','-s','256',*filters,'-o',trace,*command],timeout=180)
        rows=syscalls(trace.read_text());chosen=[row for row in rows if selector(row[1],row[3],s.slot)]
        assert chosen,(name,backend,'no target syscall')
        pid,call,ordinal,line=chosen[0]
        s.prepare(setup);assert before==snapshot(s.slot)
        injected=s.evidence/(name+'-'+backend+'-injected.trace')
        result=s.command(['strace','-f','-yy','-s','256',*filters,'-o',injected,'-e',f'inject={call}:error={errno}:when={ordinal}',*command],timeout=180)
        text=injected.read_text();hits=[row for row in syscalls(text) if '(INJECTED)' in row[3]]
        assert len(hits)==1 and selector(hits[0][1],hits[0][3],s.slot),(name,backend,'wrong injection',hits,line)
        err=bytes.fromhex(result['stderr']);assert result['exit']==code and result['stdout']=='',(name,backend,result)
        if category:
            diagnostic=err.decode();assert diagnostic.startswith('levi: '+category+':') and diagnostic.count('\n')==1,(name,diagnostic)
            for field in fields: assert field in diagnostic,(name,diagnostic,fields)
        else: assert err==b'',(name,err)
        after=snapshot(s.slot)
        if unchanged:
            assert before==after,(name,'output modified')
            writes=[row for row in syscalls(text) if row[1] in ['mkdir','mkdirat'] or (row[1] in ['open','openat'] and 'public/' in row[3] and 'O_WRONLY' in row[3])]
            assert not writes,(name,'publish reached',writes)
        if partial:
            assert sorted(p.name for p in (s.slot/'public').iterdir())==['about.html','home.html']
            assert (s.slot/'public/about.html').read_bytes()==(s.project/'fixtures/golden/about.html').read_bytes()
            if name=='write-close': assert (s.slot/'public/home.html').read_bytes()==(s.project/'fixtures/golden/home.html').read_bytes()
            else: assert (s.slot/'public/home.html').read_bytes()==b''
        s.record(name,[23] if partial else [25] if name=='stderr' else [32,36,37],backend,result,before,after,
            {'calibration':{'syscall':call,'ordinal':ordinal,'baseline_line':line,'injected_line':hits[0][3]},
             'trace_files':[trace.name,injected.name], 'fault_model':'skipped syscall returns '+errno+'; close does not prove fd release',
             'natural_reproduction':False})
        observed.append((result['exit'],err,after))
    assert observed[0]==observed[1],(name,'backend difference')

def verify_faults(s):
    reference=s.reference
    keep_fixture=lambda p:kept(p,reference)
    three_fixture=lambda p:three(p,reference)
    s.metadata['strace']=subprocess.check_output(['strace','--version'],text=True).splitlines()[0];s.save()
    output_fd=lambda line,p:'<'+str(p/'public')+'>' in line
    inject(s,'output-body',keep_fixture,lambda call,line,p:call=='getdents64' and output_fd(line,p),'ENOENT',1,'io',
           ['operation=ReadDirectory','kind=NotFound','subject="./public"','phase=Body'],unchanged=True)
    inject(s,'output-cleanup',keep_fixture,lambda call,line,p:call=='close' and output_fd(line,p),'ENOENT',1,'io',
           ['operation=ReadDirectory','kind=NotFound','subject="./public"','phase=Cleanup'],unchanged=True)
    inject(s,'output-metadata',keep_fixture,lambda call,line,p:call=='newfstatat' and output_fd(line,p) and '"keep"' in line,'ENOENT',1,'io',
           ['operation=ReadDirectory','kind=NotFound','subject="./public/keep"','phase=Body'],unchanged=True)
    inject(s,'write-body',three_fixture,lambda call,line,p:call=='write' and '<'+str(p/'public/home.html')+'>' in line,'EIO',1,'io',
           ['operation=WriteTextFile','kind=Other','subject="./public/home.html"','phase=Body'],partial=True)
    inject(s,'write-close',three_fixture,lambda call,line,p:call=='close' and '<'+str(p/'public/home.html')+'>' in line,'EIO',1,'io',
           ['operation=WriteTextFile','kind=Other','subject="./public/home.html"','phase=Cleanup'],partial=True)
    inject(s,'stderr',keep_fixture,lambda call,line,p:call=='write' and re.search(r'write\(2(?:<|,)',line) is not None and 'levi:' in line,'EPIPE',1,None,[],unchanged=True)
    # Real missing-root counterpart: same operation/kind/subject, Target enables publication.
    s.pair('target-missing-counterpart',[19,36,37],reference,expected={p.name:p.read_bytes() for p in (s.project/'fixtures/golden').glob('*.html')})
