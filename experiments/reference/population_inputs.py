"""Helpers used by run_reference.py, copied unchanged from perf/simulation-redundancy
(experiments/acceleration/pilot.py, scripts/analyze_baseline_diagnostic.py, scripts/run_baseline_diagnostic.py)
so that this branch does not need the pilot's dependencies."""
import collections, gzip, hashlib, io
import xml.etree.ElementTree as E


def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def stream(path):
    if path.suffix=='.zst':
        import zstandard
        return io.BufferedReader(zstandard.open(path,'rb'))
    if path.suffix=='.gz':return gzip.open(path,'rb')
    return path.open('rb')


def selected_only(source, target):
    count=0; ids=hashlib.sha256(); groups=collections.Counter()
    with stream(source) as f, gzip.open(target,'wt') as out:
        out.write('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE population SYSTEM "http://www.matsim.org/files/dtd/population_v6.dtd">\n<population>\n')
        it=E.iterparse(f,events=('start','end'));_,root=next(it)
        for event,person in it:
            if event!='end' or person.tag!='person':continue
            plans=person.findall('plan'); selected=[p for p in plans if p.get('selected')=='yes']
            if len(selected)!=1:raise ValueError('Expected one selected plan')
            for p in plans:
                if p is not selected[0]:person.remove(p)
            selected[0].attrib.pop('score',None)
            pid=person.get('id');ids.update((pid+'\n').encode());count+=1
            groups[person.find("attributes/attribute[@name='subpopulation']").text]+=1
            out.write(E.tostring(person,encoding='unicode'));root.remove(person)
        out.write('</population>\n')
    return dict(persons=count,ordered_person_ids_sha256=ids.hexdigest(),groups=dict(groups),source=str(source),source_sha256=sha(source),output_sha256=sha(target))


def setparam(root,module,name,value):
    m=root.find(f"module[@name='{module}']")
    if m is None:raise ValueError('Missing module '+module)
    p=m.find(f"param[@name='{name}']")
    if p is None:p=E.SubElement(m,'param',name=name)
    p.set('value',str(value))
