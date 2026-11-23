"""Real Core paired-purpose helpers with synthetic HA/provider seams."""
import importlib
import unittest
from unittest.mock import patch
from tests import test_display_service as fixtures


class GuestServiceTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.DisplayServiceTests.setUpClass()
        cls.module = importlib.import_module('custom_components.djconnect.guest_service')

    @classmethod
    def tearDownClass(cls):
        fixtures.DisplayServiceTests.tearDownClass()

    async def asyncSetUp(self):
        self.fixture = fixtures.DisplayServiceTests()
        await self.fixture.asyncSetUp()
        self.admitted = await self.fixture.admitted()
        self.share_id = self.admitted.payload['share_id']
        self.service = self.module.GuestParticipationService(self.fixture.fixture.hass, self.fixture.manager)

    async def asyncTearDown(self):
        await self.fixture.asyncTearDown()

    async def call(self, action, payload=None, headers=None, origins=None):
        data = {'contract_version':1, **(payload or {})}
        if action.startswith('owner/'):
            data.update(identity=self.fixture.fixture.identity, share_id=self.share_id,
                        session_id=self.fixture.fixture.active.session_id)
        return await self.service.post(action, data,
            headers=self.fixture.fixture.headers if headers is None else headers,
            origins=[self.fixture.origin] if origins is None else origins, source='guest-unit-peer')

    async def enable(self):
        return await self.call('owner/configure', {'policy':{'information':True,'requests':'review','max_pending':3}})

    async def join(self):
        await self.enable()
        invited = (await self.call('owner/invite')).payload
        return await self.call('redeem', {k:invited[k] for k in ('issuer_epoch','invitation_id','invitation_secret')}, headers={})

    async def test_only_current_paired_host_can_configure_or_issue_invitation(self):
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.call('owner/configure', {'policy':{'information':True,'requests':'review','max_pending':3}}, headers={})
        await self.enable()
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.call('owner/invite', headers={})

    async def test_guest_is_separate_from_host_and_display_and_cannot_promote_itself(self):
        joined = await self.join()
        guest = joined.payload
        self.assertTrue(guest['capabilities']['request_song'])
        self.assertFalse(guest['capabilities']['owner_controls'])
        binding = {k:guest[k] for k in ('guest_id','issuer_epoch')}
        headers = {'Authorization':'Bearer '+guest['guest_token']}
        result = await self.call('context', binding, headers=headers)
        self.assertEqual(result.payload['guest_id'], guest['guest_id'])
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.call('owner/configure', {'policy':{'information':True,'requests':'auto_queue','max_pending':3}}, headers=headers)
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.call('context', binding, headers={'Authorization':'Bearer '+self.admitted.payload['grant_token']})

    async def test_withdrawal_after_response_preparation_rejects_original_release(self):
        joined = await self.join()
        await self.call('owner/configure', {'policy':{'information':False,'requests':'disabled','max_pending':3}})
        with self.assertRaises(self.module.DisplayAdmissionError):
            joined.release()

    async def test_wrong_origin_and_foreign_payload_cannot_enter_guest_scope(self):
        joined = await self.join()
        guest = joined.payload
        binding = {k:guest[k] for k in ('guest_id','issuer_epoch')}
        for payload, origins in ((binding, []), (binding, ['https://foreign.example']),
                                  ({**binding,'profile_id':'owner'}, [self.fixture.origin]),
                                  ({**binding,'contract_version':True}, [self.fixture.origin])):
            with self.subTest(payload=payload, origins=origins), self.assertRaises(self.module.DisplayAdmissionError):
                await self.call('context', payload, origins=origins, headers={'Authorization':'Bearer '+guest['guest_token']})

    async def test_share_end_invalidates_guest_without_ending_another_session(self):
        joined = await self.join()
        self.fixture.manager._display_admission.revoke_session(self.fixture.fixture.active.session_id)
        with self.assertRaises(self.module.DisplayAdmissionError):
            joined.release()

    async def test_public_context_withdrawal_after_headers_blocks_original_body(self):
        guest = (await self.join()).payload
        binding = {k:guest[k] for k in ('guest_id', 'issuer_epoch')}
        presentation = importlib.import_module('custom_components.djconnect.guest_presentation')
        with patch.object(presentation, 'public_context', return_value={
                'playback':{}, 'moments':[{'moment_id':'original', 'summary':'public at capture'}]}) as public:
            result = await self.call('context', binding,
                headers={'Authorization':'Bearer '+guest['guest_token']})
            result.release()
            public.return_value = {'playback':{}, 'moments':[]}
            with self.assertRaises(self.module.DisplayAdmissionError):
                result.release()
