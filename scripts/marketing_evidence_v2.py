#!/usr/bin/env python3
"""Evidence-first marketing report. Missing is not zero. Never infer bookings from clicks."""
import argparse, csv, json
from pathlib import Path
from datetime import date
from collections import defaultdict

FIELDS=['date','channel','impressions','content_clicks','booking_click_events','confirmed_bookings','paid_new_customers','spend_krw','source','traffic_scope']
METRICS=FIELDS[2:8]
SCOPES={'measured','includes_tests','unknown'}

def load(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        rd=csv.DictReader(f)
        if rd.fieldnames!=FIELDS: raise ValueError('invalid header')
        rows=[];seen=set()
        for idx,r in enumerate(rd,2):
            try:
                dt=date.fromisoformat(r['date'])
                if dt.isoformat()!=r['date']:raise ValueError('bad date')
                channel=r['channel'].strip();source=r['source'].strip();scope=r['traffic_scope'].strip()
                if not channel or not source or scope not in SCOPES:raise ValueError('missing source/channel or bad scope')
                unique=(r['date'],channel,source)
                if unique in seen:raise ValueError('duplicate day/channel/source')
                seen.add(unique)
                row={'date':r['date'],'channel':channel,'source':source,'traffic_scope':scope}
                for k in METRICS:
                    raw=r[k].strip()
                    if raw=='':row[k]=None
                    elif not raw.isascii() or not raw.isdecimal():raise ValueError('invalid count: '+k)
                    else:row[k]=int(raw)
                rows.append(row)
            except (ValueError,AttributeError,TypeError) as e:raise ValueError(f'row {idx}: {e}') from e
    return rows

def compute(rows,target=100):
    if type(target) is not int or target<1:raise ValueError('invalid target')
    groups=defaultdict(list)
    for row in rows:groups[row['channel']].append(row)
    def total(rs):
        return {k:(sum(r[k] for r in rs) if rs and all(r[k] is not None for r in rs) else None) for k in METRICS}
    t=total(rows)
    return {'schema_version':'marketing_evidence_v2','target':target,'rows':len(rows),
            'channels':{k:total(v) for k,v in sorted(groups.items())},'total':t,
            'paid_target_pct':round(t['paid_new_customers']/target*100,2) if t['paid_new_customers'] is not None else None,
            'contains_unverified_traffic':any(r['traffic_scope']!='measured' for r in rows),
            'cross_stage_conversion_rate':None,'attribution_verified':False}

def markdown(result):
    fmt=lambda n:'미측정' if n is None else f'{n:,}'
    lines=['# 근거 기반 신규 고객 퍼널','',
        '공란=미측정, 숫자 0=확인된 0. 이벤트 클릭은 실제 예약 또는 유료 방문이 아닙니다.','',
        '| 채널 | 노출 | 콘텐츠 클릭 | 예약 링크 클릭 이벤트 | 확정 예약 | 유료 신규 | 비용 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name,values in result['channels'].items():
        lines.append('| '+name.replace('|','/')+' | '+' | '.join(fmt(values[k]) for k in METRICS)+' |')
    lines += ['| **합계** | '+' | '.join(fmt(result['total'][k]) for k in METRICS)+' |','',
        '유료 신규 목표: '+str(result['target'])+'명',
        '목표 달성률: '+('미측정' if result['paid_target_pct'] is None else str(result['paid_target_pct'])+'%'), '',
        '주의: 테스트 트래픽, 중복 이용자, 채널별 이벤트 분모를 별도 확인해야 합니다.']
    return '\n'.join(lines)+'\n'

def briefs():
    return {'status':'hypotheses_only','publish_approved':False,'items':[
      {'segment':'뜨는 옆머리','format':'B 문제 해결','question':'왜 커트 후에도 옆머리가 뜰까?','proof':['동의된 비포 옆모습','실제 모류 상담','실제 애프터'],'cta':'모류 맞춤 상담','metric':'verified paid new visits'},
      {'segment':'볼륨 없는 직모','format':'A 결과 반전','question':'커트와 펌 중 무엇이 필요한가?','proof':['실제 비포','확인된 시술 단계','실제 애프터'],'cta':'스타일 상담','metric':'verified paid new visits'},
      {'segment':'스타일 실패 불안','format':'C 상담 전문성','question':'사진과 실제 모질의 차이는 무엇인가?','proof':['동의된 상담 근거','실제 결과 사진'],'cta':'사진 기반 상담','metric':'verified paid new visits'}
    ]}

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--report',required=True);p.add_argument('--json',required=True);p.add_argument('--briefs',required=True);p.add_argument('--target',type=int,default=100)
    a=p.parse_args();result=compute(load(a.input),a.target)
    for path,value in ((a.report,markdown(result)),(a.json,json.dumps(result,ensure_ascii=False,indent=2)),(a.briefs,json.dumps(briefs(),ensure_ascii=False,indent=2))):
        f=Path(path);f.parent.mkdir(parents=True,exist_ok=True);f.write_text(value+'\n' if not value.endswith('\n') else value,encoding='utf8')
    print('REPORT_READY',result['rows'])
if __name__=='__main__':main()
