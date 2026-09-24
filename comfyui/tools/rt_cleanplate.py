import json, sys
sys.path.insert(0,'/opt/cf')
from runtest import *
p=json.load(open('/opt/cf/out_cleanplate.api.json'))
dec=find(p,'VAEDecodeTiled')[0]
fM=find(p,'ImageFromBatch','8n+1')[0]
wf=find(p,'ComfyMathExpression','stage2 가로')[0]; hf=find(p,'ComfyMathExpression','stage2 세로')[0]
p['9001']={'class_type':'ImageBlend','inputs':{'image1':[fM,0],'image2':[fM,0],'blend_factor':0.3,'blend_mode':'multiply'}}
p[dec]={'class_type':'ImageScale','inputs':{'image':['9001',0],'upscale_method':'bilinear','width':[wf,1],'height':[hf,1],'crop':'disabled'}}
print("OK" if run(p,'cleanplate-stub') else "FAIL")
