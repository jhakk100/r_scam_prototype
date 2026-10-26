"""Exercise real HTTP routes against a disposable board, never user posts."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import server
from community import Community


class BoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / 'community.sqlite3'
        cls.previous = server.board
        server.board = Community(cls.path)
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.worker = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.worker.start()
        cls.base = f'http://127.0.0.1:{cls.http.server_port}'
        cls.client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.worker.join(timeout=5)
        server.board = cls.previous
        cls.temp.cleanup()

    def request(self, path='', value=None, status=200, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        request = urllib.request.Request(self.base + '/api/community/posts' + path,
            data=None if value is None else json.dumps(value).encode(), headers=headers)
        try:
            response = self.client.open(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            self.assertEqual(response.status, status)
            data = json.load(response)
        self.assertNotIn('digest', json.dumps(data))
        self.assertNotIn('salt', json.dumps(data))
        self.assertNotIn('password', json.dumps(data))
        return data

    def setUp(self):
        # Every case owns a clean disposable DB, independent of test order/failures.
        server.board.attempts.clear()
        with server.board.connect() as db:
            db.execute('DELETE FROM posts')

    def test_full_lifecycle_and_guards(self):
        value = {'category': '의심 정황', 'author': '익명', 'title': '출금 전 세금을 요구해요',
                 'body': '확인을 요청했습니다.\n<script>alert(1)</script>',
                 'password': 'test-secret-3924', 'privacy_checked': True}
        self.request('', {**value, 'privacy_checked': False}, 400)
        self.request('', {**value, 'password': '123'}, 400)
        self.request('', value, 403, origin='https://another.example')
        self.request('', [], 400)
        post = self.request('', value, 201)
        path = '/' + post['id']
        self.assertEqual(self.request(path)['body'], value['body'])
        found = self.request('?q=%EC%B6%9C%EA%B8%88')
        self.assertTrue(any(p['id'] == post['id'] for p in found['posts']))
        self.assertEqual(self.request('?q=%25')['total'], 0)
        self.request('?page=0', status=400)
        self.request('?page=abc', status=400)
        self.request('/missing', status=404)
        for action in ('edit', 'delete'):
            self.request(path + '/' + action, {**value, 'password': 'wrong-password', 'revision': 1}, 403)
        self.assertEqual(self.request(path)['revision'], 1)
        changed = self.request(path + '/edit', {**value, 'title': '공식 경로로 확인했어요', 'revision': 1})
        self.assertEqual(changed['revision'], 2)
        self.request(path + '/edit', {**value, 'revision': 1}, 409)
        self.assertEqual(Community(self.path).get(post['id'])['title'], '공식 경로로 확인했어요')
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute('SELECT salt, digest FROM posts WHERE id=?', (post['id'],)).fetchone()
            self.assertEqual(len(row[0]), 16)
            self.assertEqual(len(row[1]), 32)
            self.assertNotEqual(row[1], value['password'].encode())
        # Reset the per-minute test counter before a separate successful delete.
        server.board.attempts.clear()
        self.request(path + '/delete', {'password': value['password'], 'revision': 2})
        self.request(path, status=404)
        self.assertFalse(self.request()['posts'])

    def test_comment_lifecycle_and_post_scope(self):
        server.board.attempts.clear()
        value = {'category':'정보 공유','author':'글 작성자','title':'댓글 기능 검증','body':'임시 테스트 글',
                 'password':'post-only-secret','privacy_checked':True}
        post = self.request('',value,201)
        other = self.request('',value,201)
        path = '/' + post['id'] + '/comments'
        comment = {'author':'댓글 작성자','body':'<script>test</script>\n확인한 경험입니다.',
                   'password':'comment-only-secret','privacy_checked':True}
        self.request(path,{**comment,'privacy_checked':False},400)
        self.request(path,{**comment,'body':'x'*2001},400)
        self.request(path,{**comment,'password':'123'},400)
        self.request(path,comment,403,origin='https://another.example')
        saved = self.request(path,comment,201)
        ident = path + '/' + saved['id']
        self.assertEqual(self.request(path)['comments'][0]['body'],comment['body'])
        self.assertEqual(Community(self.path).comments(post['id'])['total'],1)
        for action in ('edit','delete'):
            self.request(ident+'/'+action,{**comment,'password':'incorrect-secret','revision':1},403)
        # A post password cannot authorize changing someone else's comment.
        self.request(ident+'/edit',{**comment,'password':value['password'],'revision':1},403)
        self.request('/'+other['id']+'/comments/'+saved['id']+'/delete',
                     {'password':comment['password'],'revision':1},404)
        changed = self.request(ident+'/edit',{**comment,'body':'수정한 의견','revision':1})
        self.assertEqual(changed['revision'],2)
        server.board.attempts.clear()
        self.request(ident+'/edit',{**comment,'revision':1},409)
        with closing(sqlite3.connect(self.path)) as db:
            salt,digest = db.execute('SELECT salt,digest FROM comments WHERE id=?',(saved['id'],)).fetchone()
            self.assertEqual(len(salt),16)
            self.assertEqual(len(digest),32)
        server.board.attempts.clear()
        for _ in range(5):
            self.request(ident+'/delete',{'password':'incorrect-secret','revision':2},403)
        self.request(ident+'/delete',{'password':'incorrect-secret','revision':2},429)
        server.board.attempts.clear()
        self.request(ident+'/delete',{'password':comment['password'],'revision':2})
        self.assertEqual(self.request(path)['total'],0)
        self.request(path,comment,201)
        self.request('/'+post['id']+'/delete',{'password':value['password'],'revision':1})
        self.request(path,status=404)
        self.request(path,comment,404)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM comments WHERE post_id=?',(post['id'],)).fetchone()[0],0)
        self.request('/'+other['id']+'/delete',{'password':value['password'],'revision':1})

    def test_comment_pages_and_legacy_database(self):
        server.board.attempts.clear()
        value = {'category':'정보 공유','author':'익명','title':'페이지 검증','body':'임시 글',
                 'password':'temporary-secret','privacy_checked':True}
        post = self.request('',value,201)
        path = '/'+post['id']+'/comments'
        for i in range(21):
            self.request(path,{'author':'익명','body':str(i),'password':'comment-test-secret','privacy_checked':True},201)
        self.assertEqual(len(self.request(path)['comments']),20)
        self.assertEqual(self.request(path+'?page=2')['comments'][0]['body'],'20')
        self.request(path+'?page=0',status=400)
        self.request('/'+post['id']+'/delete',{'password':value['password'],'revision':1})
        # Existing pre-comment installations retain their posts during schema creation.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'legacy.sqlite3'
            with closing(sqlite3.connect(path)) as db:
                db.execute('''CREATE TABLE posts (id TEXT PRIMARY KEY, category TEXT, title TEXT, author TEXT,
                    body TEXT, created INTEGER, updated INTEGER, revision INTEGER, salt BLOB, digest BLOB)''')
                db.execute('INSERT INTO posts VALUES (?,?,?,?,?,1,1,1,?,?)',
                           ('a'*32,'정보 공유','기존 글','기존 작성자','보존해야 하는 내용',b's'*16,b'd'*32))
                db.commit()
            migrated = Community(path)
            self.assertEqual(migrated.get('a'*32)['body'],'보존해야 하는 내용')
            self.assertEqual(migrated.comments('a'*32)['total'],0)

    def test_pagination_and_password_throttle(self):
        value = {'category':'피해 경험', 'author':'테스트', 'title':'검증 전용', 'body':'테스트 내용',
                 'password':'temporary-password', 'privacy_checked':True}
        server.board.attempts.clear()
        posts = [self.request('', value, 201) for _ in range(11)]
        self.assertEqual(len(self.request()['posts']), 10)
        self.assertEqual(len(self.request('?page=2')['posts']), 1)
        self.assertEqual(self.request('?category=%EC%A0%95%EB%B3%B4%20%EA%B3%B5%EC%9C%A0')['total'], 0)
        for _ in range(5):
            self.request('/' + posts[0]['id'] + '/delete', {'password':'wrong-password', 'revision':1}, 403)
        self.request('/' + posts[0]['id'] + '/delete', {'password':'wrong-password', 'revision':1}, 429)
        # DB and test posts are discarded by TemporaryDirectory.

    @unittest.skipUnless((HERE / 'bootstrap.py').is_file(), 'Application update test runs from homepage source')
    def test_source_update_preserves_data_and_model(self):
        # Freshly restored and previously used bundles both receive current UI.
        import bootstrap
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'data').mkdir()
            (root / 'data/community.sqlite3').write_bytes(b'existing-user-data')
            (root / 'model.safetensors').write_bytes(b'unchanged-model')
            (root / 'manifest.json').write_text(json.dumps({'files': {'model.safetensors':
                {'bytes': 15, 'sha256': 'original-model-hash', 'category': 'base_model'}}}), encoding='utf-8')
            bootstrap.update_application(root)
            first = (root / 'manifest.json').read_bytes()
            bootstrap.update_application(root)
            self.assertEqual((root / 'manifest.json').read_bytes(), first)
            self.assertEqual((root / 'data/community.sqlite3').read_bytes(), b'existing-user-data')
            self.assertEqual((root / 'model.safetensors').read_bytes(), b'unchanged-model')
            self.assertEqual((root / 'app/community.js').read_bytes(), (HERE / 'app/community.js').read_bytes())


if __name__ == '__main__':
    unittest.main(verbosity=2)
