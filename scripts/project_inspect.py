"""Read-only project navigation, source candidates and migration accounting.

Only `render --write` changes a file. Never imports project modules, executes
validation commands, loads native libraries, starts CST or accesses the network.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess
import sys
import tokenize

ROOT = Path(__file__).resolve().parents[1]
CATALOG = 'docs/project-map.json'


def git(root, *args):
    return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.PIPE).decode('utf-8')


def safe_path(root, path):
    posix=PurePosixPath(path)
    if posix.is_absolute() or PureWindowsPath(path).is_absolute() or '..' in posix.parts or '\\' in path:
        raise ValueError('repository-relative path required: '+path)
    result=(root/path).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('path escapes repository: '+path)
    return result


def load(root):
    return json.loads((root/CATALOG).read_text(encoding='utf-8'))


def git_root(root):
    try:return Path(git(root,'rev-parse','--show-toplevel').strip()).resolve()==root.resolve()
    except subprocess.CalledProcessError:return False


def scope(root):
    if not git_root(root):
        manifest=json.loads((root/'release-manifest.json').read_text(encoding='utf-8'))
        return sorted(set(manifest['files']) | {'release-manifest.json'})
    return sorted(set(filter(None,git(root,'ls-files','-z','--cached','--others','--exclude-standard').split('\0'))))


def identity(root):
    if not git_root(root):
        manifest=json.loads((root/'release-manifest.json').read_text(encoding='utf-8'))
        return dict(kind='source-release',commit=manifest['base_commit'],content_sha256=manifest['content_sha256'],
                    worktree='not a Git checkout',catalog_sha256=hashlib.sha256((root/CATALOG).read_bytes()).hexdigest())
    return dict(commit=git(root,'rev-parse','HEAD').strip(),
                worktree=git(root,'status','--porcelain').splitlines(),
                catalog_sha256=hashlib.sha256((root/CATALOG).read_bytes()).hexdigest())


def declarations(root, path):
    file=safe_path(root,path)
    if file.suffix=='.py':
        with tokenize.open(file) as stream: tree=ast.parse(stream.read(),filename=path)
        result=[]
        def visit(body,prefix=''):
            for node in body:
                if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
                    name=prefix+node.name
                    result.append(dict(symbol=name,line=node.lineno,end_line=node.end_lineno))
                    visit(node.body,name+'.')
        visit(tree.body)
        return result,tree
    text=file.read_text(encoding='utf-8-sig')
    return [dict(symbol=m.group(1),line=text.count('\n',0,m.start())+1)
            for m in re.finditer(r'(?im)^\s*(?:(?:Public|Private)\s+)?(?:Sub|Function)\s+(\w+)',text)],None


def headings(root,path):
    counts=Counter();result=[]
    for number,line in enumerate(safe_path(root,path).read_text(encoding='utf-8-sig').splitlines(),1):
        match=re.match(r'^#{1,6}\s+(.+)',line)
        if match:
            title=match[1].strip().strip('#').strip()
            slug=re.sub(r'[^\w\- ]','',title.casefold()).replace(' ','-')
            index=counts[slug];counts[slug]+=1
            result.append(dict(title=title,line=number,anchor=slug+(f'-{index}' if index else '')))
    return result


def feature_paths(feature):
    return {x['path'] for key in ('sources','tests','docs') for x in feature[key]}


def inventory(root,catalog,paths=None):
    paths=scope(root) if paths is None else paths
    mapping={}
    for feature in catalog['features']:
        for path in feature_paths(feature):mapping.setdefault(path,[]).append(feature['id'])
    rows=[]
    for path in paths:
        domain=next((d for d in catalog['domains'] if any(path.startswith(p[:-3]+'/') if p.endswith('/**') else PurePosixPath(path).match(p) for p in d['patterns'])),None)
        if path.startswith('knowledge-base/vendor/') or path.startswith('csttool/_vendor/'):
            category='vendor';disposition='retain-vendor; no source refactor'
        elif path.startswith('utils/'):
            category='preserved-utils';disposition='unchanged per project instruction'
        elif path.startswith(('artifacts/','docs/archive/')):
            category='historical-evidence';disposition='retain dated evidence'
        elif Path(path).suffix.lower() not in {'.py','.vb','.bas','.md','.json','.toml','.ini','.ps1','.bat','.txt','.yaml','.yml','.gitignore','.gitattributes'}:
            category='binary-or-resource';disposition='retain; no semantic source analysis'
        else:
            category='first-party-text';disposition='retain path; use authoritative navigation'
        features=mapping.get(path,[])
        rows.append(dict(path=path,category=category,domain=domain['id'] if domain else None,
                         features=features,mapping_status='declared' if features else 'unmapped',
                         unknown=None if features else 'no explicit feature relation; domain classification is not a functional mapping',
                         migration=dict(old_path=path,target_path=path,disposition=disposition)))
    return dict(denominator=len(rows),categories=dict(Counter(x['category'] for x in rows)),
                explicitly_mapped=sum(bool(x['features']) for x in rows),
                unmapped=sum(not x['features'] for x in rows),files=rows)


def module_path(root,module):
    for value in (module.replace('.','/')+'.py',module.replace('.','/')+'/__init__.py'):
        if safe_path(root,value).is_file():return value
    return None


def source_relations(root,paths):
    relations=[];problems=[]
    interesting={'getattr','setattr','import_module','connect','disconnect','emit','add_tool','register',
                 'register_tool','Popen','RunScript','MacroCheckThis','submit','add_done_callback','create_task'}
    for path in paths:
        if not path.endswith('.py') or '/_vendor/' in path:continue
        try: symbols,tree=declarations(root,path)
        except (OSError,UnicodeError,SyntaxError) as error:
            problems.append(dict(path=path,reason=type(error).__name__,detail=str(error)));continue
        aliases={};local={x['symbol']:x for x in symbols if '.' not in x['symbol']}
        package=path.rsplit('/',1)[0].replace('/','.') if '/' in path else ''
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                for item in node.names:
                    target=module_path(root,item.name)
                    aliases[item.asname or item.name.split('.')[0]]=(target,None)
                    if target:relations.append(dict(source=path,line=node.lineno,target=target,type='import',evidence='static-declaration'))
            elif isinstance(node,ast.ImportFrom):
                parent=package.split('.') if package else []
                prefix=parent[:len(parent)-node.level+1] if node.level else []
                module='.'.join([*prefix,*((node.module or '').split('.') if node.module else [])])
                target=module_path(root,module) if module else None
                for item in node.names:
                    aliases[item.asname or item.name]=(target,item.name)
                    if target:relations.append(dict(source=path,line=node.lineno,target=target,target_symbol=item.name,type='import',evidence='static-declaration'))
        for node in ast.walk(tree):
            if not isinstance(node,ast.Call):continue
            name=ast.unparse(node.func)
            target=None;target_symbol=None
            if isinstance(node.func,ast.Name):
                if node.func.id in aliases:target,target_symbol=aliases[node.func.id]
                elif node.func.id in local:target,target_symbol=path,node.func.id
            elif isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name):
                if node.func.value.id in aliases:
                    target,base=aliases[node.func.value.id]
                    target_symbol=(base+'.' if base else '')+node.func.attr
            terminal=name.split('.')[-1]
            if target or terminal in interesting:
                relation=dict(source=path,line=node.lineno,type='call-site-candidate',expression=name,
                              target=target,target_symbol=target_symbol,evidence='AST-candidate',
                              unknown=None if target else 'receiver/registration/runtime target not statically resolved',
                              runtime_proven=False)
                if terminal in {'connect','add_tool','register','register_tool','add_done_callback'}:
                    relation['callback_expression']=ast.unparse(node.args[0]) if node.args else None
                    relation['registration_not_delivery']=True
                relations.append(relation)
    return relations,problems


def render(catalog):
    def links(items):return '、'.join(f"[{x['label']}]({('../'+x['path']) if not x.get('anchor') else '../'+x['path']+'#'+x['anchor']})" for x in items)
    lines=['# 功能—实现—验收映射入口','','此文件由 `scripts/project_inspect.py render --write` 从 [唯一机器契约](project-map.json)派生；不要直接编辑表格。',
           '先读[当前状态](current-status.md)与[TODO](minimal-python-vba-todo.md)。登记/结构检查不证明运行验收；查询及维护见[工具指南](project-map-guide.md)。','',
           '|功能ID|目的|源码|符号|测试/工具|说明|','|---|---|---|---|---|---|']
    for feature in catalog['features']:
        symbols=', '.join('`'+s+'`' for item in feature['sources'] for s in item['symbols'])
        lines.append('|'+ '|'.join([feature['id'],feature['purpose'],links(feature['sources']),symbols,
                                    links(feature['tests']) or feature.get('verification_note',''),links(feature['docs'])])+'|')
    return '\n'.join(lines)+'\n'


def validate(root,catalog):
    import jsonschema
    errors=[];warnings=[]
    schema=json.loads((root/'docs/project-map.schema.json').read_text(encoding='utf-8'))
    for error in jsonschema.Draft202012Validator(schema).iter_errors(catalog):errors.append(dict(kind='schema',location=list(error.path),message=error.message))
    if errors:return dict(valid=False,errors=errors,warnings=warnings)
    ids=[f['id'] for f in catalog['features']]
    if len(set(ids))!=len(ids):errors.append(dict(kind='duplicate-feature-id'))
    for feature in catalog['features']:
        for key in ('sources','docs','tests'):
            for link in feature[key]:
                try:
                    path=safe_path(root,link['path'])
                    if not path.is_file():raise ValueError('file missing')
                    if key=='sources':
                        symbols,_=declarations(root,link['path'])
                        missing=set(link['symbols'])-{r['symbol'] for r in symbols}
                        if missing:raise ValueError('symbols missing: '+str(sorted(missing)))
                    if link.get('anchor') and link['anchor'] not in {h['anchor'] for h in headings(root,link['path'])}:
                        raise ValueError('heading missing: '+link['anchor'])
                except (ValueError,OSError,UnicodeError,SyntaxError) as error:errors.append(dict(feature=feature['id'],path=link['path'],message=str(error)))
    for category in ('documents','tools'):
        for item in catalog[category]:
            try:
                if not safe_path(root,item['path']).is_file():raise ValueError('file missing')
            except (ValueError,OSError) as error:errors.append(dict(kind=category,path=item['path'],message=str(error)))
    for relation in catalog['relations']:
        for item in [relation['source'],*relation['targets']]:
            try:
                symbols,_=declarations(root,item['path'])
                if item.get('symbol') and item['symbol'] not in {x['symbol'] for x in symbols}:raise ValueError('relation symbol missing')
            except (ValueError,OSError,UnicodeError,SyntaxError) as error:errors.append(dict(kind='relation',id=relation['id'],message=str(error)))
    for path,expected in catalog['source_fingerprints'].items():
        file=safe_path(root,path)
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=expected:
            warnings.append(dict(kind='changed-since-capture',path=path,meaning='declarations/relations need review; fingerprints do not prove semantic validity'))
    if (root/'docs/feature-index.md').read_text(encoding='utf-8')!=render(catalog):errors.append(dict(kind='derived-index-stale',command='python scripts/project_inspect.py render --write'))
    return dict(valid=not errors,features=len(ids),errors=errors,warnings=warnings,
                semantic_and_runtime_validation=False)


def query(root,catalog,*,feature=None,path=None,symbol=None,question=None,delete=False,analysis=None):
    if path:safe_path(root,path)
    matched=[];reasons={}
    requested_path=path
    for item in catalog['features']:
        why=[]
        if feature and item['id'].casefold()==feature.casefold():why.append('exact feature id')
        if path and any(p==path or p.startswith(path.rstrip('/')+'/') for p in feature_paths(item)):why.append('declared path')
        if symbol and any(s==symbol or s.rsplit('.',1)[-1]==symbol for src in item['sources'] for s in src['symbols']):why.append('declared symbol')
        if question:
            words=question.casefold().split()
            text=(item['id']+' '+item['purpose']+' '+' '.join(feature_paths(item))).casefold()
            if any(w in text for w in words):why.append('literal text relevance, not semantic proof')
        if why:matched.append(item);reasons[item['id']]=why
    selected_paths=sorted({p for item in matched for p in feature_paths(item)} | ({requested_path} if requested_path else set()))
    relations,problems=analysis if analysis is not None else source_relations(root,[p for p in scope(root) if p.endswith('.py')])
    consumers=[r for r in relations if r.get('target') in selected_paths and r['source'] not in selected_paths]
    declarations_found=[]
    if symbol:
        for p in scope(root):
            if not p.endswith('.py') or '/_vendor/' in p:continue
            try:
                decls,_=declarations(root,p)
                declarations_found += [dict(path=p,**d) for d in decls if d['symbol']==symbol or d['symbol'].split('.')[-1]==symbol]
            except (OSError,UnicodeError,SyntaxError):pass
    registered=[r for r in catalog['relations'] if r['source']['path'] in selected_paths or any(t['path'] in selected_paths for t in r['targets'])]
    docs={x['path'] for f in matched for x in f['docs']}
    required=[dict(path=p,role='project-required') for p in ('AGENTS.md','docs/current-status.md','docs/feature-index.md')]
    registry={d['path']:d for d in catalog['documents']}
    for p in sorted(docs):
        doc=registry.get(p,{})
        required.append(dict(path=p,role=doc.get('role','unreviewed'),authority=doc.get('authority','unreviewed'),
                             headings=headings(root,p) if p.endswith('.md') and (root/p).is_file() else []))
    result=dict(matches=matched,match_reasons=reasons,selected_paths=selected_paths,
                symbol_declarations=declarations_found,ambiguous_symbol=len(declarations_found)>1,
                registered_relations=registered,consumer_candidates=consumers,analysis_problems=problems,
                required_reading=required,tests=sorted({x['path'] for f in matched for x in f['tests']}),
                runtime_checks='Use linked acceptance contracts; this command runs no tests or CST.',
                unmapped_input=not matched,unknown=['Dynamic receivers, reflection and runtime registrations are not a complete call graph.'],
                reviewed_relationships_refreshed=False)
    result['path_availability']={p:safe_path(root,p).is_file() for p in selected_paths}
    if delete:result['deletion']=dict(safe_to_delete=False,meaning='preflight only, never deletion authorization',known_references=consumers+registered)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('inventory');sub.add_parser('validate');sub.add_parser('tools')
    command=sub.add_parser('query')
    for name in ('feature','path','symbol','question'):command.add_argument('--'+name)
    command=sub.add_parser('delete');command.add_argument('path')
    command=sub.add_parser('changes');command.add_argument('--base',default='HEAD')
    command=sub.add_parser('graph');command.add_argument('--path');command.add_argument('--limit',type=int,default=40)
    command=sub.add_parser('render');command.add_argument('--write',action='store_true')
    args=parser.parse_args();root=args.root.resolve();catalog=load(root)
    result={};code=0
    if args.command=='render':
        text=render(catalog)
        if args.write:(root/'docs/feature-index.md').write_text(text,encoding='utf-8')
        else:print(text,end='');return
        result=dict(written='docs/feature-index.md',side_effect='explicit-derived-index-write')
    elif args.command=='inventory':result=inventory(root,catalog)
    elif args.command=='validate':result=validate(root,catalog);code=0 if result['valid'] else 1
    elif args.command=='tools':result=dict(tools=catalog['tools'],execution_permitted=False)
    elif args.command=='graph':
        paths=[p for p in scope(root) if not args.path or p==args.path or p.startswith(args.path.rstrip('/')+'/')]
        rows,problems=source_relations(root,paths)
        result=dict(relations=rows[:args.limit],total=len(rows),truncated=len(rows)>args.limit,
                    problems=problems,registered=catalog['relations'],complete_runtime_graph=False)
    elif args.command=='changes':
        if not git_root(root):parser.error('changes requires an actual Git checkout')
        if args.base.startswith('-'):parser.error('invalid base ref')
        git(root,'rev-parse','--verify',args.base+'^{commit}')
        paths=sorted(set(filter(None,git(root,'diff','--name-only','-z',args.base,'--').split('\0'))) |
                     set(filter(None,git(root,'ls-files','--others','--exclude-standard','-z').split('\0'))))
        analysis=source_relations(root,[p for p in scope(root) if p.endswith('.py')])
        result=dict(base=args.base,changed_paths=paths,impacts=[dict(path=p,**query(root,catalog,path=p,analysis=analysis)) for p in paths],
                    execution_permitted=False)
    else:
        if args.command=='delete':result=query(root,catalog,path=args.path,delete=True)
        else:
            if not any((args.feature,args.path,args.symbol,args.question)):parser.error('query selector required')
            if args.path:safe_path(root,args.path)
            result=query(root,catalog,feature=args.feature,path=args.path,symbol=args.symbol,question=args.question)
        if result['unmapped_input']:code=2
    print(json.dumps(dict(input=identity(root),command=args.command,result=result),ensure_ascii=False,indent=2))
    raise SystemExit(code)


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,json.JSONDecodeError,subprocess.CalledProcessError) as error:
        print(json.dumps(dict(error=type(error).__name__,message=str(error)),ensure_ascii=False));raise SystemExit(1)
