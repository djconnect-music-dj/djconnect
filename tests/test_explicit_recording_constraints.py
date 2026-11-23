"""Literal recording identity survives parsing, stale proposals and provider rank."""
import asyncio
from copy import deepcopy
import importlib
import types
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from tests.test_spotify_backend import install_backend_stubs


class RecordingConstraintsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_backend_stubs()
        cls.music = importlib.import_module('custom_components.djconnect.music_intent')
        cls.spotify = importlib.import_module('custom_components.djconnect.spotify')
        cls.backend = importlib.import_module('custom_components.djconnect.spotify_backend')
        cls.processor = importlib.import_module('custom_components.djconnect.processor')

    def test_literal_recording_in_five_languages_not_album_or_stale_model(self):
        phrases = (
            'Speel Children van Armin van Buuren van het album Piano',
            'Play Children by Armin van Buuren from the album Piano',
            'Spiele Children von Armin van Buuren aus dem Album Piano',
            "Joue Children de Armin van Buuren de l’album Piano",
            'Reproduce Children de Armin van Buuren del álbum Piano',
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                parsed = self.music.parse_spoken_music_request(phrase)
                self.assertEqual(parsed['type'], 'track')
                self.assertEqual((parsed['title'], parsed['artist'], parsed['album']),
                                 ('Children', 'Armin van Buuren', 'Piano'))
                bound = self.processor._request_bound_music_intent(phrase,
                    {'type':'album','title':'What If I Told You','artist':'Unrelated','album':'Other'})
                self.assertEqual((bound['type'],bound['title'],bound['artist'],bound['album']),
                                 ('track','Children','Armin van Buuren','Piano'))

    def test_unknown_output_is_not_discarded_from_literal_album(self):
        parsed = self.music.parse_spoken_music_request(
            'Speel Children van Armin van Buuren van het album Piano op Denon Home 150 Schuur.')
        self.assertEqual(parsed['type'], 'track')
        self.assertEqual(parsed['album'], 'Piano op Denon Home 150 Schuur')

    def item(self, marker='A', **overrides):
        return {'uri':'spotify:track:'+marker*22,'name':'Children',
                'artists':[{'name':'Armin van Buuren'}],'album':{'name':'Piano'},**overrides}

    def execute(self, items, *, album='Piano'):
        runtime=types.SimpleNamespace(config={})
        backend=self.backend.SpotifyBackend(object(),runtime)
        calls=[]
        async def request(method,path,**kwargs):
            calls.append((method,path,kwargs))
            if method=='GET':
                return {'tracks':{'items':deepcopy(items)}}
            return {}
        backend._request=request
        parsed={'type':'track','title':'Children','artist':'Armin van Buuren','album':album}
        async def command(hass,runtime,command,value):
            self.assertEqual(command,'play')
            return {'success':True,'selection':await backend.play(value)}
        try:
            with patch.object(self.spotify,'run_music_command',command):
                result=asyncio.run(self.spotify.play_from_intent(object(),runtime,parsed,{}))
        except self.backend.SpotifyBackendError:
            result=None
        return result,calls,runtime

    def test_provider_first_unrelated_ignored_exact_second_recording_dispatched(self):
        bad=self.item('B',name='What If I Told You',album={'name':'What If I Told You'})
        result,calls,runtime=self.execute([bad,self.item()])
        self.assertIsNotNone(result)
        self.assertEqual([call[0] for call in calls],['GET','PUT'])
        params=parse_qs(urlsplit(calls[0][1]).query)
        self.assertEqual(params['q'],['track:"Children" artist:"Armin van Buuren" album:"Piano"'])
        self.assertEqual(params['type'],['track'])
        self.assertEqual(params['limit'],['10'])
        self.assertEqual(calls[1][2]['json'],{'uris':['spotify:track:'+'A'*22]})
        self.assertEqual(runtime.last_resolved_media['title'],'Children')

    def test_every_original_constraint_and_unique_recording_required_before_put(self):
        invalid=[[],[self.item(name='Children - Extended Mix')],
                 [self.item(album={'name':'Piano Deluxe'})],
                 [self.item(artists=[{'name':'Robert Miles'}])],
                 [self.item(is_playable=False)],[self.item(is_local=True)],
                 [self.item(),self.item('B')],[self.item(uri='spotify:album:'+'A'*22)]]
        for items in invalid:
            with self.subTest(items=items):
                result,calls,_=self.execute(items)
                self.assertIsNone(result)
                self.assertEqual([call[0] for call in calls],['GET'])
        result,calls,_=self.execute([self.item()],album='Piano op Unknown speaker')
        self.assertIsNone(result)
        self.assertEqual([call[0] for call in calls],['GET'])

    def test_duplicate_same_recording_and_punctuation_case_normalization_allowed(self):
        item=self.item(name='CHILDREN',artists=[{'name':'Armin van Buuren'}],album={'name':'Piano!'})
        result,calls,_=self.execute([item,deepcopy(item)])
        self.assertIsNotNone(result)
        self.assertEqual([call[0] for call in calls],['GET','PUT'])

    def test_deferred_search_verifies_same_original_constraints_without_write(self):
        runtime=types.SimpleNamespace(config={})
        backend=self.backend.SpotifyBackend(object(),runtime)
        backend._request=AsyncMock(return_value={'tracks':{'items':[
            self.item('B',name='Other'),self.item()]}})
        item=asyncio.run(backend.search_media('Children Armin van Buuren','track',
            constraints={'title':'Children','artist':'Armin van Buuren','album':'Piano'}))
        self.assertEqual(item['uri'],'spotify:track:'+'A'*22)
        self.assertEqual(backend._request.await_args.args[0],'GET')
        backend._request.assert_awaited_once()

    def test_direct_search_intent_also_preserves_literal_album_for_dispatch(self):
        command=AsyncMock(return_value={'success':True})
        with patch.object(self.spotify,'run_music_command',command):
            asyncio.run(self.spotify.play_from_intent(object(),types.SimpleNamespace(),
                {'type':'search','query':'Play Children by Armin van Buuren from the album Piano'},{}))
        self.assertEqual(command.await_args.args[3]['constraints'],
            {'title':'Children','artist':'Armin van Buuren','album':'Piano'})

    def test_malformed_constraints_deny_before_provider_read_or_write(self):
        backend=self.backend.SpotifyBackend(object(),types.SimpleNamespace(config={}))
        for constraints in ({},None,{'title':'Children','artist':'Artist','album':'Piano','extra':'x'},
                            {'title':'Children','artist':'Artist','album':'Piano" OR artist:Other'}):
            with self.subTest(constraints=constraints):
                backend._request=AsyncMock()
                with self.assertRaises(self.backend.SpotifyBackendError):
                    asyncio.run(backend.play({'type':'track','query':'spotify:track:'+'Z'*22,'constraints':constraints}))
                backend._request.assert_not_awaited()


class InlineRecordingOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_backend_stubs()
        cls.output=importlib.import_module('custom_components.djconnect.ask_dj.recording_output')

    def test_known_output_requires_existing_owner_or_existing_single_choice(self):
        text='Speel Children van Armin van Buuren van het album Piano op Denon Home 150 Schuur.'
        device={'id':'actual-inventory-id','name':'Denon Home 150 Schuur'}
        for existing in ('','another-id','actual-inventory-id'):
            with self.subTest(existing=existing):
                turn=types.SimpleNamespace(guard=AsyncMock(),play_output_id=existing)
                inventory=AsyncMock(return_value=[device])
                offer=AsyncMock(return_value={'action':'select_output','retained':True})
                cleaned,response=asyncio.run(self.output.prepare(object(),object(),text,{},object(),
                    inventory=inventory,offer=offer,turn=turn))
                turn.guard.assert_awaited_once()
                if existing==device['id']:
                    self.assertEqual(cleaned,'Speel Children van Armin van Buuren van het album Piano')
                    self.assertIsNone(response)
                    offer.assert_not_awaited()
                else:
                    self.assertEqual(cleaned,text)
                    self.assertEqual(response['action'],'select_output')
                    self.assertEqual(offer.await_args.args[2],'Speel Children van Armin van Buuren van het album Piano')
                    self.assertEqual(offer.await_args.kwargs['devices'],[device])
                self.assertEqual(turn.play_output_id,existing)

    def test_unknown_ambiguous_cached_restricted_output_never_strips_or_offers(self):
        text='Play Children by Armin van Buuren from the album Piano on Speaker'
        device={'id':'one','name':'Speaker'}
        for devices in ([],[{**device,'cached':True}],[{**device,'is_restricted':True}],
                        [device,{**device,'id':'two'}],[{**device,'name':'Other'}]):
            with self.subTest(devices=devices):
                turn=types.SimpleNamespace(guard=AsyncMock(),play_output_id='one')
                offer=AsyncMock()
                result=asyncio.run(self.output.prepare(object(),object(),text,{},object(),
                    inventory=AsyncMock(return_value=devices),offer=offer,turn=turn))
                self.assertEqual(result,(text,None))
                offer.assert_not_awaited()

    def test_withdrawal_during_inventory_allows_no_cleaning_or_offer(self):
        turn=types.SimpleNamespace(guard=AsyncMock(side_effect=RuntimeError('scope withdrawn')),play_output_id='one')
        offer=AsyncMock()
        with self.assertRaises(RuntimeError):
            asyncio.run(self.output.prepare(object(),object(),
                'Play Children by Artist from the album Piano on Speaker',{},object(),
                inventory=AsyncMock(return_value=[{'id':'one','name':'Speaker'}]),offer=offer,turn=turn))
        offer.assert_not_awaited()
