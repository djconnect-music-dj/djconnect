"""Shared playback metadata uses real projection/share owners, synthetic samples."""
from dataclasses import replace
import hashlib
import importlib
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from tests import test_display_projection as fixtures


class DisplayObservedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.DisplayProjectionTests.setUpClass()
        cls.observed = importlib.import_module('custom_components.djconnect.display_observed')
        cls.samples = importlib.import_module('custom_components.djconnect.surface_status_samples')
        cls.Occurrence = importlib.import_module('custom_components.djconnect.track_start_announcement').Occurrence

    @classmethod
    def tearDownClass(cls):
        fixtures.DisplayProjectionTests.tearDownClass()

    def setUp(self):
        self.fixture = fixtures.DisplayProjectionTests()
        self.fixture.prepared()
        self.state, self.active = self.fixture.state, self.fixture.session
        self.share = self.state._shares[self.fixture.display.share_id]
        self.source_live = True
        self.set_track('A')
        # The source/clock boundary is explicitly synthetic; no provider I/O.
        witness = SimpleNamespace(current=lambda *args, **kwargs: self.source_live)
        self.sample = self.samples.OriginalSample(witness, 1795467000000, 101,
                                                 'playing', False, str(uuid.uuid4()))

    def set_track(self, character):
        track_id = character * 22
        self.track = 'spotify:track:' + track_id
        item_id = hashlib.sha256(self.track.encode()).hexdigest()[:24]
        state = self.active.broadcast.state
        self.active.broadcast.state = replace(state, playback=replace(state.playback,
            state='playing', item_id=item_id, title='Observed title', artist='Observed artist',
            album='Observed album', source_url='https://open.spotify.com/track/' + track_id))

    def occurrence(self, *, repeated=False):
        return self.Occurrence('occurrence-' + uuid.uuid4().hex, self.track,
            'Observed title', 'Observed artist', '', 101, 113, (), repeated=repeated)

    def capture(self, **kwargs):
        self.observed.capture(self.state, self.active, self.sample, self.track, **kwargs)

    def test_public_item_is_metadata_only_without_moment_or_private_identity(self):
        self.capture()
        rows = self.fixture.snapshot()['observed_playback']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['title'], 'Observed title')
        self.assertEqual(set(rows[0]), {'entry_id', 'playback_item_id', 'title', 'artist',
                                      'album', 'source_url', 'observed_at', 'expires_at'})
        self.assertEqual(rows, self.observed.public(self.share, self.state))
        self.assertNotIn('moment_id', rows[0])
        original = self.share.observed_playback
        for _ in range(10):
            self.fixture.snapshot()
        self.assertIs(self.share.observed_playback, original)

    def test_polling_same_recording_never_creates_or_renews_an_occurrence(self):
        self.capture()
        original = self.share.observed_playback
        self.sample = replace(self.sample, observed_ms=self.sample.observed_ms + 15000,
                              observed_monotonic=116, sample_id=str(uuid.uuid4()))
        self.capture()
        self.assertIs(self.share.observed_playback, original)
        self.assertEqual(original[0].deadline, 1901)
        with patch.object(self.state, '_clock', return_value=1901):
            self.assertEqual(self.observed.public(self.share, self.state), [])

    def test_start_and_following_polls_share_one_row(self):
        start = self.occurrence()
        self.capture(occurrence=start)
        original = self.share.observed_playback
        self.sample = replace(self.sample, observed_ms=self.sample.observed_ms + 3000,
                              observed_monotonic=104, sample_id=str(uuid.uuid4()))
        self.capture()
        self.capture(occurrence=start)
        self.assertIs(self.share.observed_playback, original)
        self.assertEqual(original[0].entry_id, start.occurrence_id)
        self.assertEqual(len(self.fixture.snapshot()['observed_playback']), 1)

    def test_same_recording_only_adds_a_second_row_on_confirmed_repeat(self):
        self.capture()
        original = self.share.observed_playback
        self.capture(occurrence=self.occurrence())
        self.assertIs(self.share.observed_playback, original)
        repeat = self.occurrence(repeated=True)
        self.capture(occurrence=repeat)
        self.capture()
        self.capture(occurrence=repeat)
        rows = self.fixture.snapshot()['observed_playback']
        self.assertEqual([row['entry_id'] for row in rows],
                         [original[0].entry_id, repeat.occurrence_id])
        self.assertEqual(rows[0]['playback_item_id'], rows[1]['playback_item_id'])

    def test_return_to_a_recording_gets_its_own_fallback_row(self):
        for track in 'ABA':
            self.set_track(track)
            self.capture()
        rows = self.fixture.snapshot()['observed_playback']
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({row['entry_id'] for row in rows}), 3)
        self.assertEqual(rows[0]['playback_item_id'], rows[2]['playback_item_id'])

    def test_source_withdrawal_fences_prepared_snapshot(self):
        self.capture()
        snapshot = self.fixture.snapshot()
        guard = self.fixture.projection.projection_release_guard(
            self.active, self.fixture.display, self.state, snapshot)
        with patch('time.monotonic', return_value=101):
            self.assertTrue(guard())
            self.source_live = False
            self.assertFalse(guard())
        self.assertEqual(self.fixture.snapshot()['observed_playback'], [])

    def test_share_end_scrubs_the_original_object_and_pending_response(self):
        self.capture()
        self.state._drop_share(self.share.share_id)
        self.assertEqual(self.share.observed_playback, ())
        self.assertEqual(self.share.observed_key, '')
        self.assertEqual(self.share.observed_item_id, '')
        self.assertEqual(self.observed.public(self.share, self.state), [])

    def test_unaccepted_wrong_recording_and_nonplaying_samples_do_not_add_rows(self):
        self.source_live = False
        self.capture()
        self.source_live = True
        self.sample = replace(self.sample, state='paused')
        self.capture()
        self.sample = replace(self.sample, state='playing')
        self.observed.capture(self.state, self.active, self.sample, 'spotify:track:' + 'B' * 22)
        self.observed.capture(self.state, self.active, self.sample, None)
        self.assertEqual(self.share.observed_playback, ())
