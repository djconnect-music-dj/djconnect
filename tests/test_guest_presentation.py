"""Real qualified shared publication; focus never publishes or extends its rights."""
from types import SimpleNamespace
import importlib
import unittest
from tests import test_display_projection as fixtures


class GuestPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.DisplayProjectionTests.setUpClass()
        cls.module = importlib.import_module('custom_components.djconnect.guest_presentation')
        cls.guests = importlib.import_module('custom_components.djconnect.guest_admission')

    @classmethod
    def tearDownClass(cls):
        fixtures.DisplayProjectionTests.tearDownClass()

    def setUp(self):
        self.fixture = fixtures.DisplayProjectionTests()
        self.fixture.setUp()
        self.moment = self.fixture.prepared()
        self.state = self.fixture.state
        self.admission = self.state.participation
        self.share_id = self.fixture.display.share_id
        self.configure()

    def tearDown(self):
        self.fixture.tearDown()

    def configure(self, enabled=True):
        self.admission.configure(owner=self.fixture.owner, share_id=self.share_id,
            policy=self.guests.ParticipationPolicy(True, 'review', 3, enabled))
        invite = self.admission.invite(owner=self.fixture.owner, share_id=self.share_id)
        joined = self.admission.redeem(invitation_id=invite['invitation_id'],
            invitation_secret=invite['invitation_secret'],issuer_epoch=invite['issuer_epoch'],source='unit')
        self.grant = self.admission.authorize(guest_id=joined['guest_id'], token=joined['guest_token'],
                                             issuer_epoch=joined['issuer_epoch'])
        self.actor = SimpleNamespace(grant=self.grant, share=self.state._shares[self.share_id],
            active=self.fixture.session, manager=SimpleNamespace(_display_admission=self.state, current_active=lambda _:self.fixture.session))
        self.actor.validate = lambda: self.admission.validate(self.grant)
        return self.actor

    def test_focus_uses_original_publication_without_duplicate_or_playback_change(self):
        before = self.fixture.session.broadcast.state
        result = self.module.focus(self.actor, self.moment.moment_id)
        shown = self.module.display_focus(None, self.actor.manager, self.fixture.display)
        self.assertEqual(result['focused_moment_id'], self.moment.moment_id)
        self.assertEqual(shown['focused_moment_id'], self.moment.moment_id)
        self.assertTrue(shown['focus_revision'])
        self.assertIs(self.fixture.session.broadcast.state, before)
        self.module.focus(self.actor, None)
        self.assertIsNone(self.module.display_focus(None, self.actor.manager, self.fixture.display)['focused_moment_id'])
        self.assertIs(self.fixture.session.broadcast.state, before)

    def test_shared_information_does_not_grant_screen_focus(self):
        self.configure(False)
        self.assertIn(self.moment.moment_id,
            self.module.shared_items(self.fixture.session, now=self.state._clock()))
        with self.assertRaises(self.module.SessionConversationError):
            self.module.focus(self.actor, self.moment.moment_id)

    def test_private_or_unknown_reference_cannot_be_shown(self):
        with self.assertRaises(self.module.SessionConversationError):
            self.module.focus(self.actor, 'another-concert-or-private-history')
        target = {'session_id':'another-session','moment_id':self.moment.moment_id}
        with self.assertRaises(self.module.SessionConversationError):
            self.module.selected_shared_moment(self.actor, target)

    def test_withdrawn_publication_removes_original_focus(self):
        self.module.focus(self.actor, self.moment.moment_id)
        self.fixture.session.broadcast.deleted_moment_ids.add(self.moment.moment_id)
        result = self.module.display_focus(None, self.actor.manager, self.fixture.display)
        self.assertIsNone(result['focused_moment_id'])
        self.assertNotIn(self.share_id, self.admission._focus)

    def test_expired_guest_cannot_keep_focus_on_display(self):
        self.module.focus(self.actor, self.moment.moment_id)
        self.grant.lease_deadline = self.state._clock()
        self.assertIsNone(self.module.display_focus(None, self.actor.manager, self.fixture.display)['focused_moment_id'])

    def test_five_language_commands_only_select_presentation(self):
        for text in ('toon dit op het scherm','show that on the screen','zeige das auf dem bildschirm',
                     'affiche ce moment sur l’écran','muestra este en la pantalla'):
            self.assertEqual(self.module.presentation_action(text), 'focus', text)
        for text in ('terug naar live','back to live','zurück zu live','revenir au direct','volver al directo'):
            self.assertEqual(self.module.presentation_action(text), 'return', text)
        for text in ('pause','end session','show my private history','request a song'):
            self.assertIsNone(self.module.presentation_action(text))
