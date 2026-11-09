"""Create three TVLP 2.0 examples, including extreme initial loss."""
import math
import sys
from pathlib import Path
from viewer_next.writer import RunWriter


def generate(root):
    for i,(title,label,key,role,direction) in enumerate([
        ('分类训练','分类准确率','validation/top1','score','max'),
        ('注意力模块消融','验证 mIoU','validation/miou','score','max'),
        ('自定义目标优化','目标函数','objective/custom','other','min')]):
        with RunWriter(root/str(i),experiment={'id':f'exp{i}','name':title},
            variant={'id':'baseline','name':'基线方案','kind':'baseline','description':'标准训练设置'},
            metrics={'train/objective':{'label':'训练损失','unit':'1','direction':'min','role':'loss'},
                     key:{'label':label,'unit':'ratio' if role=='score' else '1','direction':direction,'role':role},
                     'lr':{'label':'学习率','unit':'1','direction':'none','role':'other'}},
            charts=['train/objective',key],numbers=['lr'],primary_metric=key,config={'optimizer':'AdamW','epochs':100}) as w:
            for step in range(1000):
                values={'train/objective':100*math.exp(-step/25)+.02+.002*math.sin(step/12),'lr':.0003}
                if step%10==0:values[key]=.3+.45*(1-math.exp(-step/200)) if role=='score' else 2/(1+step)
                w.log(step,values,epoch=step/10)


if __name__=='__main__':
    generate(Path(sys.argv[1]))
