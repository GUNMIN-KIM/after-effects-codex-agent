import json, sys
sys.path.insert(0,'/opt/cf')
from runtest import *
p=json.load(open('/opt/cf/out_extend.api.json'))
vid=find(p,'VHS_LoadVideo')[0]
dec=find(p,'VAEDecodeTiled')[0]; adec=find(p,'LTXVAudioVAEDecode')[0]
cst=find(p,'ComfyMathExpression','문맥 시작 인덱스')[0]
tot=find(p,'ComfyMathExpression','생성 길이')[0]
wf=find(p,'ComfyMathExpression','stage2 가로')[0]; hf=find(p,'ComfyMathExpression','stage2 세로')[0]
p['9001']={'class_type':'RepeatImageBatch','inputs':{'image':[vid,0],'amount':4}}
p['9002']={'class_type':'ImageFromBatch','inputs':{'image':['9001',0],'batch_index':[cst,1],'length':[tot,1]}}
# tint the fake generation so the colour-match step has something to correct
p['9003']={'class_type':'ImageBlend','inputs':{'image1':['9002',0],'image2':['9002',0],'blend_factor':0.3,'blend_mode':'screen'}}
p[dec]={'class_type':'ImageScale','inputs':{'image':['9003',0],'upscale_method':'bilinear','width':[wf,1],'height':[hf,1],'crop':'disabled'}}
p[adec]={'class_type':'TrimAudioDuration','inputs':{'audio':[vid,2],'start_index':0.0,'duration':60.0}}
for t in ['문맥 프레임 C','새 프레임 수','생성 길이','문맥 시작 인덱스','stage2 가로','stage2 세로','stage1 가로','잘라낼 시작','잘라낼 길이']:
    i=find(p,'ComfyMathExpression',t)[0]
    p['dbg'+i]={'class_type':'PreviewAny','inputs':{'source':[i,1]}, '_meta':{'title':t}}
print("OK" if run(p,'extend-stub') else "FAIL")
