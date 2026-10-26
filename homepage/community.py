"""Local anonymous board. Passwords authorize changes to one post only."""
import hashlib
from contextlib import contextmanager
import hmac
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid

CATEGORIES = ('의심 정황', '피해 경험', '정보 공유')
ITERATIONS = 600_000


class BoardError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Community:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.initialized = False
        self.attempts = {}

    @contextmanager
    def connect(self):
        with self.lock:
            if not self.initialized:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                db = sqlite3.connect(self.path)
                try:
                    db.execute('''CREATE TABLE IF NOT EXISTS posts (
                        id TEXT PRIMARY KEY, category TEXT NOT NULL,
                        title TEXT NOT NULL, author TEXT NOT NULL, body TEXT NOT NULL,
                        created INTEGER NOT NULL, updated INTEGER NOT NULL,
                        revision INTEGER NOT NULL, salt BLOB NOT NULL, digest BLOB NOT NULL)''')
                    db.execute('CREATE INDEX IF NOT EXISTS posts_created ON posts(created DESC, id DESC)')
                    db.execute('''CREATE TABLE IF NOT EXISTS comments (
                        id TEXT PRIMARY KEY, post_id TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                        author TEXT NOT NULL, body TEXT NOT NULL, created INTEGER NOT NULL,
                        updated INTEGER NOT NULL, revision INTEGER NOT NULL, salt BLOB NOT NULL, digest BLOB NOT NULL)''')
                    db.execute('CREATE INDEX IF NOT EXISTS comments_post ON comments(post_id, created)')
                    db.commit()
                finally:
                    db.close()
                self.initialized = True
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA foreign_keys = ON')
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def throttle(self, key, limit):
        now = time.monotonic()
        with self.lock:
            self.attempts = {k: v for k, v in self.attempts.items() if v[0] > now - 60}
            start, count = self.attempts.get(key, (now, 0))
            if count >= limit:
                raise BoardError('시도가 많아요. 1분 뒤 다시 시도해 주세요.', 429)
            self.attempts[key] = (start, count + 1)

    @staticmethod
    def fields(value):
        if not isinstance(value, dict):
            raise BoardError('글 내용을 확인해 주세요.')
        result = {}
        for key, label, maximum in (('title', '제목', 100), ('author', '닉네임', 20), ('body', '내용', 8000)):
            text = value.get(key)
            if not isinstance(text, str) or not text.strip() or len(text.strip()) > maximum or '\x00' in text:
                raise BoardError(f'{label}은 1~{maximum:,}자로 입력해 주세요.')
            result[key] = text.strip()
        if value.get('category') not in CATEGORIES:
            raise BoardError('글 분류를 선택해 주세요.')
        if value.get('privacy_checked') is not True:
            raise BoardError('개인정보를 가렸는지 확인해 주세요.')
        result['category'] = value['category']
        return result

    @staticmethod
    def password(value, label='글'):
        password = value.get('password') if isinstance(value, dict) else None
        if not isinstance(password, str) or not 6 <= len(password) <= 128:
            raise BoardError(f'{label} 비밀번호는 6~128자로 입력해 주세요.')
        return password

    @staticmethod
    def public(row, detail=False):
        keys = ('id', 'category', 'title', 'author', 'created', 'updated', 'revision')
        data = {key: row[key] for key in keys}
        data['body' if detail else 'preview'] = row['body'] if detail else row['body'][:140]
        return data

    def list(self, query='', category='', page=1):
        if len(query) > 100 or (category and category not in CATEGORIES) or not 1 <= page <= 100000:
            raise BoardError('검색 조건을 확인해 주세요.')
        # instr treats search terms literally, including SQL wildcards.
        where = "WHERE (instr(title, ?) > 0 OR instr(body, ?) > 0) AND (? = '' OR category = ?)"
        values = (query, query, category, category)
        with self.connect() as db:
            total = db.execute('SELECT count(*) FROM posts ' + where, values).fetchone()[0]
            rows = db.execute('SELECT * FROM posts ' + where +
                ' ORDER BY created DESC, id DESC LIMIT 10 OFFSET ?', (*values, (page-1)*10)).fetchall()
        return {'posts': [self.public(row) for row in rows], 'total': total, 'page': page, 'page_size': 10}

    def get(self, ident):
        with self.connect() as db:
            row = db.execute('SELECT * FROM posts WHERE id = ?', (ident,)).fetchone()
        if row is None:
            raise BoardError('글을 찾을 수 없어요. 삭제되었을 수 있습니다.', 404)
        return self.public(row, True)

    def create(self, value, client):
        fields = self.fields(value)
        password = self.password(value)
        self.throttle(('write', client), 30)
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
        ident, now = uuid.uuid4().hex, int(time.time())
        with self.connect() as db:
            db.execute('INSERT INTO posts VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)',
                (ident, fields['category'], fields['title'], fields['author'], fields['body'], now, now, salt, digest))
        return self.get(ident)

    def change(self, ident, action, value, client):
        password = self.password(value)
        fields = self.fields(value) if action == 'edit' else None
        revision = value.get('revision')
        if type(revision) is not int or revision < 1:
            raise BoardError('글을 다시 열고 시도해 주세요.')
        self.throttle(('write', client), 30)
        self.throttle(('password', client, ident), 5)
        with self.connect() as db:
            row = db.execute('SELECT * FROM posts WHERE id = ?', (ident,)).fetchone()
            if row is None:
                raise BoardError('글을 찾을 수 없어요.', 404)
            digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), row['salt'], ITERATIONS)
            if not hmac.compare_digest(digest, row['digest']):
                raise BoardError('글 비밀번호가 맞지 않아요.', 403)
            if action == 'delete':
                result = db.execute('DELETE FROM posts WHERE id = ? AND revision = ?', (ident, revision))
            else:
                result = db.execute('''UPDATE posts SET category=?, title=?, author=?, body=?,
                    updated=?, revision=revision+1 WHERE id=? AND revision=?''',
                    (fields['category'], fields['title'], fields['author'], fields['body'], int(time.time()), ident, revision))
            if result.rowcount != 1:
                raise BoardError('다른 창에서 글이 변경됐어요. 글을 다시 열어 주세요.', 409)
        return {'deleted': True} if action == 'delete' else self.get(ident)

    @staticmethod
    def comment_fields(value):
        if not isinstance(value, dict):
            raise BoardError('댓글 내용을 확인해 주세요.')
        fields = {}
        for key, label, limit in (('author', '닉네임', 20), ('body', '댓글', 2000)):
            text = value.get(key)
            if not isinstance(text, str) or not text.strip() or len(text.strip()) > limit or '\x00' in text:
                raise BoardError(f'{label}은 1~{limit:,}자로 입력해 주세요.')
            fields[key] = text.strip()
        if value.get('privacy_checked') is not True:
            raise BoardError('댓글의 개인정보를 가렸는지 확인해 주세요.')
        return fields

    @staticmethod
    def public_comment(row):
        return {key: row[key] for key in ('id', 'post_id', 'author', 'body', 'created', 'updated', 'revision')}

    def comments(self, post_id, page=1):
        if not 1 <= page <= 100000:
            raise BoardError('페이지를 확인해 주세요.')
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM posts WHERE id=?', (post_id,)).fetchone():
                raise BoardError('글을 찾을 수 없어요.', 404)
            total = db.execute('SELECT count(*) FROM comments WHERE post_id=?', (post_id,)).fetchone()[0]
            rows = db.execute('SELECT * FROM comments WHERE post_id=? ORDER BY created, rowid LIMIT 20 OFFSET ?',
                              (post_id, (page-1)*20)).fetchall()
        return {'comments': [self.public_comment(row) for row in rows], 'total': total, 'page': page, 'page_size': 20}

    def create_comment(self, post_id, value, client):
        fields = self.comment_fields(value)
        password = self.password(value, '댓글')
        self.throttle(('write', client), 30)
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
        ident, now = uuid.uuid4().hex, int(time.time())
        with self.connect() as db:
            result = db.execute('''INSERT INTO comments
                SELECT ?, ?, ?, ?, ?, ?, 1, ?, ? WHERE EXISTS (SELECT 1 FROM posts WHERE id=?)''',
                (ident, post_id, fields['author'], fields['body'], now, now, salt, digest, post_id))
            if result.rowcount != 1:
                raise BoardError('글을 찾을 수 없어요.', 404)
            row = db.execute('SELECT * FROM comments WHERE id=?', (ident,)).fetchone()
        return self.public_comment(row)

    def change_comment(self, post_id, ident, action, value, client):
        password = self.password(value, '댓글')
        fields = self.comment_fields(value) if action == 'edit' else None
        revision = value.get('revision')
        if type(revision) is not int or revision < 1:
            raise BoardError('댓글을 다시 불러온 뒤 시도해 주세요.')
        self.throttle(('write', client), 30)
        self.throttle(('comment-password', client, ident), 5)
        with self.connect() as db:
            row = db.execute('SELECT * FROM comments WHERE id=? AND post_id=?', (ident, post_id)).fetchone()
            if row is None:
                raise BoardError('댓글을 찾을 수 없어요.', 404)
            digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), row['salt'], ITERATIONS)
            if not hmac.compare_digest(digest, row['digest']):
                raise BoardError('댓글 비밀번호가 맞지 않아요.', 403)
            if action == 'delete':
                result = db.execute('DELETE FROM comments WHERE id=? AND post_id=? AND revision=?',
                                    (ident, post_id, revision))
            else:
                result = db.execute('''UPDATE comments SET author=?, body=?, updated=?, revision=revision+1
                    WHERE id=? AND post_id=? AND revision=?''',
                    (fields['author'], fields['body'], int(time.time()), ident, post_id, revision))
            if result.rowcount != 1:
                raise BoardError('다른 창에서 댓글이 변경됐어요. 다시 불러와 주세요.', 409)
            updated = db.execute('SELECT * FROM comments WHERE id=?', (ident,)).fetchone() if action == 'edit' else None
        return {'deleted': True} if action == 'delete' else self.public_comment(updated)
