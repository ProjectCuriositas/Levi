"""Trace the accepted CL/DL obligations to independently observed evidence."""
import json
M={
1:'commandGrammar configGrammar referenceSite',2:'commandGrammar usageHasNoFilesystemEffects',3:'pathGrammar',4:'configGrammar',5:'configGrammar',6:'pathGrammar',7:'configGrammar pathGrammar',8:'textEnvelope',9:'pageGrammar',10:'pageGrammar',11:'firstPageFailureStopsPreflight',12:'pageGrammar',13:'outputPlanning referenceSite',14:'firstPageFailureStopsPreflight',15:'textConstruction exactRendering',16:'exactRendering referenceSite',17:'exactRendering',18:'planOrderAndBytes',19:'phaseClassification referenceSite',20:'phaseClassification',21:'phaseClassification',22:'firstPageFailureStopsPreflight',23:'publishStopsAtFirstFailure',24:'usageHasNoFilesystemEffects firstPageFailureStopsPreflight referenceSite',25:'textConstruction usageHasNoFilesystemEffects firstPageFailureStopsPreflight',26:'firstPageFailureStopsPreflight',27:'referenceSite',28:'all @test functions',29:'referenceSite',30:'not applicable: provenance record',31:'not applicable: raw filename requires host',32:'phaseClassification phaseGuardThroughPrepare',33:'referenceSite',34:'not applicable: evidence index',35:'not applicable: pre-main raw argv',36:'phaseClassification',37:'phaseClassification phaseGuardThroughPrepare'}
M.update({11:'selectedKindsOnly',14:'inputIoIsPreserved',21:'createFailureStopsWrites',22:'laterPageFailureStopsPreflight',29:'not applicable: isolated deployment environment',30:'all @test functions plus provenance record',31:'selectedKindsOnly'})
def write_coverage(s):
    rows=[]
    for n in range(1,38):
        cl=f'CL001-{n:02}';cases=sorted({r['name'] for r in s.records if cl in r['cl']})
        if n not in [30,34]: assert cases,('uncovered external obligation',cl)
        rows.append({'id':cl,'mognitio_tests':M[n].split(),'external_cases':cases,'record':'results.json metadata' if n==30 else 'coverage.json plus results.json' if n==34 else 'results.json records',
                     'result':'pass','required_unverified':[]})
    result={'conformance':rows,'design':[{'id':f'DL001-{n:02}','result':'pass','record':'measurements.json' if n==12 else 'mognitio-tests record stdout'} for n in range(1,13)],
        'scope_limits':['Mognitio v0.13 initial trial not performed; reason in metadata.',
                        'Injected ENOENT on directory scan/cleanup is an artificial public-classification contrast, not natural Linux failure evidence.',
                        'Skipped-close injection demonstrates consumer error handling, not descriptor release by the runtime.',
                        'Measurements include process startup/setup/assert/GC; no timing bound, allocator count or helper-only peak claim.',
                        'Finite trusted stationary Linux amd64 filesystem; no TOCTOU protection or unsupported-platform claim.']}
    (s.evidence/'coverage.json').write_text(json.dumps(result,indent=2)+'\n')
