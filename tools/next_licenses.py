"""Collect runtime license notices into the desktop distribution."""
import importlib.metadata as metadata
import shutil
import sys
from pathlib import Path

out=Path('dist/TrainingViewer/licenses')
out.mkdir(parents=True,exist_ok=True)
names=['fastapi','uvicorn','jsonschema','pywebview','pythonnet','clr_loader','cffi',
       'pycparser','proxy_tools','bottle','starlette','pydantic','pydantic_core',
       'typing_extensions','typing_inspection','annotated_types','annotated_doc',
       'anyio','idna','h11','opentelemetry_api','attrs','referencing','rpds_py',
       'jsonschema_specifications']
notices=[]
for name in names:
    d=metadata.distribution(name)
    notices.append(f'{d.metadata["Name"]} {d.version}: {d.metadata.get("License-Expression") or d.metadata.get("License") or "see bundled license"}')
    for file in d.files or []:
        if 'license' in str(file).lower() or 'copying' in str(file).lower():
            source=Path(d.locate_file(file))
            if source.is_file():
                dest=out/name/source.name
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,dest)
for name in ['react','react-dom','scheduler','echarts','zrender','tslib']:
    source=Path('frontend/node_modules')/name
    for p in source.glob('*'):
        if p.is_file() and any(word in p.name.lower() for word in ('license','copying','notice')):
            dest=out/name/p.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
for name in ['LICENSE','NOTICE']:
    shutil.copyfile(name,out/name)
python_license=Path(sys.base_prefix)/'LICENSE.txt'
if python_license.exists():shutil.copyfile(python_license,out/'Python-LICENSE.txt')
(out/'DEPENDENCIES.txt').write_text('\n'.join(notices),encoding='utf-8')
