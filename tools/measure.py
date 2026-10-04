"""Separate native process measurements for scanning and prepared fragment assembly."""
from pathlib import Path
import json, shutil, statistics
from verify import ROOT, digest

def measure(s):
    project=s.root/'measurement';(project/'src/Core').mkdir(parents=True)
    (project/'mognitio.toml').write_text('[project]\nname="levi"\nroot_namespace="Levi"\n')
    copied={}
    for name in ['model.mgn','text.mgn']:
        source=ROOT/'src/Core'/name;shutil.copy2(source,project/'src/Core'/name);copied[name]=digest(source.read_bytes())
    results=[];repetitions=4
    for kind in ['scan-control','scan','join-control','join']:
        setup='let parts:List<String>=text->scalars();' if kind.startswith('join') else ''
        operation={'scan-control':'assert text->length()==expected;', 'scan':'assert validTitle(text);',
                   'join-control':'assert parts->length()==expected;', 'join':'assert assembleFragments(parts)==text;'}[kind]
        source=r'''namespace Levi;
use Std\Io\{readTextFile,IoError};
use Levi\Core\{validTitle,assembleFragments};
let main:Function(List<String>):Int=function(args:List<String>):Int{
    let text:String=branch on readTextFile("input"){Result<String,IoError>::Ok(value:String)=>value,Result<String,IoError>::Err=>panic{"input"}};
    let expected:Int=text->length();
'''+setup+f'var n:Int=0;loop while(n<{repetitions}){{{operation}n=n+1;}};0\n}};\n'
        entry=project/'src/levi.mgn';entry.write_text(source)
        (s.evidence/(kind+'.mgn')).write_text(source)
        image=project/kind
        result=s.command([s.mgn,'build',project/'mognitio.toml','-o',image],cwd=project,timeout=240);assert result['exit']==0,result
        for shape,pattern in [('ascii','abcdef09'),('unicode','日😀e\u0301<&>\"')]:
            for size in [256,1024,4096]:
                text=(pattern*((size+len(pattern)-1)//len(pattern)))[:size]
                (project/'input').write_text(text)
                # Check both runtime backends; measure only the independent native process.
                checked=s.command([s.mgn,'run',project/'mognitio.toml'],cwd=project);assert checked['exit']==0 and checked['stdout']==checked['stderr']=='',checked
                samples=[]
                for trial in range(5):
                    timer=project/'time.txt'
                    run=s.command(['/usr/bin/time','-f','%e %M','-o',timer,image],cwd=project)
                    assert run['exit']==0 and run['stdout']==run['stderr']=='',run
                    elapsed,peak=timer.read_text().split()
                    samples.append({'process_elapsed_seconds':run['process_elapsed_seconds'],'process_peak_memory_kib':int(peak)})
                row={'kind':kind,'shape':shape,'scalars':size,'utf8_bytes':len(text.encode()),'iterations':repetitions,'samples':samples,
                    'median_process_elapsed_seconds':statistics.median(v['process_elapsed_seconds'] for v in samples),
                    'max_process_peak_memory_kib':max(v['process_peak_memory_kib'] for v in samples),
                    'input_sha256':digest(text.encode()),'entry_sha256':digest(source.encode()),'assertions_passed':True}
                results.append(row)
                (s.evidence/'measurements-progress.json').write_text(json.dumps(results,indent=2)+'\n')
    # Difference is only an estimate; retain negative/noisy values and all process peaks.
    for row in results:
        if row['kind'] in ['scan','join']:
            control=next(c for c in results if c['kind']==row['kind']+'-control' and c['shape']==row['shape'] and c['scalars']==row['scalars'])
            row['helper_elapsed_estimate_seconds_per_iteration']=(row['median_process_elapsed_seconds']-control['median_process_elapsed_seconds'])/repetitions
    report={'module_sha256':copied,'results':results,
        'boundary':'Process time includes startup, read, scalar/fragment setup, assertions, GC. Build and fixture generation excluded. Controls match setup. Assembly setup happens before repeated join. No peak subtraction; no wall-clock complexity guarantee.',
        'measurement_tool':'Python monotonic and GNU time maximum resident set size; five native processes per cell'}
    (s.evidence/'measurements.json').write_text(json.dumps(report,indent=2)+'\n')
    s.record('text-measurements',[], 'native-measurement',{'exit':0,'command':'tools/measure.py via tools/verify.py'}, {},{},
             {'dl':['DL001-12'],'evidence':'measurements.json','cells':len(results),'native_processes':len(results)*5,'host_assertion_runs':len(results)})
