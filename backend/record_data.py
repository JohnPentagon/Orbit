"""Bounded scalar field extraction shared by live read adapters and comparisons."""
import math

OMITTED='[not captured]'


def fields(value, secret='', prefix='', limit=200):
    result={}
    sensitive={'password','secret','access_token','refresh_token','authorization','cookie','connection_string','links','href','url','downloadurl','download_url'}
    def walk(node,path,depth):
        if len(result)>=limit:return
        if isinstance(node,dict) and depth<3:
            for key,item in node.items():
                if not isinstance(key,str) or key.lower() in sensitive:continue
                if secret and secret in key:continue
                walk(item,(path+'.' if path else '')+key,depth+1)
        elif node is None or type(node) in {str,bool,int,float} or isinstance(node,list) and len(node)<=100 and all(v is None or type(v) in {str,bool,int,float} for v in node):
            def safe(item):
                if isinstance(item,str):return OMITTED if len(item)>2000 or secret and secret in item else item
                if type(item) is float and not math.isfinite(item):return OMITTED
                if type(item) is int and abs(item)>9007199254740991:return str(item)
                return item
            if path:result[path]=[safe(v) for v in node] if isinstance(node,list) else safe(node)
    walk(value,prefix,0)
    return result


def resource_records(resources):
    return [{'id':str(r['id']),'values':{**fields({k:v for k,v in r.items() if k!='fields'}),**r.get('fields',{})}} for r in resources]


def native_metadata(data):
    values={'id':str(data['artefact_id']),'number':data['number'],'title':data['title'],'modified':data['modified']}
    revisions=data.get('guard',{}).get('revisions',[])
    for field in ['id','version','status']:
        values['visible_revision_'+field]=revisions[0].get(field) if len(revisions)==1 else [r.get(field) for r in revisions]
    for key in data['keys']:
        raw=data['values'].get(str(key['id']),[])
        values['metadata.'+key['name']]=raw[0] if len(raw)==1 else raw if raw else None
    values.update(fields(data.get('guard',{}),prefix='state'))
    return {'id':str(data['artefact_id']),'values':values}
