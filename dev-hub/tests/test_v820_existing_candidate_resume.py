#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,subprocess,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
MOD=ROOT/"dev-hub/bin/existing-candidate-resume.py"
spec=importlib.util.spec_from_file_location("existing_candidate_resume",MOD)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def git(repo:Path,*args:str)->str:
    p=subprocess.run(["git","-C",str(repo),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True)
    return p.stdout.strip()

def commit(repo:Path,msg:str)->str:
    subprocess.run(["git","-C",str(repo),"add","."],check=True)
    subprocess.run(["git","-C",str(repo),"commit","-m",msg],check=True,stdout=subprocess.DEVNULL)
    return git(repo,"rev-parse","HEAD")

def prompt(worktree:Path,revision:str,tree:str)->str:
    return f'''REPRISE EXACTE — candidat existant\nNe pas reconstruire le chantier.\nWorktree :\n{worktree}\nCommit local déjà figé :\n{revision}\nTree exact :\n{tree}\nBranche locale :\ndev-hub-candidate\nReprendre le commit, publier et qualifier.'''

base_root=Path('/opt/chacha-dev/runtime')
with tempfile.TemporaryDirectory(prefix='v820-resume-test-',dir=str(base_root)) as td:
    repo=Path(td);git(repo,'init');git(repo,'config','user.email','test@local.invalid');git(repo,'config','user.name','ChaCha Test')
    (repo/'a.txt').write_text('base\n');base=commit(repo,'base')
    active=repo/'active.revision';active.write_text(base+'\n')
    (repo/'a.txt').write_text('candidate\n');candidate=commit(repo,'candidate');tree=git(repo,'rev-parse','HEAD^{tree}')
    ready=m.inspect(prompt(repo,candidate,tree),base_root,active)
    assert ready['status']=='READY',ready
    assert ready['next_stage']=='EXISTING_CANDIDATE_RELEASE',ready
    assert ready['candidate_revision']==candidate and ready['candidate_tree']==tree,ready
    assert ready['domain_factories_required'] is False and ready['new_project_required'] is False,ready
    stale=m.inspect(prompt(repo,base,git(repo,'rev-parse',base+'^{tree}')),base_root,active)
    assert stale['next_stage']=='REFRESH_CANDIDATE_REFERENCE',stale
    mismatch=m.inspect(prompt(repo,candidate,'0'*40),base_root,active)
    assert mismatch['next_stage']=='CANDIDATE_TREE_MISMATCH',mismatch
    plain=m.inspect('Construis une nouvelle application',base_root,active)
    assert plain['status']=='NOT_APPLICABLE',plain

orchestrator=(ROOT/'dev-hub/bin/autonomous-project-orchestrator.py').read_text()
controller=(ROOT/'dev-hub/bin/central-interface-controller.py').read_text()
assert 'existing-candidate-resume.py' in orchestrator
assert 'synthetic_project_created":False' in orchestrator
assert 'prior_next=="EXISTING_CANDIDATE_RELEASE"' in controller
assert 'CANDIDATE_PUBLICATION_REQUIRED' in controller
print('CHACHA_DEV_V820_EXISTING_CANDIDATE_RESUME=PASS')
