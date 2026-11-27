"""Local audio transcription review. Run with Python 3.11+."""
import argparse
import csv
import io
import json
import mimetypes
import os
import sqlite3
import sys
import urllib.parse
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HTML = r'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>音声とセリフの確認</title><style>
:root{font-family:system-ui,"Yu Gothic UI",sans-serif;color:#27334a;background:#f4f7fc}*{box-sizing:border-box}body{margin:0}header{background:#fff;border-bottom:1px solid #dfe5ef;padding:18px 28px;display:flex;align-items:center;justify-content:space-between}h1{font-size:20px;margin:0}header span,.muted{font-size:13px;color:#68758a}.layout{display:grid;grid-template-columns:330px 1fr;height:calc(100vh - 70px)}aside{padding:18px;background:#fff;border-right:1px solid #dfe5ef;display:flex;flex-direction:column;min-height:0;gap:12px}.filters{display:grid;grid-template-columns:1fr 1fr;gap:8px}input,select,textarea,button{font:inherit}input,select,textarea{border:1px solid #ccd5e3;border-radius:8px;padding:9px;background:white;width:100%;color:inherit}#search{grid-column:span 2}.list{overflow:auto;flex:1} .item{width:100%;border:0;background:transparent;text-align:left;padding:11px 10px;border-radius:8px;cursor:pointer;color:#34415a;word-break:break-all;font-size:12px}.item:hover{background:#f2f6fd}.item.active{background:#e9f0ff;color:#254b99}.item small{display:block;color:#78849a;margin-top:4px}main{overflow:auto;padding:30px;display:flex;justify-content:center}.content{width:min(850px,100%)}.card{background:#fff;border:1px solid #e0e7f1;border-radius:14px;padding:23px;margin-bottom:16px;box-shadow:0 3px 12px #253d6010}.eyebrow{font-size:12px;color:#687994;margin-bottom:7px}.filename{font-size:17px;font-weight:700;overflow-wrap:anywhere}.meta{font-size:13px;color:#6d7c92;margin:8px 0 18px}audio{width:100%}.actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}button,.btn{border:1px solid #d1daea;border-radius:8px;background:#fff;padding:9px 14px;color:#34415a;cursor:pointer;text-decoration:none;font-size:14px}button:hover,.btn:hover{background:#f2f6fd}.primary{background:#315fc4;border-color:#315fc4;color:#fff}.primary:hover{background:#254da5}.success{color:#147a55}textarea{min-height:120px;resize:vertical;line-height:1.7;margin:8px 0}h2{font-size:15px;margin:0 0 10px}.candidate{padding:12px;background:#f6f8fc;border-radius:8px;margin:8px 0;white-space:pre-wrap;font-size:14px}.candidate small{color:#718096}.hint{font-size:12px;color:#718096;line-height:1.6}.spacer{flex:1}#saveStatus{font-size:13px;color:#68758a}.empty{color:#8b98aa;text-align:center;padding:35px}.badge{font-size:12px;background:#eef3fb;border-radius:50px;padding:4px 9px}.error{color:#b42318} @media(max-width:750px){.layout{display:block;height:auto}aside{border-right:0;height:300px}main{padding:15px}}
</style></head><body><header><div><h1>音声とセリフの確認</h1><span>音声を聞き、確認したテキストを記録します</span></div><a href="/export" class="btn">作業結果をCSVで保存</a></header><div class="layout"><aside><div class="filters"><select id="duration"><option value="5">5秒以上</option><option value="3">3秒以上</option><option value="0">すべて</option></select><select id="status"><option value="all">すべて</option><option value="todo">未確認</option><option value="confirmed">確認済み</option><option value="skip">保留・除外</option></select><input id="search" placeholder="ファイル名で検索"></div><div class="muted" id="counts"></div><div class="list" id="list"></div></aside><main><div class="content" id="detail"><div class="empty">音声を選んでください</div></div></main></div><script>
let rows=[],current=null,saveTimer=null,saving=Promise.resolve();const $=s=>document.querySelector(s);function esc(s){let e=document.createElement('div');e.textContent=s??'';return e.innerHTML}function state(r){return r.review_status||'todo'}function filtered(){let d=Number($('#duration').value),st=$('#status').value,q=$('#search').value.toLowerCase();return rows.filter(r=>r.duration>=d&&(st==='all'||state(r)===st)&&r.voice_id.toLowerCase().includes(q))}function renderList(){let items=filtered();$('#counts').textContent=`表示 ${items.length} 件 ／ 確認済み ${rows.filter(r=>state(r)==='confirmed').length} 件 ／ 全 ${rows.length} 件`;$('#list').innerHTML=items.map(r=>`<button class="item ${r.voice_id===current?'active':''}" data-id="${esc(r.voice_id)}">${esc(r.voice_id)}<small>${r.duration.toFixed(2)} 秒 · ${state(r)==='confirmed'?'確認済み':state(r)==='skip'?'保留・除外':'未確認'}${r.candidate_count?' · 候補あり':''}</small></button>`).join('')||'<div class="empty">該当なし</div>';document.querySelectorAll('.item').forEach(el=>el.onclick=()=>show(el.dataset.id))}function show(id){if(saveTimer){clearTimeout(saveTimer);saveTimer=null;save()}current=id;let r=rows.find(x=>x.voice_id===id);if(!r)return;$('#detail').innerHTML=`<div class="card"><div class="eyebrow">音声ファイル</div><div class="filename">${esc(r.voice_id)}.wav</div><div class="meta">${r.duration.toFixed(2)} 秒　·　${esc(r.audio_path)}</div><audio id="audio" controls preload="metadata" src="/audio?id=${encodeURIComponent(id)}"></audio><div class="actions" style="margin-top:15px"><button id="prev">← 前へ</button><button id="next">次へ →</button><span class="spacer"></span><label class="muted">再生速度 <select id="speed" style="width:auto;padding:5px"><option value="0.75">0.75×</option><option value="1" selected>1×</option><option value="1.25">1.25×</option></select></label></div></div><div class="card"><h2>確認したセリフ</h2><textarea id="text" placeholder="聞き取った内容を入力してください">${esc(r.verified_text)}</textarea><div class="actions"><button class="primary" id="confirm">確認済みにする</button><button id="skip">保留・除外</button><button id="reset">未確認に戻す</button><span class="spacer"></span><span id="saveStatus">${state(r)==='confirmed'?'確認済み':state(r)==='skip'?'保留・除外':'未確認'}</span></div><p class="hint">入力は自動保存されます。Ctrl + Enter で確認済み、Alt + ← / → で前後に移動できます。</p></div><div class="card"><h2>シナリオの候補文</h2><p class="hint">同じ音声IDが使われた場面の表示文です。実際の発話と異なる場合があります。</p>${r.candidate_texts?`<div class="candidate">${esc(r.candidate_texts)}</div><div class="hint">出典<br>${esc(r.sources).replaceAll('\n','<br>')}</div>`:'<div class="muted">候補文は見つかっていません。</div>'}</div>`;$('#text').oninput=()=>{r.verified_text=$('#text').value;$('#saveStatus').textContent='保存待ち…';clearTimeout(saveTimer);saveTimer=setTimeout(save,450)};$('#speed').onchange=e=>$('#audio').playbackRate=Number(e.target.value);$('#confirm').onclick=()=>{if(!r.verified_text.trim()){alert('セリフを入力してください。');return}r.review_status='confirmed';save()};$('#skip').onclick=()=>{r.review_status='skip';save()};$('#reset').onclick=()=>{r.review_status='todo';save()};$('#prev').onclick=()=>move(-1);$('#next').onclick=()=>move(1);renderList()}
function save(){clearTimeout(saveTimer);saveTimer=null;let r=rows.find(x=>x.voice_id===current);if(!r)return;const id=r.voice_id,payload=JSON.stringify({id,text:r.verified_text,status:state(r)});saving=saving.catch(()=>{}).then(async()=>{let res=await fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},body:payload});if(!res.ok)throw Error(await res.text());if(current===id&&$('#saveStatus'))$('#saveStatus').textContent='保存済み';renderList()}).catch(e=>{if($('#saveStatus')){$('#saveStatus').textContent='保存エラー: '+e.message;$('#saveStatus').className='error'}throw e})}function move(n){let items=filtered(),idx=items.findIndex(r=>r.voice_id===current);if(idx<0&&items.length)show(items[0].voice_id);else if(items[idx+n])show(items[idx+n].voice_id)}['duration','status','search'].forEach(x=>$('#'+x).oninput=renderList);document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key==='Enter'&&$('#confirm')){e.preventDefault();$('#confirm').click()}if(e.altKey&&e.key==='ArrowRight'){e.preventDefault();move(1)}if(e.altKey&&e.key==='ArrowLeft'){e.preventDefault();move(-1)}});fetch('/data').then(r=>r.json()).then(data=>{rows=data;renderList();let first=filtered()[0];if(first)show(first.voice_id)}).catch(e=>$('#detail').textContent='読み込みエラー: '+e.message);
</script></body></html>'''


def load_items(review, base):
    result = {}
    with review.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            path = Path(row['audio_path'])
            if not path.is_absolute(): path = base / path
            path = path.resolve()
            if not path.is_relative_to(base.resolve()) or not path.is_file() or path.suffix.lower() != '.wav': continue
            try:
                with wave.open(str(path), 'rb') as w: duration = w.getnframes() / w.getframerate()
            except (OSError, EOFError, wave.Error, ZeroDivisionError): continue
            id = row['voice_id']
            if id in result: raise ValueError(f'Duplicate voice_id: {id}')
            result[id] = {**row, 'file': str(path), 'duration': duration, 'candidate_count': int(row.get('candidate_count') or 0)}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--review',type=Path,default=Path(__file__).resolve().parent/'voice_caption_review.csv')
    p.add_argument('--base',type=Path,default=Path.cwd(),help='Directory containing shro_voices')
    p.add_argument('--db',type=Path,default=Path(__file__).resolve().parent/'voice_review.sqlite3')
    p.add_argument('--port',type=int,default=8765)
    args=p.parse_args(); items=load_items(args.review,args.base)
    if not items: p.error('No WAV files found. Run from the GkmasObjectManager directory.')
    def connect():
        c=sqlite3.connect(args.db,timeout=30);c.execute('CREATE TABLE IF NOT EXISTS review (id TEXT PRIMARY KEY, text TEXT NOT NULL, status TEXT NOT NULL)');return c
    with connect(): pass
    class Handler(BaseHTTPRequestHandler):
        def reply(self,content,content_type,status=200):
            self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(content)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(content)
        def do_GET(self):
            parsed=urllib.parse.urlparse(self.path)
            if parsed.path=='/':return self.reply(HTML.encode(),'text/html; charset=utf-8')
            if parsed.path=='/data':
                with connect() as db: saved={r[0]:(r[1],r[2]) for r in db.execute('SELECT id,text,status FROM review')}
                data=[{**{k:v for k,v in r.items() if k!='file'},'verified_text':saved.get(id,('', 'todo'))[0],'review_status':saved.get(id,('', 'todo'))[1]} for id,r in items.items()]
                return self.reply(json.dumps(data,ensure_ascii=False).encode(),'application/json; charset=utf-8')
            if parsed.path=='/audio':
                id=urllib.parse.parse_qs(parsed.query).get('id',[''])[0]
                if id not in items:return self.reply(b'Not found','text/plain',404)
                return self.reply(Path(items[id]['file']).read_bytes(),'audio/wav')
            if parsed.path=='/export':
                with connect() as db: saved={r[0]:(r[1],r[2]) for r in db.execute('SELECT id,text,status FROM review')}
                out=io.StringIO(newline='');w=csv.writer(out);w.writerow(['voice_id','audio_path','duration_seconds','candidate_texts','sources','verified_text','review_status'])
                for id,r in items.items():
                    text,status=saved.get(id,('', 'todo'));w.writerow([id,r['audio_path'],f"{r['duration']:.3f}",r['candidate_texts'],r['sources'],text,status])
                data=out.getvalue().encode('utf-8-sig');self.send_response(200);self.send_header('Content-Type','text/csv; charset=utf-8');self.send_header('Content-Disposition','attachment; filename="voice_review_export.csv"');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
            self.reply(b'Not found','text/plain',404)
        def do_POST(self):
            if self.path!='/save':return self.reply(b'Not found','text/plain',404)
            try:
                if self.headers.get('Origin') not in (None, f'http://127.0.0.1:{args.port}',f'http://localhost:{args.port}'): raise ValueError('Invalid origin')
                length=int(self.headers.get('Content-Length','0'))
                if length<=0 or length>100000: raise ValueError('Invalid length')
                data=json.loads(self.rfile.read(length)); id=data['id'];text=data['text'];status=data['status']
                if id not in items or status not in ('todo','confirmed','skip') or not isinstance(text,str): raise ValueError('Invalid data')
                if status=='confirmed' and not text.strip(): raise ValueError('Text required')
                with connect() as db:db.execute('INSERT INTO review(id,text,status) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET text=excluded.text,status=excluded.status',(id,text,status))
                self.reply(b'ok','text/plain')
            except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e:self.reply(str(e).encode(),'text/plain; charset=utf-8',400)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Loaded {len(items)} WAV files. Open http://127.0.0.1:{args.port}',flush=True)
    print(f'Autosave database: {args.db.resolve()}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: print('\nStopped.')
    finally:server.server_close()

if __name__=='__main__':main()
