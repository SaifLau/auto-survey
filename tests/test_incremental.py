import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import incremental as m
import state


def paper(**kw):
    return dict(title='Edge inference kernels', kind='paper', category='operator',
                url='https://arxiv.org/abs/2610.12345v1', **kw)


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = m.load(self.root)

    def test_duplicate_versions_and_title(self):
        d = m.scan(self.data, [paper(), paper()], 'a')
        self.assertEqual(len(d['items']), 1)
        self.assertEqual(len(d['outbox']), 1)
        other = paper()
        other['url'] = 'https://example.org/paper'
        d = m.scan(d, [other], 'b')
        self.assertEqual(len(d['items']), 1)

    def test_update_then_unchanged(self):
        d = m.scan(self.data, [paper(summary='v1')], 'a')
        p = paper(summary='v2')
        d = m.scan(d, [p], 'a')
        d = m.scan(d, [p], 'a')
        self.assertEqual([e['type'] for e in d['outbox']], ['first', 'update'])

    def test_persistence_and_no_new(self):
        d = m.scan(self.data, [paper()], 'a', 'cursor')
        state.save(d, self.root)
        path = m.generate(m.load(self.root), self.root)
        self.assertIn('首次发现', path.read_text())
        restored = m.load(self.root)
        self.assertEqual(restored['sources']['a']['cursor'], 'cursor')
        restored = m.scan(restored, [paper()], 'a')
        path = m.generate(restored, self.root)
        self.assertIn('无新增', path.read_text())
        self.assertIsNone(restored['outbox'][0]['delivered_at'])

    def test_corrupt_state_recovery(self):
        state.save(self.data, self.root)
        state.save(self.data, self.root)
        state.state_path(self.root).write_text('{broken')
        self.assertEqual(m.load(self.root)['items'], {})
        self.assertTrue(state.state_path(self.root).with_suffix('.corrupt').exists())

    def test_invalid_batch_does_not_advance(self):
        before = copy.deepcopy(self.data)
        with self.assertRaises(ValueError):
            m.scan(self.data, [paper(), dict(paper(), url='javascript:alert(1)')], 'a', 'bad')
        self.assertEqual(self.data, before)

    def test_unknown_dates_and_background(self):
        d = m.normalize(paper(published_at='2099-01-01', affiliations=None))
        self.assertIsNone(d['published_at'])
        self.assertEqual(d['verification'], 'unverified-import')
        self.assertIn('未知', m.render([{'type': 'first', 'record': d}]))

    def test_report_failure_keeps_pending(self):
        d = m.scan(self.data, [paper()], 'a')
        state.save(d, self.root)
        with patch.object(m.os, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                m.generate(d, self.root)
        self.assertIsNone(m.load(self.root)['outbox'][0]['rendered_at'])

    def test_alternating_sources_do_not_republish(self):
        a = paper(summary='v1')
        b = dict(paper(summary='v2'), url='https://arxiv.org/abs/2610.12345v2')
        d = self.data
        for r in (a, b, a, b):
            d = m.scan(d, [r], 'replay')
        self.assertEqual(len(d['outbox']), 2)
        self.assertEqual(next(iter(d['items'].values()))['record']['summary'], 'v2')

    def test_lock(self):
        with m.locked(self.root):
            with self.assertRaises(FileExistsError):
                with m.locked(self.root):
                    pass

    def test_github_pagination(self):
        row = dict(draft=False, prerelease=False, name='Metal kernels', tag_name='v1',
                   html_url='https://github.com/a/b/releases/tag/v1', body='kernel change', published_at='2026-01-01')
        with patch.object(m, 'get_json', side_effect=[[row] * 100, []]) as get:
            self.assertEqual(len(m.releases('a/b')), 100)
            self.assertEqual(get.call_count, 2)

    def test_arxiv_adapter(self):
        import io
        xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://arxiv.org/abs/2610.12345v2</id><title>Edge</title><summary>Kernel</summary><author><name>A</name></author><published>2026-01-01</published><updated>2026-02-01</updated></entry></feed>'
        with patch.object(m.urllib.request, 'urlopen', return_value=io.BytesIO(xml)):
            rows = m.arxiv('edge', 10)
        self.assertEqual(rows[0]['authors'], ['A'])
        self.assertEqual(m.normalize(rows[0])['arxiv_id'], '2610.12345')

    def test_original_survey_compatible(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('survey_init', Path(m.__file__).with_name('init.py'))
        init = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(init)
        with patch.object(Path, 'cwd', return_value=self.root):
            init.init_workspace('test')
        self.assertEqual(state.load(self.root)['phase'], 'init')
        with self.assertRaises(ValueError):
            m.main(['--workspace', str(self.root), 'status'])

if __name__ == '__main__':
    unittest.main()
