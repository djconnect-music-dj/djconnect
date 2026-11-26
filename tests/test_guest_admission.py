"""Temporary share/guest authority behavior; no physical or installed HA claim."""
import importlib
from pathlib import Path
import secrets
import sys
from types import ModuleType
import unittest


class GuestAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = '_guest_authority_unit'
        package = ModuleType(cls.package)
        package.__path__ = [str(Path(__file__).resolve().parents[1]/'custom_components/djconnect')]
        sys.modules[cls.package] = package
        cls.display = importlib.import_module(cls.package+'.display_admission')
        cls.guest = importlib.import_module(cls.package+'.guest_admission')

    @classmethod
    def tearDownClass(cls):
        for name in tuple(sys.modules):
            if name == cls.package or name.startswith(cls.package+'.'):
                del sys.modules[name]

    def setUp(self):
        self.now = 100.0
        self.live = True
        self.device_live = True
        self.state = self.display.DisplayAdmissionState(lambda: self.now)
        self.owner = self.display.DisplayOwnerBinding('host-private-profile', 'session', 'paired-entry', 'real-stamp', lambda: self.live)
        claim = self.state.create_claim(source='source', browser_nonce=secrets.token_urlsafe(32))
        approval = self.state.approve(owner=self.owner, issuer_epoch=claim['issuer_epoch'],
            claim_id=claim['claim_id'], browser_generation=claim['browser_generation'], code=claim['code'],
            share={'mode':'create','consent':True,'lifetime_seconds':7200})
        self.share_id = approval['share_id']
        self.guests = self.state.participation

    def enable(self, **kwargs):
        self.guests.configure(owner=self.owner, share_id=self.share_id,
            policy=self.guest.ParticipationPolicy(information=True, **kwargs))

    def join(self, invitation=None):
        invitation = invitation or self.guests.invite(owner=self.owner, share_id=self.share_id)
        return self.guests.redeem(**{k:invitation[k] for k in ('invitation_id','invitation_secret','issuer_epoch')}, source='client')

    def authenticate(self, response):
        return self.guests.authorize(guest_id=response['guest_id'], token=response['guest_token'],
                                     issuer_epoch=response['issuer_epoch'])

    def test_participation_defaults_off_and_never_copies_display_token(self):
        with self.assertRaises(self.display.DisplayAdmissionError):
            self.guests.invite(owner=self.owner, share_id=self.share_id)
        self.enable()
        result = self.join()
        self.assertFalse(result['capabilities']['owner_controls'])
        self.assertFalse(result['capabilities']['profile_history'])
        self.assertFalse(result['capabilities']['music_dna'])
        self.assertFalse(result['capabilities']['request_song'])
        self.assertTrue(result['guest_token'].startswith('djcg_'))
        self.assertNotIn(result['guest_token'], repr(self.guests._guests))
        self.assertNotIn(self.owner.profile_id, repr(result))

    def test_single_use_redemption_does_not_mint_another_grant_after_lost_response(self):
        self.enable()
        invite = self.guests.invite(owner=self.owner, share_id=self.share_id)
        first = self.join(invite)
        with self.assertRaises(self.display.DisplayAdmissionError):
            self.join(invite)
        self.assertEqual(len(self.guests._guests), 1)
        self.authenticate(first)

    def test_rotation_withdraws_invitation_without_rejecting_admitted_guest(self):
        self.enable()
        first = self.join()
        invite = self.guests.invite(owner=self.owner, share_id=self.share_id)
        self.guests.invite(owner=self.owner, share_id=self.share_id)
        with self.assertRaises(self.display.DisplayAdmissionError):
            self.join(invite)
        self.authenticate(first)

    def test_share_end_and_source_withdrawal_immediately_close_original_grant(self):
        for reason in ('end','owner'):
            with self.subTest(reason=reason):
                self.setUp()
                self.enable()
                result = self.join()
                grant = self.authenticate(result)
                invalidated = []
                grant.invalidated = lambda: invalidated.append(True)
                if reason == 'end':
                    self.state.revoke_session('session')
                else:
                    self.live = False
                    self.state.prune()
                with self.assertRaises(self.display.DisplayAdmissionError):
                    self.authenticate(result)
                self.assertEqual(invalidated, [True])

    def test_party_enabled_for_existing_display_keeps_song_requests_on(self):
        self.enable(requests='auto_queue')
        self.assertTrue(self.state._shares[self.share_id].party_requests)
        self.enable()
        self.assertEqual(self.guests._policies[self.share_id].policy.requests, 'auto_queue')
        self.assertTrue(self.join()['capabilities']['request_song'])

    def test_policy_withdrawal_and_regrant_never_reauthorize_original_principal(self):
        self.enable(requests='auto_queue')
        original = self.join()
        self.guests.configure(owner=self.owner, share_id=self.share_id, policy=self.guest.ParticipationPolicy())
        self.enable(requests='auto_queue')
        with self.assertRaises(self.display.DisplayAdmissionError):
            self.authenticate(original)
        self.assertNotEqual(self.join()['guest_id'], original['guest_id'])

    def test_expiry_renewal_replay_and_runtime_clear_preserve_original_deadline(self):
        self.enable()
        result = self.join()
        grant = self.authenticate(result)
        self.now += 10
        self.guests.renew(grant, 1)
        deadline = grant.lease_deadline
        self.now += 10
        self.guests.renew(grant, 1)
        self.assertEqual(grant.lease_deadline, deadline)
        self.now = deadline
        with self.assertRaises(self.display.DisplayAdmissionError):
            self.authenticate(result)
        self.state.clear()
        self.assertEqual(self.guests._guests, {})

    def test_real_endpoint_binding_does_not_name_a_human_or_survive_registry_change(self):
        self.enable()
        self.guests.bind_voice(owner=self.owner, share_id=self.share_id, endpoint_id='actual-registry-device',
                               current=lambda: self.device_live)
        grant = self.guests.voice('actual-registry-device')
        self.assertEqual(grant.kind, 'voice')
        self.assertEqual(grant.secret_hash, '')
        self.assertFalse(self.guests.public(grant)['capabilities']['owner_controls'])
        self.device_live = False
        with self.assertRaises(self.display.DisplayAdmissionError):
            self.guests.validate(grant)
        with self.assertRaises(self.display.DisplayAdmissionError):
            self.guests.voice('actual-registry-device')

    def test_foreign_owner_and_malformed_policy_cannot_grant_participation(self):
        other = self.display.DisplayOwnerBinding('different', 'session', 'paired-entry', 'stamp', lambda: True)
        with self.assertRaises(self.display.DisplayAdmissionError):
            self.guests.configure(owner=other, share_id=self.share_id, policy=self.guest.ParticipationPolicy(information=True))
        for kwargs in ({'information':1}, {'requests':'auto_queue'}, {'max_pending':True}, {'requests':[]}):
            with self.subTest(kwargs=kwargs), self.assertRaises(self.display.DisplayAdmissionError):
                self.guest.ParticipationPolicy(**kwargs)

    def test_identical_host_policy_and_endpoint_retry_keep_original_guest(self):
        self.enable(requests='review')
        self.guests.bind_voice(owner=self.owner,share_id=self.share_id,endpoint_id='actual-room',current=lambda:True)
        voice = self.guests.voice('actual-room')
        browser = self.authenticate(self.join())
        generation = voice.generation
        self.enable(requests='review')
        self.guests.bind_voice(owner=self.owner,share_id=self.share_id,endpoint_id='actual-room',current=lambda:True)
        self.assertIs(self.guests.voice('actual-room'),voice)
        self.assertEqual(voice.generation,generation)
        self.guests.validate(browser)

    def test_owner_invitation_and_display_qr_keep_the_same_single_use_invitation(self):
        self.enable()
        invited = self.guests.invite(owner=self.owner,share_id=self.share_id)
        qr = self.guests.display_invitation(self.share_id)
        self.assertEqual(invited['invitation_id'],qr['invitation_id'])
        self.assertEqual(invited['invitation_secret'],qr['invitation_secret'])
        self.join(invited)
        self.assertNotEqual(self.guests.display_invitation(self.share_id)['invitation_id'],invited['invitation_id'])

    def test_fresh_turn_and_actual_model_budgets_are_distinct_and_share_scoped(self):
        self.enable()
        first = self.authenticate(self.join())
        for _ in range(8):
            self.guests.charge_model(first)
        with self.assertRaises(self.display.DisplayAdmissionError):
            self.guests.charge_model(first)
        for _ in range(12):
            self.guests.charge_turn(first)
        with self.assertRaises(self.display.DisplayAdmissionError):
            self.guests.charge_turn(first)
        for _ in range(3):
            other = self.authenticate(self.join())
            for _ in range(12):
                self.guests.charge_turn(other)
        last = self.authenticate(self.join())
        with self.assertRaises(self.display.DisplayAdmissionError):
            self.guests.charge_turn(last)
