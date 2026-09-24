import json, sys
sys.path.insert(0,'/opt/cf')
from runtest import *
video = sys.argv[1] if len(sys.argv) > 1 else 'test.mp4'
gen_audio = (sys.argv[2] if len(sys.argv) > 2 else '1') == '1'
p=json.load(open('/opt/cf/out_extend.api.json'))
vid=find(p,'VHS_LoadVideo')[0]
p[vid]['inputs']['video']=video
dec=find(p,'VAEDecodeTiled')[0]; adec=find(p,'LTXVAudioVAEDecode')[0]
cst=find(p,'ComfyMathExpression','문맥 시작 인덱스')[0]
tot=find(p,'ComfyMathExpression','생성 길이')[0]
wf=find(p,'ComfyMathExpression','stage2 가로')[0]; hf=find(p,'ComfyMathExpression','stage2 세로')[0]
p['9001']={'class_type':'RepeatImageBatch','inputs':{'image':[vid,0],'amount':4}}
p['9002']={'class_type':'ImageFromBatch','inputs':{'image':['9001',0],'batch_index':[cst,1],'length':[tot,1]}}
p['9003']={'class_type':'ImageBlend','inputs':{'image1':['9002',0],'image2':['9002',0],'blend_factor':0.3,'blend_mode':'screen'}}
p[dec]={'class_type':'ImageScale','inputs':{'image':['9003',0],'upscale_method':'bilinear','width':[wf,1],'height':[hf,1],'crop':'disabled'}}
# stand-in for LTX generated audio: 24 kHz stereo covering the whole generated span
p[adec]={'class_type':'EmptyAudio','inputs':{'duration':10.0,'sample_rate':24000,'channels':2}}
sw=[k for k,v in p.items() if v['class_type']=='PrimitiveBoolean' and '⑦' in v.get('_meta',{}).get('title','')]
for k in sw: p[k]['inputs']['value']=gen_audio
src=[k for k,v in p.items() if v['class_type']=='PrimitiveBoolean' and '⑪' in v.get('_meta',{}).get('title','')]
for k in src: p[k]['inputs']['value']=(video!='test_silent.mp4')
print("OK" if run(p,f'extend[{video},gen_audio={gen_audio}]') else "FAIL")
