import hashlib
import json
import math
import sqlite3
import threading
import time
from pathlib import Path
from .protocol import validate, timestamp


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.directory / 'index.sqlite3', check_same_thread=False)
        self.state = sqlite3.connect(self.directory / 'settings.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA wal_autocheckpoint=10000;
          CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,path TEXT,meta TEXT,revision INTEGER DEFAULT 0);
          CREATE TABLE IF NOT EXISTS cursors(path TEXT PRIMARY KEY,offset INTEGER,signature TEXT);
          CREATE TABLE IF NOT EXISTS points(run TEXT,key TEXT,session TEXT,step INTEGER,epoch REAL,time REAL,seq INTEGER,value REAL,PRIMARY KEY(run,key,session,step));
          CREATE INDEX IF NOT EXISTS point_range ON points(run,key,session,step);
          CREATE INDEX IF NOT EXISTS point_step_cover ON points(run,key,step,value,session,epoch,seq);
          CREATE INDEX IF NOT EXISTS point_epoch_cover ON points(run,key,epoch,value,session,step,seq);
          CREATE INDEX IF NOT EXISTS point_session ON points(run,session,step DESC);
          CREATE INDEX IF NOT EXISTS point_latest ON points(run,key,seq DESC);
          CREATE INDEX IF NOT EXISTS point_best ON points(run,key,value,seq DESC);
          CREATE INDEX IF NOT EXISTS point_activity ON points(run,time);
          CREATE INDEX IF NOT EXISTS point_epoch ON points(run,key,session,epoch);
          CREATE TABLE IF NOT EXISTS events(run TEXT,session TEXT,time REAL,seq INTEGER,kind TEXT,PRIMARY KEY(run,seq));
          CREATE TABLE IF NOT EXISTS issues(path TEXT,message TEXT,UNIQUE(path,message));
        ''')
        self.state.executescript('CREATE TABLE IF NOT EXISTS roots(path TEXT PRIMARY KEY); CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);')
        self.curve_cache = {}
        self.stop = threading.Event()
        self.progress = {'scanning': False, 'found': 0}

    def roots(self):
        with self.lock:
            return [r[0] for r in self.state.execute('SELECT path FROM roots')]

    def add(self, path):
        path = Path(path).resolve()
        if not path.is_dir():
            raise ValueError('目录不存在或不是目录')
        # Opening the directory catches common permission failures before saving it.
        next(path.iterdir(), None)
        with self.lock, self.state:
            self.state.execute('INSERT OR IGNORE INTO roots VALUES(?)', (str(path),))
        return str(path)

    def remove(self, path):
        with self.lock, self.state:
            self.state.execute('DELETE FROM roots WHERE path=?', (path,))
        # Existing indexed records remain visible; source files are untouched.

    def setting(self, key, value=None, write=False):
        with self.lock:
            if write:
                with self.state:
                    self.state.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, json.dumps(value)))
                return value
            row = self.state.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def issue(self, path, error):
        self.db.execute('INSERT OR IGNORE INTO issues VALUES(?,?)', (str(path), str(error)[:500]))

    def scan(self, roots=None):
        self.progress = {'scanning': True, 'found': 0}
        try:
            for root in roots if roots is not None else self.roots():
                if self.stop.is_set():
                    break
                try:
                    base = Path(root)
                    if not base.is_dir():
                        raise ValueError('来源目录已不可用，请重新添加目录')
                    for path in base.rglob('run.json'):
                        if self.stop.is_set():
                            break
                        self.progress['found'] += 1
                        try:
                            self.ingest(path)
                        except Exception as error:
                            with self.lock, self.db:
                                self.issue(path, error)
                except Exception as error:
                    with self.lock, self.db:
                        self.issue(root, error)
        finally:
            self.progress['scanning'] = False

    def ingest(self, path):
        meta = validate(json.loads(path.read_text(encoding='utf-8')))
        rid = meta['run_id']
        encoded = json.dumps(meta, sort_keys=True, ensure_ascii=False)
        with self.lock, self.db:
            old = self.db.execute('SELECT * FROM runs WHERE id=?', (rid,)).fetchone()
            if old and old['path'] != str(path):
                original = Path(old['path'])
                if original.exists():
                    same = old['meta'] == encoded
                    for name in ('metrics.jsonl', 'events.jsonl'):
                        a, b = original.parent / name, path.parent / name
                        same = same and (a.read_bytes() if a.exists() else b'') == (b.read_bytes() if b.exists() else b'')
                    if not same:
                        raise ValueError('Run ID 冲突：不同内容不能合并')
                    return
            self.db.execute('INSERT INTO runs(id,path,meta) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET path=excluded.path,meta=excluded.meta', (rid, str(path), encoded))
            for name in ('metrics.jsonl', 'events.jsonl'):
                file = path.parent / name
                if not file.exists():
                    continue
                stat = file.stat()
                with file.open('rb') as stream:
                    head = stream.read(min(256, stat.st_size))
                cursor = self.db.execute('SELECT * FROM cursors WHERE path=?', (str(file),)).fetchone()
                offset = cursor['offset'] if cursor else 0
                # Prefix signature uses only already committed bytes, so appends do not reset it.
                def fingerprint(stream, committed):
                    stream.seek(0)
                    prefix = stream.read(min(256, committed))
                    stream.seek(max(0, committed-256))
                    tail = stream.read(min(256, committed))
                    return hashlib.sha256(str(stat.st_ino).encode()+prefix+tail).hexdigest()
                with file.open('rb') as stream:
                    signature = fingerprint(stream, offset)
                if cursor and (stat.st_size < offset or signature != cursor['signature']):
                    self.db.execute('DELETE FROM points WHERE run=?', (rid,))
                    self.db.execute('DELETE FROM events WHERE run=?', (rid,))
                    self.db.execute('DELETE FROM cursors WHERE path IN (?,?)', (str(path.parent/'metrics.jsonl'), str(path.parent/'events.jsonl')))
                    self.db.execute('UPDATE runs SET revision=revision+1 WHERE id=?', (rid,))
                    # Restart both streams after a reset, inside the same transaction.
                    return self.ingest(path)
                if cursor and stat.st_size == offset:
                    continue
                changed = False
                batch_count = 0
                session_steps = dict(self.db.execute('SELECT session,MAX(step) FROM points WHERE run=? GROUP BY session', (rid,)))
                with file.open('rb') as stream:
                    stream.seek(offset)
                    while not self.stop.is_set():
                        line = stream.readline()
                        if not line or not line.endswith(b'\n'):
                            break
                        offset = stream.tell()
                        try:
                            r = json.loads(line)
                            seq, session = r['seq'], r['session_id']
                            if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1 or not isinstance(session, str) or not session:
                                raise ValueError('无效序号或训练阶段')
                            ts = timestamp(r['time'])
                            if name == 'events.jsonl':
                                if r['kind'] not in ('started', 'resumed', 'heartbeat', 'completed', 'failed'):
                                    raise ValueError('未知生命周期事件')
                                self.db.execute('INSERT OR REPLACE INTO events VALUES(?,?,?,?,?)', (rid, session, ts, seq, r['kind']))
                            else:
                                step = r['step']
                                epoch = r.get('epoch')
                                if isinstance(step, bool) or not isinstance(step, int) or step < 0:
                                    raise ValueError('step 必须是非负整数')
                                if epoch is not None and (isinstance(epoch, bool) or not isinstance(epoch, (int,float)) or not math.isfinite(epoch) or epoch < 0):
                                    raise ValueError('epoch 必须是非负有限数值')
                                values = r['values']
                                if not values or any(k not in meta['metrics'] or isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) for k,v in values.items()):
                                    raise ValueError('指标必须已定义且为有限数值')
                                previous = session_steps.get(session)
                                if previous is not None and step < previous:
                                    raise ValueError('同一训练阶段内 step 不可回退')
                                self.db.executemany('''INSERT INTO points VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(run,key,session,step) DO UPDATE SET epoch=excluded.epoch,time=excluded.time,seq=excluded.seq,value=excluded.value WHERE excluded.seq>points.seq''', [(rid,k,session,step,epoch,ts,seq,v) for k,v in values.items()])
                            if name == 'metrics.jsonl':
                                session_steps[session] = step
                            changed = True
                            batch_count += 1
                            if batch_count % 2048 == 0:
                                position = stream.tell()
                                stream.seek(0)
                                checkpoint = fingerprint(stream, offset)
                                stream.seek(position)
                                self.db.execute('INSERT OR REPLACE INTO cursors VALUES(?,?,?)', (str(file), offset, checkpoint))
                                self.db.execute('UPDATE runs SET revision=revision+1 WHERE id=?', (rid,))
                                self.db.commit()
                                self.lock.release()
                                try:
                                    time.sleep(.001)
                                finally:
                                    self.lock.acquire()
                        except (ValueError, KeyError, TypeError, UnicodeError) as error:
                            self.issue(f'{file}:{offset-len(line)}', error)
                    stream.seek(0)
                    signature = fingerprint(stream, offset)
                self.db.execute('INSERT OR REPLACE INTO cursors VALUES(?,?,?)', (str(file), offset, signature))
                if changed:
                    self.db.execute('UPDATE runs SET revision=revision+1 WHERE id=?', (rid,))

    def runs(self, limit=50, offset=0):
        with self.lock:
            rows = self.db.execute('SELECT * FROM runs ORDER BY json_extract(meta,\'$.created_at\') DESC LIMIT ? OFFSET ?', (limit,offset)).fetchall()
            return [self.detail(row['id']) for row in rows]

    def detail(self, rid):
        with self.lock:
            row = self.db.execute('SELECT * FROM runs WHERE id=?', (rid,)).fetchone()
            if not row:
                raise KeyError(rid)
            meta = json.loads(row['meta'])
            event = self.db.execute('SELECT * FROM events WHERE run=? ORDER BY seq DESC LIMIT 1', (rid,)).fetchone()
            last = self.db.execute('SELECT MAX(time) FROM points WHERE run=?', (rid,)).fetchone()[0]
            status = event['kind'] if event else 'unknown'
            if status not in ('completed', 'failed'):
                status = 'running' if time.time() - max(last or 0, event['time'] if event else 0) <= 30 else 'interrupted'
            sessions = [r[0] for r in self.db.execute('SELECT session FROM events WHERE run=? GROUP BY session ORDER BY MIN(seq)', (rid,))]
            return dict(meta=meta, revision=row['revision'], status=status, sessions=sessions, source=str(Path(row['path']).parent))

    def summary(self, rid):
        meta = self.detail(rid)['meta']
        result = {}
        with self.lock:
            for key, definition in meta['metrics'].items():
                latest = self.db.execute('SELECT step,epoch,value,session FROM points WHERE run=? AND key=? ORDER BY seq DESC LIMIT 1', (rid,key)).fetchone()
                order = 'ASC' if definition['direction']=='min' else 'DESC'
                best = self.db.execute(f'SELECT step,epoch,value,session FROM points WHERE run=? AND key=? ORDER BY value {order},seq DESC LIMIT 1', (rid,key)).fetchone() if definition['direction']!='none' else None
                result[key] = dict(latest=dict(latest) if latest else None,best=dict(best) if best else None)
        return result

    def curve(self, rid, key, session=None, axis='step', low=None, high=None, budget=2000):
        if axis not in ('step','epoch'):
            raise ValueError('未知横轴')
        budget = max(4,min(2000,budget))
        where, args = 'run=? AND key=?', [rid,key]
        if session:
            where += ' AND session=?'; args.append(session)
        if low is not None:
            where += f' AND {axis}>=?'; args.append(low)
        if high is not None:
            where += f' AND {axis}<=?'; args.append(high)
        where += f' AND {axis} IS NOT NULL'
        with self.lock:
            revision = self.db.execute('SELECT revision FROM runs WHERE id=?', (rid,)).fetchone()
            cache_key = (rid, key, session, axis, low, high, budget, revision[0] if revision else 0)
            if cache_key in self.curve_cache:
                return self.curve_cache[cache_key]
            index = 'point_step_cover' if axis == 'step' else 'point_epoch_cover'
            stats = self.db.execute(f'SELECT COUNT(*),MIN({axis}),MAX({axis}),MIN(value),MAX(value) FROM points INDEXED BY {index} WHERE {where}', args).fetchone()
            count,xmin,xmax,ymin,ymax = stats
            columns = f'{axis} AS x,value,session,step,epoch,seq'
            if count <= budget:
                points = self.db.execute(f'SELECT {columns} FROM points INDEXED BY {index} WHERE {where} ORDER BY seq',args).fetchall()
            else:
                buckets = max(1,budget//4)
                selected = {}
                bucket_where = "run=? AND key=?" + (" AND session=?" if session else "")
                bucket_args = [rid,key] + ([session] if session else [])
                width = max((xmax-xmin+1e-9)/buckets, 1e-9)
                for bucket in range(buckets):
                    left = xmin + bucket*width
                    right = xmin + (bucket+1)*width
                    for ordering in ((axis+' ASC', axis+' DESC', 'value ASC', 'value DESC') if session else ('seq ASC', 'seq DESC', 'value ASC', 'value DESC')):
                        point = self.db.execute(f'SELECT {columns} FROM points INDEXED BY {index} WHERE {bucket_where} AND {axis}>=? AND {axis}<? ORDER BY {ordering} LIMIT 1', [*bucket_args,left,right]).fetchone()
                        if point:
                            selected[(point['session'],point['step'])] = point
                points = sorted(selected.values(), key=lambda p:p['seq'])
            result = dict(points=[dict(p) for p in points],count=count,x_min=xmin,x_max=xmax,y_min=ymin,y_max=ymax,downsampled=count>budget)
            if len(self.curve_cache) >= 64:
                self.curve_cache.pop(next(iter(self.curve_cache)))
            self.curve_cache[cache_key] = result
            return result

    def start(self):
        def work():
            while not self.stop.is_set():
                self.scan()
                self.stop.wait(2)
        self.thread = threading.Thread(target=work, daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if hasattr(self,'thread'):
            self.thread.join()
        with self.lock:
            self.db.close(); self.state.close()
