#!/usr/bin/env python3
"""Bounded investigation of native scalar scanning cost, separate from acceptance."""
import argparse, json, shutil, subprocess
from verify import Session, digest

def main():
    if not __debug__: raise SystemExit('Do not disable verification assertions')
    p=argparse.ArgumentParser();p.add_argument('--compiler',type=__import__('pathlib').Path,required=True);p.add_argument('--evidence',type=__import__('pathlib').Path,required=True);p.add_argument('--timeout',type=float,default=10);args=p.parse_args()
    s=Session(args.compiler,args.evidence)
    try:
        s.slot.mkdir();project=s.root/'stress';(project/'src/Core').mkdir(parents=True)
        (project/'mognitio.toml').write_text('[project]\nname="levi"\nroot_namespace="Levi"\n')
        for name in ['model.mgn','text.mgn']: shutil.copy2(s.project/'src/Core'/name,project/'src/Core'/name)
        source=r'''namespace Levi;
use Std\Io\{readTextFile,IoError};
use Levi\Core\{validTitle};
let main:Function(List<String>):Int=function(args:List<String>):Int{
    let text:String=branch on readTextFile("input"){Result<String,IoError>::Ok(value:String)=>value,Result<String,IoError>::Err=>panic{"input"}};
    var n:Int=0;loop while(n<32){assert validTitle(text);n=n+1;};0
};
'''
        (project/'src/levi.mgn').write_text(source);(s.evidence/'driver.mgn').write_text(source)
        data=('abcdef09'*2048).encode();(project/'input').write_bytes(data);(s.evidence/'input').write_bytes(data)
        built=s.command([s.mgn,'build',project/'mognitio.toml','-o',project/'scan'],cwd=project);assert built['exit']==0,built
        report={'scalars':16384,'iterations':32,'input_sha256':digest(data),'driver_sha256':digest(source.encode()),'timeout_seconds':args.timeout,'build':built}
        try: report['native']=s.command([project/'scan'],cwd=project,timeout=args.timeout);report['outcome']='completed'
        except subprocess.TimeoutExpired: report['native']=s.last_interrupted;report['outcome']='timeout'
        # Same exact production helper and fixture on the host interpreter.
        report['host']=s.command([s.mgn,'run',project/'mognitio.toml'],cwd=project,timeout=90)
        assert report['host']['exit']==0,report
        (s.evidence/'stress.json').write_text(json.dumps(report,indent=2)+'\n');print(report['outcome'],s.evidence)
    finally:s.close()

if __name__=='__main__':main()
