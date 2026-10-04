#!/usr/bin/env python3
"""Lévi's external fixture/process observer; product semantics remain in Mognitio."""
from pathlib import Path
import argparse, base64, hashlib, json, os, platform, shutil, signal, stat, subprocess, tempfile, time

ROOT = Path(__file__).resolve().parents[1]
def digest(data): return hashlib.sha256(data).hexdigest()
def git(path, *args): return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()
def snapshot(root):
    result = {}
    if not root.exists(): return result
    def visit(folder):
        try: entries=sorted(os.scandir(folder), key=lambda x: os.fsencode(x.name))
        except PermissionError:
            result[os.fsencode(str(folder.relative_to(root))).hex()+':unreadable']={'enumeration':'PermissionDenied'}
            return
        for item in entries:
            p = Path(item.path); info = item.stat(follow_symlinks=False)
            key = os.fsencode(str(p.relative_to(root))).hex()
            row = {'mode': stat.S_IMODE(info.st_mode), 'kind': stat.S_IFMT(info.st_mode)}
            if item.is_symlink(): row['link'] = os.fsencode(os.readlink(p)).hex()
            elif item.is_file(follow_symlinks=False): row['bytes'] = p.read_bytes().hex()
            elif item.is_dir(follow_symlinks=False): visit(p)
            result[key] = row
    visit(root)
    return result

class Session:
    def __init__(self, compiler, evidence):
        self.levi = ROOT
        self.compiler = compiler.resolve(); self.mgn = self.compiler/'bin/mgn'
        self.evidence = evidence.resolve()
        self.evidence.mkdir(parents=True, exist_ok=False)
        self.root = Path(tempfile.mkdtemp(prefix='levi-v001-')).resolve()
        self.slot = self.root/'slot'; self.project = self.root/'project'; self.image = self.root/'levi'
        self.project.mkdir()
        for name in git(self.levi,'ls-files').splitlines():
            source=self.levi/name
            if name=='mognitio.toml' or name.startswith(('src/','sample/','fixtures/golden/')):
                target=self.project/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        self.manifest = self.project/'mognitio.toml'; self.records = []; self.active = None
        self.metadata = {'levi_commit': git(self.levi,'rev-parse','HEAD'), 'levi_dirty': git(self.levi,'status','--porcelain'),
            'compiler_commit': git(self.compiler,'rev-parse','HEAD'), 'compiler_dirty': git(self.compiler,'status','--porcelain'),
            'python': platform.python_version(), 'host': platform.uname()._asdict(),
            'uid': os.geteuid(), 'initial_v013_trial': 'not run: accepted v0.14 design uses phase/scalars/join; no old-version port',
            'source_sha256': {str(p.relative_to(self.project)):digest(p.read_bytes()) for p in sorted((self.project/'src').rglob('*.mgn'))}}
        for label,repo in [('levi',self.levi),('compiler',self.compiler)]:
            files=git(repo,'ls-files','--cached','--others','--exclude-standard').splitlines()
            self.metadata[label+'_files_sha256']={name:digest((repo/name).read_bytes()) for name in sorted(set(files)) if (repo/name).is_file()}
        assert os.geteuid() != 0, 'permission fixtures require a non-root user'
        self.save()
    def reference(self,p): shutil.copytree(self.project/'sample',p,dirs_exist_ok=True)
    def save(self):
        (self.evidence/'results.json').write_text(json.dumps({'metadata':self.metadata,'records':self.records},ensure_ascii=True,indent=2)+'\n')
    def command(self, argv, cwd=None, timeout=90):
        argv=[os.fspath(x) for x in argv]; cwd=cwd or self.slot
        started=time.monotonic(); self.active=subprocess.Popen(argv,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        try:
            out,err=self.active.communicate(timeout=timeout); code=self.active.returncode
        except BaseException:
            os.killpg(self.active.pid,signal.SIGKILL);out,err=self.active.communicate()
            self.last_interrupted={'argv':[os.fsdecode(x) for x in argv],'cwd':str(cwd),'exit':self.active.returncode,'stdout':out.hex(),'stderr':err.hex(),'interrupted':True}
            raise
        finally: self.active=None
        self.last_command={'argv':[os.fsdecode(x) for x in argv], 'cwd':str(cwd), 'exit':code,
                'stdout':out.hex(),'stderr':err.hex(),'process_elapsed_seconds':time.monotonic()-started}
        return self.last_command
    def remove(self,path):
        # Only owned descendants; symlink roots are unlinked without following their target.
        assert path.parent.resolve().is_relative_to(self.root) and path != self.root
        if path.is_symlink(): path.unlink();return
        assert path.resolve().is_relative_to(self.root)
        if path.exists():
            for parent,dirs,files in os.walk(path,followlinks=False):
                os.chmod(parent,0o700)
                for name in dirs:
                    child=Path(parent)/name
                    if not child.is_symlink(): os.chmod(child,0o700)
            shutil.rmtree(path)
    def prepare(self,setup):
        self.remove(self.slot);self.slot.mkdir();setup(self.slot)
    def argv(self,backend,args):
        return ([self.mgn,'run',self.manifest,'--'] if backend=='run' else [self.image])+list(args)
    def record(self,name,cl,backend,result,before,after,extra=None):
        row={'name':name,'cl':[f'CL001-{n:02}' for n in cl], 'backend':backend,'result':result,'initial':before,'final':after,'passed':True}
        if extra: row.update(extra)
        self.records.append(row);self.save()
    def pair(self,name,cl,setup,args=('build','site.cfg'),code=0,category=None,expected=None,subject=None,io=None,unchanged=False):
        comparison=[];initial=None
        for backend in ('run','native'):
            self.prepare(setup);before=snapshot(self.slot)
            if initial is None: initial=before
            else: assert initial==before,(name,'initial mismatch')
            result=self.command(self.argv(backend,args));after=snapshot(self.slot)
            out=bytes.fromhex(result['stdout']);err=bytes.fromhex(result['stderr'])
            assert result['exit']==code and out==b'',(name,backend,result)
            if category:
                diagnostic=err.decode('utf-8');assert diagnostic.startswith('levi: '+category+':') and diagnostic.count('\n')==1 and diagnostic.endswith('\n'),(name,diagnostic)
                if subject: assert subject in diagnostic,(name,diagnostic,subject)
                if io:
                    for key,value in io.items(): assert key+'='+value in diagnostic,(name,diagnostic,io)
            else: assert err==b'',(name,err)
            if unchanged: assert before==after,(name,'filesystem changed')
            if expected is not None:
                output=self.slot/'public'
                assert output.is_dir() and sorted(p.name for p in output.iterdir())==sorted(expected),(name,list(output.iterdir()))
                for file,data in expected.items(): assert (output/file).read_bytes()==data,(name,file)
            comparison.append((result['exit'],out,err,after))
            self.record(name,cl,backend,result,before,after)
        assert comparison[0]==comparison[1],(name,'backend difference',comparison)
    def close(self):
        if self.active:
            os.killpg(self.active.pid,signal.SIGKILL);self.active.communicate();self.active=None
        for child in self.root.iterdir():
            if child.is_dir() and not child.is_symlink(): self.remove(child)
            else: child.unlink()
        self.root.rmdir()

def change_config(p,data): (p/'site.cfg').write_bytes(data if isinstance(data,bytes) else data.encode())
def config_case(data,reference):
    def setup(p): reference(p);change_config(p,data)
    return setup
def page_case(data,reference):
    def setup(p): reference(p);(p/'content/home.page').write_bytes(data if isinstance(data,bytes) else data.encode())
    return setup

def ordinary(s):
    reference=s.reference
    config_fixture=lambda data: config_case(data,reference)
    page_fixture=lambda data: page_case(data,reference)
    gold={p.name:p.read_bytes() for p in (s.project/'fixtures/golden').glob('*.html')}
    s.pair('reference',[1,8,13,15,16,18,19,24,27],reference,expected=gold)
    s.pair('repeat-reference',[17,33],reference,expected=gold)
    for n,args in enumerate([[],['build'],['help','site.cfg'],['Build','site.cfg'],['build',''],['build','site.cfg','extra']]):
        s.pair(f'usage-{n}',[2,24],reference,args,2,'usage',subject=('invalid argument count \"arguments\"' if n in [0,1,5] else 'empty config path \"\"' if n==4 else 'unknown command \"'+args[0]+'\"'),unchanged=True)
    s.pair('usage-escaped',[2,24,25],reference,['bad\n\"\\\u2028','site.cfg'],2,'usage',subject='unknown command \"bad\\n\\\"\\\\\\u{2028}\"',unchanged=True)
    for n,text in enumerate(['output=public\n\ninput=content\ntitle= S=1 ', 'title="S"\ninput=content\noutput=public\n']):
        title=' S=1 ' if n==0 else '&quot;S&quot;'
        expected={k:v.replace('小さなサイト'.encode(),title.encode()) for k,v in gold.items()}
        s.pair(f'config-order-{n}',[1,4,5],config_fixture(text),expected=expected)
    bad=['title=A\ninput=content','title=A\ninput=content\noutput=public\nx=y','title=A\ntitle=B\ninput=content\noutput=public',
         'title=\ninput=content\noutput=public','title= \ninput=content\noutput=public','title=A\tB\ninput=content\noutput=public',
         ' title=A\ninput=content\noutput=public','title=A\ninput=content\noutput=public\n# comment']
    for n,text in enumerate(bad): s.pair(f'bad-config-{n}',[5,24],config_fixture(text),code=1,category='config',unchanged=True)
    for n,path in enumerate(['/public','p//q','p/','p/../q','p/./q','P','p q','p\\q','日','_p','']):
        s.pair(f'bad-path-{n}',[6],config_fixture('title=S\ninput=content\noutput='+path),code=1,category='config',unchanged=True)
    for n,path in enumerate(['content','content/child']): s.pair(f'overlap-{n}',[7],config_fixture('title=S\ninput=content\noutput='+path),code=1,category='config',unchanged=True)
    s.pair('ancestor-input',[7],config_fixture('title=S\ninput=public/child\noutput=public'),code=1,category='config',unchanged=True)
    def prefix(p): reference(p);(p/'content').rename(p/'public2');change_config(p,'title=小さなサイト\ninput=public2\noutput=public')
    s.pair('prefix-only',[7],prefix,expected=gold)
    def spaces(p):
        folder=p/'space dir';folder.mkdir();reference(folder)
        (p/'public').symlink_to('space dir/public',target_is_directory=True)
    s.pair('spaced-config',[3],spaces,args=['build','space dir/site.cfg'],expected=gold)
    def config_link(p):
        reference(p);(p/'elsewhere').mkdir();(p/'site.cfg').rename(p/'elsewhere/real.cfg');(p/'site.cfg').symlink_to('elsewhere/real.cfg')
    s.pair('lexical-symlink-base',[3],config_link,expected=gold)
    def crlf(p):
        reference(p)
        for file in [p/'site.cfg',*sorted((p/'content').glob('*.page'))]: file.write_bytes(file.read_bytes().replace(b'\n',b'\r\n'))
    s.pair('crlf',[8],crlf,expected=gold)
    for n,data in enumerate([b'\xff',b'\xef\xbb\xbf'+(s.project/'sample/site.cfg').read_bytes(),b'title=S\rinput=c\noutput=p',b'title=S\x00\ninput=c\noutput=p']):
        s.pair(f'config-envelope-{n}',[8,26],config_fixture(data),code=1,category='io' if n==0 else 'config',unchanged=True)
    for n,data in enumerate([b'\xff',b'\xef\xbb\xbftitle=T\n\n',b'title=T\n\nx\r',b'title=T\n\n\x7f',b'title=T\n\n\r\r\n']):
        s.pair(f'page-envelope-{n}',[8,26],page_fixture(data),code=1,category='io' if n==0 else 'content',unchanged=True)
    for n,data in enumerate(['','title=\n\n','title=T','title=T\n','title=T\n \nbody']):
        s.pair(f'page-grammar-{n}',[9],page_fixture(data),code=1,category='content',unchanged=True)
    for n,body in enumerate(['','\n\ttitle=\'x\'\n','日本😀e\u0301\ufeff','&<>"\'&amp;']):
        encoded=['','\n\ttitle=&#39;x&#39;\n','日本😀e\u0301\ufeff','&amp;&lt;&gt;&quot;&#39;&amp;amp;'][n]
        expected=dict(gold);expected['home.html']=gold['home.html'].replace(b'&lt;hello&gt;',encoded.encode())
        s.pair(f'body-{n}',[9,10,15,16],page_fixture('title=Home & More\n\n'+body),expected=expected)
    def selection(p):
        reference(p);(p/'content/Bad.page').symlink_to('missing');(p/'content/BadDir.page').mkdir();os.mkfifo(p/'content/BadPipe.page');(p/'content/bad.PAGE').write_bytes(b'\xff')
    s.pair('entry-selection',[11,12],selection,expected=gold)
    for name in ['.page','About.page','a_b.page','a--b.page']:
        def stem(p,name=name): reference(p);(p/'content'/name).write_text('title=T\n\n')
        s.pair('stem-'+name,[12],stem,code=1,category='content',subject=name,unchanged=True)
    def empty(p): reference(p);[(p/'content'/name).unlink() for name in ['about.page','home.page']]
    s.pair('empty',[13],empty,code=1,category='empty-input',unchanged=True)
    def one(p): reference(p);(p/'content/about.page').unlink()
    s.pair('one',[13],one,expected={'home.html':gold['home.html']})
    def input_missing(p): reference(p);(p/'content').rename(p/'other')
    def input_file(p): input_missing(p);(p/'content').write_text('file')
    def input_permission(p): reference(p);(p/'content').chmod(0)
    for name,setup in [('missing',input_missing),('file',input_file),('permission',input_permission)]:
        s.pair('input-'+name,[14,36],setup,code=1,category='io',unchanged=True)
    def existing_empty(p): reference(p);(p/'public').mkdir()
    s.pair('existing-empty',[19],existing_empty,expected=gold)
    for kind in ['file','dotfile','directory','symlink','generated']:
        def nonempty(p,kind=kind):
            existing_empty(p)
            if kind=='directory': (p/'public/nested').mkdir()
            elif kind=='symlink': (p/'public/link').symlink_to('../content/home.page')
            else: (p/'public'/({'dotfile':'.keep','generated':'home.html'}.get(kind,'keep'))).write_bytes(b'kept')
        s.pair('nonempty-'+kind,[20,24],nonempty,code=1,category='output-not-empty',unchanged=True)
    s.pair('missing-output-parent',[21],config_fixture('title=S\ninput=content\noutput=missing/public'),code=1,category='io',io={'operation':'CreateDirectory','phase':'Target','kind':'NotFound'},unchanged=True)
    def bad_parent(p): reference(p);change_config(p,'title=S\ninput=content\noutput=parent/public');(p/'parent').write_text('file')
    s.pair('file-output-parent',[21],bad_parent,code=1,category='io',unchanged=True)
    def output_file(p): reference(p);(p/'public').write_text('file')
    s.pair('output-file',[21],output_file,code=1,category='io',unchanged=True)
    def mkdir_permission(p): reference(p);(p/'locked').mkdir();(p/'locked').chmod(0o500);change_config(p,'title=S\ninput=content\noutput=locked/public')
    s.pair('mkdir-permission',[21],mkdir_permission,code=1,category='io',io={'operation':'CreateDirectory','kind':'PermissionDenied'},unchanged=True)
    s.pair('later-invalid',[22,26],page_fixture('invalid'),code=1,category='content',subject='home.page',unchanged=True)
    def first_invalid(p): reference(p);(p/'content/about.page').write_text('invalid');(p/'content/home.page').write_bytes(b'\xff')
    s.pair('first-invalid',[26],first_invalid,code=1,category='content',subject='about.page',unchanged=True)
    def raw_name(p): existing_empty(p);fd=os.open(os.fsencode(p/'public')+b'/\xff',os.O_CREAT|os.O_WRONLY,0o600);os.write(fd,b'kept');os.close(fd)
    s.pair('output-invalid-name',[31,32,36],raw_name,code=1,category='io',io={'operation':'ReadDirectory','kind':'InvalidEncoding','phase':'Body'},unchanged=True)
    def output_permission(p): existing_empty(p);(p/'public').chmod(0)
    s.pair('output-permission',[32,36],output_permission,code=1,category='io',io={'operation':'ReadDirectory','kind':'PermissionDenied'},unchanged=True)
    s.pair('control-subject',[25],reference,args=['build','missing\n\r\t\\"\x01\x85\u2028'],code=1,category='io',subject='missing\\n\\r\\t\\\\\\"\\u{1}\\u{85}\\u{2028}',unchanged=True)

def runtime_checks(s):
    reference=s.reference
    s.prepare(reference)
    unit=s.slot/'fixtures/work/reference';unit.parent.mkdir(parents=True);shutil.copytree(s.project/'sample',unit)
    shutil.copy2(s.project/'fixtures/golden/home.html',unit/'home.expected')
    shutil.copy2(s.project/'fixtures/golden/about.html',unit/'about.expected')
    result=s.command([s.mgn,'test',s.manifest],timeout=240)
    from evidence import parse_tests
    tests=parse_tests(result)
    s.record('mognitio-tests',[28], 'mgn-test', result,{},snapshot(s.slot),{'tests':tests})
    for backend in ['run','native']:
        s.prepare(reference);before=snapshot(s.slot)
        result=s.command(s.argv(backend,[b'build',b'\xff']))
        assert result['exit']==2 and not bytes.fromhex(result['stdout']) and b'levi: usage:' not in bytes.fromhex(result['stderr']),result
        assert before==snapshot(s.slot)
        s.record('invalid-utf8-argv',[35],backend,result,before,before)
    s.prepare(reference);before=snapshot(s.slot)
    # Empty mount namespace: no host root, compiler, source, interpreter or libraries.
    argv=['bwrap','--unshare-all','--die-with-parent','--new-session','--ro-bind',s.image,'/levi','--bind',s.slot,'/data','--chdir','/data','/levi','build','site.cfg']
    result=s.command(argv)
    assert result['exit']==0 and result['stdout']==result['stderr']=='',result
    for name in ['home.html','about.html']: assert (s.slot/'public'/name).read_bytes()==(s.project/'fixtures/golden'/name).read_bytes()
    s.record('standalone',[29], 'isolated-native', result,before,snapshot(s.slot),{'namespace_files':['/levi','/data (fixture only)'],'elf':subprocess.check_output(['file',s.image],text=True)})
    # Exercise the exact timeout/kill/reap cleanup path, then rebuild fresh data.
    s.prepare(reference);before=snapshot(s.slot);trace=s.evidence/'interrupted.trace'
    # Stop a real Lévi process while its first output write is externally delayed.
    try: s.command(['strace','-f','-yy','-P',s.slot/'public/about.html','-o',trace,'-e','inject=write:delay_enter=5s:when=1',s.image,'build','site.cfg'],timeout=0.5)
    except subprocess.TimeoutExpired: pass
    else: raise AssertionError('interruption did not occur')
    assert s.active is None and (s.slot/'public/about.html').exists() and 'write(' in trace.read_text()
    s.record('external-interruption',[33],'native',s.last_interrupted,before,snapshot(s.slot),{'trace_files':[trace.name]})
    s.prepare(reference);assert not (s.slot/'public').exists()
    s.pair('after-interruption',[33],reference,expected={p.name:p.read_bytes() for p in (s.project/'fixtures/golden').glob('*.html')})

def main():
    if not __debug__: raise SystemExit('Do not disable verification assertions with -O or PYTHONOPTIMIZE')
    parser=argparse.ArgumentParser();parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--evidence',type=Path,required=True);parser.add_argument('--only',choices=['ordinary','faults','measure','all'],default='all');args=parser.parse_args()
    s=Session(args.compiler,args.evidence)
    try:
        s.slot.mkdir();built=s.command([s.mgn,'build',s.manifest,'-o',s.image],timeout=240)
        assert built['exit']==0,built;s.metadata['build']=built;s.metadata['executable_sha256']=digest(s.image.read_bytes());s.save()
        if args.only in ['ordinary','all']: ordinary(s);runtime_checks(s)
        if args.only in ['faults','all']:
            from faults import verify_faults
            verify_faults(s)
        if args.only in ['measure','all']:
            from measure import measure
            measure(s)
        if args.only=='all':
            from coverage import write_coverage
            write_coverage(s)
        s.metadata['scope']=args.only;s.metadata['complete']=True;s.save();print(f'PASS records={len(s.records)} evidence={s.evidence}',flush=True)
    finally: s.close()

if __name__=='__main__': main()
