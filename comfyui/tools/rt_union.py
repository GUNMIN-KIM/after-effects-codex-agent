import json, sys
sys.path.insert(0,'/opt/cf')
from runtest import *
p=json.load(open('/opt/cf/out_union.api.json'))
comp=find(p,'GetVideoComponents')[0]
sw=find(p,'ComfySwitchNode','MoGe 입력')[0]
for i in find(p,'MoGeRender'): p[i]={'class_type':'ImageInvert','inputs':{'image':[sw,0]}}
dec=find(p,'VAEDecodeTiled')[0]; adec=find(p,'LTXVAudioVAEDecode')[0]
dM=find(p,'ImageFromBatch','깊이 8n+1')[0]
w2=find(p,'ComfyMathExpression','stage2 가로')[0]; h2=find(p,'ComfyMathExpression','stage2 세로')[0]
p[dec]={'class_type':'ImageScale','inputs':{'image':[dM,0],'upscale_method':'bilinear','width':[w2,1],'height':[h2,1],'crop':'disabled'}}
p[adec]={'class_type':'TrimAudioDuration','inputs':{'audio':[comp,1],'start_index':0.0,'duration':60.0}}
for t in ['stage1 가로','stage1 세로','프레임 수','stage2 가로']:
    i=find(p,'ComfyMathExpression',t)[0]; p['dbg'+i]={'class_type':'PreviewAny','inputs':{'source':[i,1]}}
print("OK" if run(p,'union-stub') else "FAIL")
