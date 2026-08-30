#!/data/data/com.termux/files/usr/bin/env python
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
IDX=ROOT/'frontend/lab/master-assets-v2/index'
POL=IDX/'lastwar-render-fidelity-policy-v1.json'
CERT=IDX/'lastwar-render-certification-v1.json'

def load(p):
    if not p.is_file():raise SystemExit(f'MISSING {p}')
    return json.loads(p.read_text('utf-8'))

def main():
    pol=load(POL);reg=load(CERT)
    print('RENDER_FIDELITY_POLICY',pol.get('target'))
    print('certificates='+str(len(reg.get('certificates',[]))))
    bad_cert=0
    for c in reg.get('certificates',[]):
        st=c.get('status','UNCERTIFIED');root=c.get('root','?')
        print(f'ROOT {root} status={st} recipeAllowed={str(bool(c.get("recipeAllowed"))).lower()}')
        if st=='CERTIFIED_PIXEL_FAITHFUL':
            missing=[]
            if c.get('recipeAllowed') is not True:missing.append('recipeAllowed=true')
            if not c.get('certifiedRecipe'):missing.append('certifiedRecipe')
            if not c.get('evidenceClosure'):missing.append('evidenceClosure')
            if not c.get('visualVerification'):missing.append('visualVerification')
            if c.get('explicitlyNotProven'):missing.append('explicitlyNotProven must be empty')
            if missing:
                bad_cert+=1
                print('INVALID_CERTIFICATE '+', '.join(missing))
        else:
            print('RECIPE_BLOCKED')
            for x in c.get('explicitlyNotProven',[])[:30]:print('  UNPROVEN '+x)
    if bad_cert:
        print('CERTIFICATION_QA_FAILED invalidCertified='+str(bad_cert));return 2
    print('CERTIFICATION_QA_OK no certified recipe can bypass evidence closure')
    return 0
if __name__=='__main__':sys.exit(main())
