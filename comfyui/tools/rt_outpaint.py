import json, sys
sys.path.insert(0,'/opt/cf')
from runtest import *
p=json.load(open('/opt/cf/out_outpaint.api.json'))
d1=find(p,'VAEDecodeTiled','stage1')[0]; d2=find(p,'VAEDecodeTiled','stage2')[0]
ref1=find(p,'ImageScale','stage1 해상도 레퍼런스')[0]
b1=find(p,'LTXVLaplacianPyramidBlend','stage1')[0]
wg=find(p,'ComfyMathExpression','stage2 생성 가로')[0]; hg=find(p,'ComfyMathExpression','stage2 생성 세로')[0]
p['9001']={'class_type':'ImageBlend','inputs':{'image1':[ref1,0],'image2':[ref1,0],'blend_factor':0.4,'blend_mode':'screen'}}
p[d1]={'class_type':'ImageScale','inputs':{'image':['9001',0],'upscale_method':'bilinear','width':1,'height':1,'crop':'disabled'}}
# ImageScale with 1x1 would break; use ImageScaleBy 1.0 instead
p[d1]={'class_type':'ImageScaleBy','inputs':{'image':['9001',0],'upscale_method':'bilinear','scale_by':1.0}}
p[d2]={'class_type':'ImageScale','inputs':{'image':[b1,0],'upscale_method':'bilinear','width':[wg,1],'height':[hg,1],'crop':'disabled'}}
for t in ['최종 캔버스 가로','최종 캔버스 세로','stage2 생성 가로','stage2 생성 세로','stage1 가로','LTX 프레임 수','원본 X','원본 Y']:
    i=find(p,'ComfyMathExpression',t)[0]
    p['dbg'+i]={'class_type':'PreviewAny','inputs':{'source':[i,1]}, '_meta':{'title':t}}
print("OK" if run(p,'outpaint-stub') else "FAIL")
