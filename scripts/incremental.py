#!/usr/bin/env python3
"""Independent, resumable edge-inference collector and Markdown outbox (stdlib only)."""
import argparse
import copy
import hashlib
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
import state
from score_paper import score

TOPIC = 'edge inference quantization kernels Metal CUDA mobile deployment MoE'
CATEGORIES = ('architecture', 'framework', 'operator', 'hardware')


def now():
    return datetime.now(timezone.utc).isoformat()


def url(value):
    if not isinstance(value, str) or any(c.isspace() or c in '<>' for c in value):
        raise ValueError('invalid source URL')
    p = urllib.parse.urlsplit(value)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('source URL must be an absolute HTTP(S) URL')
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'),
                                   urllib.parse.urlencode([(k, v) for k, v in urllib.parse.parse_qsl(p.query)
                                                          if not k.startswith('utm_')]), ''))


def date(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if parsed > datetime.now(timezone.utc):
            return None
        return parsed.isoformat()
    except (ValueError, TypeError):
        return None


def normalize(raw):
    d = {k: raw.get(k) for k in ('title', 'kind', 'category', 'summary', 'authors',
                                 'affiliations', 'lab', 'company', 'background', 'repository', 'version')}
    if not isinstance(d['title'], str) or not d['title'].strip():
        raise ValueError('title required')
    if d['category'] not in CATEGORIES or d['kind'] not in ('paper', 'release', 'news'):
        raise ValueError('invalid kind/category')
    d['url'] = url(raw.get('url'))
    d['published_at'] = date(raw.get('published_at'))
    d['updated_at'] = date(raw.get('updated_at'))
    # A valid URL/date is syntax validation, never proof that the claim is true.
    d['evidence'] = raw.get('evidence') or {}
    d['link_status'] = raw.get('link_status', 'unchecked')
    d['verification'] = 'source-metadata' if raw.get('_trusted_adapter') else 'unverified-import'
    d['doi'] = re.sub(r'^https?://(?:dx\.)?doi.org/', '', raw.get('doi') or '', flags=re.I).lower()
    match = re.search(r'arxiv.org/(?:abs|pdf)/([^?#]+)', d['url'])
    d['arxiv_id'] = re.sub(r'v\d+$', '', (raw.get('arxiv_id') or (match[1].removesuffix('.pdf') if match else '')))
    d['relevance'] = score(TOPIC, d['title'], d['summary'] or '')['score']
    return d


def aliases(d):
    keys = ['url:' + d['url']]
    if d['doi']:
        keys.append('doi:' + d['doi'])
    if d['arxiv_id']:
        keys.append('arxiv:' + d['arxiv_id'])
    if d['kind'] == 'paper':
        keys.append('title:' + ''.join(c for c in unicodedata.normalize('NFKC', d['title']).casefold() if c.isalnum()))
    return keys


def digest(d):
    return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def load(root):
    try:
        return state.load(root)
    except FileNotFoundError:
        if state.backup_path(root).exists():
            return json.loads(state.backup_path(root).read_text())
        return {'schema_version': 1, 'mode': 'incremental', 'items': {}, 'sources': {}, 'outbox': []}
    except json.JSONDecodeError:
        recovered = json.loads(state.backup_path(root).read_text())
        # Preserve corrupt bytes and prevent save() from overwriting the good backup.
        state.state_path(root).rename(state.state_path(root).with_suffix('.corrupt'))
        return recovered


@contextmanager
def locked(root):
    p = state.state_dir(root)
    p.mkdir(parents=True, exist_ok=True)
    lock = p / 'scan.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        os.close(fd)
        lock.unlink()


def scan(data, records, source, cursor=None):
    staged = copy.deepcopy(data)
    index = {a: key for key, item in staged['items'].items() for a in item['aliases']}
    stamp = now()
    # Validate entire batch before committing its cursor.
    for d in [normalize(r) for r in records]:
        aa = aliases(d)
        matches = {index[a] for a in aa if a in index}
        if len(matches) > 1:
            raise ValueError('conflicting identities; reconcile records before retry')
        key = next(iter(matches), digest(aa))
        old = staged['items'].get(key)
        revision = digest({k: v for k, v in d.items() if k not in ('link_status', 'verification')})
        if old and revision in old.get('seen_revisions', []):
            old['last_seen_at'] = stamp
            old['aliases'] = sorted(set(old['aliases'] + aa))
            for a in aa:
                index[a] = key
            continue
        if old:
            old['last_seen_at'] = stamp
            old['aliases'] = sorted(set(old['aliases'] + aa))
            # Sparse search results must not erase previously known metadata.
            d = {k: (old['record'].get(k) if v in (None, '', [], {}) else v) for k, v in d.items()}
        fingerprint = digest(d)
        if not old or fingerprint != old['fingerprint']:
            event = {'item_id': key, 'type': 'update' if old else 'first',
                     'fingerprint': fingerprint, 'record': d, 'discovered_at': stamp,
                     'rendered_at': None, 'delivered_at': None}
            staged['outbox'].append(event)
            staged['items'][key] = {'record': d, 'fingerprint': fingerprint,
                'aliases': sorted(set(aa + (old['aliases'] if old else []))),
                'seen_revisions': sorted(set([revision] + (old.get('seen_revisions', []) if old else []))),
                'first_seen_at': old['first_seen_at'] if old else stamp, 'last_seen_at': stamp}
        if old and fingerprint == old['fingerprint']:
            old.setdefault('seen_revisions', []).append(revision)
        for a in aa:
            index[a] = key
    staged['sources'][source] = {'cursor': cursor, 'last_success_at': stamp}
    return staged


def get_json(endpoint):
    req = urllib.request.Request(endpoint, headers={'User-Agent': 'auto-survey-incremental/1', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def releases(repo):
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
        raise ValueError('repository must be owner/name')
    result, page = [], 1
    while True:
        rows = get_json(f'https://api.github.com/repos/{repo}/releases?per_page=100&page={page}')
        for r in rows:
            if not r['draft'] and not r['prerelease']:
                result.append({'title': r['name'] or r['tag_name'], 'kind': 'release',
                    'category': 'framework', 'repository': 'https://github.com/' + repo,
                    'version': r['tag_name'], 'url': r['html_url'], 'summary': r['body'],
                    'published_at': r['published_at'], '_trusted_adapter': True})
        if len(rows) < 100:
            return result
        page += 1


def arxiv(query, limit):
    endpoint = 'https://export.arxiv.org/api/query?' + urllib.parse.urlencode(
        {'search_query': query, 'start': 0, 'max_results': limit, 'sortBy': 'lastUpdatedDate', 'sortOrder': 'descending'})
    with urllib.request.urlopen(endpoint, timeout=30) as response:
        feed = ET.fromstring(response.read())
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    rows = []
    for e in feed.findall('a:entry', ns):
        rows.append({'title': e.findtext('a:title', namespaces=ns).strip(), 'kind': 'paper',
            'category': 'architecture', 'url': e.findtext('a:id', namespaces=ns),
            'summary': e.findtext('a:summary', namespaces=ns).strip(),
            'authors': [x.findtext('a:name', namespaces=ns) for x in e.findall('a:author', ns)],
            'published_at': e.findtext('a:published', namespaces=ns),
            'updated_at': e.findtext('a:updated', namespaces=ns), '_trusted_adapter': True})
    return rows


def safe(v):
    if isinstance(v, list):
        v = ', '.join(str(x) for x in v)
    return str(v or '未知').replace('\n', ' ').replace('<', '&lt;').replace('>', '&gt;').replace('[', '\\[').replace(']', '\\]')


def render(events):
    lines = ['# 端侧推理增量简报', '', '首次发现不等于首次发表；未知信息不作推断。', '']
    if not events:
        return '\n'.join(lines + ['本次无新增或更新。', ''])
    for e in events:
        d = e['record']
        lines += [f"## {'首次发现' if e['type'] == 'first' else '后续更新'} · {safe(d['title'])}", '',
            f"- 类别：{d['category']} / {d['kind']}",
            f"- 原始来源：<{d['url']}>",
            f"- 发布：{safe(d['published_at'])}；更新：{safe(d['updated_at'])}",
            f"- 作者：{safe(d['authors'])}；单位：{safe(d['affiliations'])}；实验室：{safe(d['lab'])}",
            f"- 公司及背景：{safe(d['company'])}；{safe(d['background'])}",
            f"- 仓库：{safe(d['repository'])}；版本：{safe(d['version'])}",
            f"- 技术变化 / 摘要：{safe(d['summary'])}",
            f"- 核验：{d['verification']}；链接：{d['link_status']}；证据：{safe(d['evidence'])}", '']
    return '\n'.join(lines)


def generate(data, root):
    events = [e for e in data['outbox'] if not e['rendered_at']]
    body = render(events)
    report_id = digest(events)[:16]
    path = state.state_dir(root) / 'briefs' / (report_id + '.md')
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(body, encoding='utf-8')
    os.replace(tmp, path)
    for e in events:
        e['rendered_at'] = now()
        e['brief_path'] = str(path)
    state.save(data, root)
    return path


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, default=Path('.auto-survey/incremental'))
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('scan')
    source = s.add_mutually_exclusive_group(required=True)
    source.add_argument('--input', type=Path)
    source.add_argument('--github', metavar='OWNER/REPO')
    source.add_argument('--arxiv', metavar='QUERY')
    s.add_argument('--limit', type=int, default=100)
    s.add_argument('--verify-links', action='store_true', help='GET source links; HTTP success does not verify claims')
    s.add_argument('--source-id', default='import')
    sub.add_parser('brief')
    sub.add_parser('status')
    args = p.parse_args(argv)
    with locked(args.workspace):
        data = load(args.workspace)
        if data.get('mode') != 'incremental':
            raise ValueError('not an incremental workspace')
        if args.command == 'scan':
            if args.input:
                envelope = json.loads(args.input.read_text())
                rows = envelope['items']
                for r in rows:
                    r.pop('_trusted_adapter', None)
                source_id, cursor = args.source_id, envelope.get('cursor')
            elif args.github:
                rows = releases(args.github)
                source_id, cursor = 'github:' + args.github, now()
            else:
                rows = arxiv(args.arxiv, args.limit)
                source_id, cursor = 'arxiv:' + args.arxiv, now()
            if args.verify_links:
                for r in rows:
                    target = url(r.get('url'))
                    try:
                        req = urllib.request.Request(target, headers={'User-Agent': 'auto-survey-incremental/1'})
                        with urllib.request.urlopen(req, timeout=20) as response:
                            r['link_status'] = 'reachable' if response.status == 200 else 'unknown'
                    except OSError:
                        r['link_status'] = 'unreachable'
            data = scan(data, rows, source_id, cursor)
            state.save(data, args.workspace)
            print(json.dumps({'items': len(data['items']), 'pending': sum(not e['rendered_at'] for e in data['outbox'])}))
        elif args.command == 'brief':
            print(generate(data, args.workspace))
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
