# Music Canvas v1

Canonical owner decision: https://github.com/djconnect-music-dj/djconnect/issues/1101#issuecomment-6894904678
Assignment: DJC-MUSIC-CANVAS-V1-20261115. Implementation status and technical qualification are recorded separately in MUSIC_CANVAS_V1_CONTRACT.md; the following decision is the unchanged product specification, including its original registration-time status.

## OWNER — Music Canvas v1: definitief productontwerp, Core-architectuur, repositorydocumentatie en roadmap

**15 november 2026 · `DJC-MUSIC-CANVAS-V1-20261115`**

**Owning lanes:** Core `pcvantol/djconnect#1101`; Apple `pcvantol/djconnect-app#87`. Dit is de canonieke ontwerp-/opdrachtregistratie voor Music Canvas. Apple krijgt een gekoppelde consumeropdracht; geen parallelle productspecificatie of extra backlog. Geen Cast/VibeCast/API-lane-opdracht afleiden.

### Mandaat en status

Peter: **“Ga nu het definitieve ontwerp op de github lanes klaar zetten … zorg in de core lane dat onderdeel van de opdracht is het ontwerp in de repo en roadmap vast te leggen.”**

Deze registratie zet het overeengekomen ontwerp en de owning opdrachten klaar. **Core moet het ontwerp daadwerkelijk in repositorydocumentatie en de canonieke roadmap verwerken; alleen dit issuecomment opleveren is niet voldoende.** Gebruik de bestaande owning writer, actuele bootstrap/AGENTS, admission, WIP en contracts. Geen tweede writer, herprioritering van lopend werk of impliciete executor-ACK. Implementatie volgt de bestaande lane-pickup-/deliveryprocedure. Dit comment voert geen productimplementatie, hardwareactie, betaalde generatie, release, installatie of deployment uit en autoriseert geen onverwachte nieuwe provider/account/kostenroute.

**Productkeuzes hieronder zijn vastgesteld. Technische beschikbaarheid van apparaatvelden, API's, providerrechten en hardwaregedrag moet de uitvoerende lane nog kwalificeren; presenteer voorstellen niet als reeds werkende capabilities.**

## 1. Propositie en begrenzing

- Naam: **Music Canvas**; de voorlopige naam AmbientView vervalt voor deze functie.
- Payoff: **“Je muziek als kunst op je scherm.”**
- Menu-ingang Apple: **“Muziek als kunst tonen”**.
- Paneeltitel: **“Music Canvas”**.
- Korte beschrijving: **“Artwork, kleur en sfeer die je sessie volgen.”**
- Uitgebreide beschrijving: **“Music Canvas laat originele kunst ontstaan vanuit de muziek die je luistert. Een titel, een verhaal, een beeld of een live-impressie kan de inspiratie vormen. De sfeer van je sessie geeft richting aan de compositie; de artistieke interpretatie blijft vrij.”**

Music Canvas is een **kunstpresentatie van een bestaande DJ-sessie**, geen nieuwe muzieksessie, muziekinterface of uitbreiding van playbackbevoegdheden. Het beeld mag met de muziek veranderen maar mag niet ogen alsof een app aan de muur hangt.

**VibeScape blijft de bestaande live visuele animatie op het eigen apparaat. VibeCast blijft de aparte scherm-/sessie-ervaring.** Geen hernoeming, vervangen of wijzigen van die functies. Eventueel hergebruik van generieke visuele bouwstenen alleen zonder runtime-/UX-koppeling en zonder een VibeScape-screenshot als kunstproduct.

**V1-uitvoer heeft exact twee adapterfamilies:**
1. zelfstandige lokale **Samsung Art Mode-adapter binnen DJConnect Core**;
2. **SwitchBot AI Art Frame via de native, reeds ingestelde HA SwitchBot Cloud-uploadactie**.

Google Cast/browserreceiver is géén Music Canvas-route in v1. Lokale SwitchBot-reverse-engineering, eigen Base64-cloudroute en firmwaremodificatie zijn eveneens buiten scope.

## 2. Definitieve artistieke regie: vrije interpretatie, geen metadata-interface

Music Canvas mag alle bruikbare, toegestane context bij de huidige muziek als inspiratie combineren: titel, artiest, album, historische/productiecontext, geschikte artwork-/artiestenfoto's, livebeelden en passende tekstuele bronnen. Het hoeft niet alle gevonden informatie te gebruiken of herkenbaar af te beelden. De artistieke regie kiest één samenhangende richting: onderwerp/associatie, materiaal, abstractieniveau, palet en compositie.

**Een titel alleen is een volwaardige bron, geen fout of inferieure fallback.** Voorbeeld van de eigenaar: *Born Slippy* mag puur vanuit die twee woorden een volledig vrije interpretatie opleveren: ontstaan, onvaste vormen, verschuiven, vloeibaarheid. Dat is artistieke associatie, geen feitelijke verklaring van het echte nummer. De woorden zelf worden niet als titel/typografie op het kunstbeeld geschreven.

Contextverzameling is begrensd in tijd/werk/kosten. Ontbrekende foto's, lyrics of achtergrondinformatie mogen de generatieve functie niet blokkeren wanneer geschikte titel/context beschikbaar is. Niet iedere generatie moet per se opnieuw alle bronnen doorzoeken; hergebruik toegestane bestaande kennis via de bestaande Core-owners.

**Beoogde esthetiek:** matte pigmenten, subtiele textuur, bewuste negatieve ruimte, materiaalgevoel, compositorische samenhang; alsof je in een museum naar kunst kijkt. Abstract of herkenbaar, ingetogen of expressief mag. Geen neon-/disco-esthetiek als standaard, geen glanzende digitale widgets. Een beeldgenererend model maakt het beeld; een tekst-LLM kan de artistieke regie/prompt verzorgen. Afbeeldingsgeneratie blijft server-side aangestuurd; geen generatie op de Apple-client.

**Absoluut geen toegevoegde UI in het uitvoerbeeld:** klok, playbackcontrols, voortgang, track-/artiestlabel, glass cards, DJ-tekst, logo/watermark van DJConnect, badge, foutmelding, laadspinner, bronpaneel of verbindingsstatus. Er is géén instelling ‘Trackinformatie tonen’. Bediening, preview, bronnen en technische feedback horen uitsluitend in de app. Onvermijdelijke systeemeffecten van een fysiek apparaat niet verwarren met eigen beeldlagen.

### Bronnen en herkomst

Gebruik bestaande research-/Knowledge-bouwstenen, MusicBrainz, Wikidata/Wikimedia en gerichte websearch waar passend. MusicBrainz-kernmetadata en Cover Art Archive-beelden zijn niet dezelfde rechtenbron. ‘Op internet gevonden’ of ‘privégebruik’ is geen automatisch AI-/bewerkingsrecht. Bron-/licentie-/providerbeleid wordt vóór modelinvoer toegepast; leg herkomst en gebruikte bewerkingen compact vast. Externe broninhoud is onbetrouwbare data, geen uitvoeropdracht.

Geen automatische Spotify-image→vision-caption→image-modelketen als omweg. Spotify-artwork of afgeleide input niet als generiek toegestane AI-invoer aannemen. Lyrics, referentiebeelden en andere inhoud alleen verwerken wanneer bronvoorwaarden, rechten en modelprovidergebruik dat toelaten. Geen rechten-/bronlabel als digitale opsmuk in het kunstwerk drukken om een ongeschikte bron toch te gebruiken: kies een andere geschikte bron of titel/context-only. Tekstuele metadata is ook bronbewust; neem geen ongedocumenteerde provideruitzondering aan. Als een bron ontbreekt/afvalt, blijft artistieke vrijheid bestaan.

Dit is geen verplicht plakboek of vaste albumhoes-op-achtergrondpipeline. De eerdere voorstellen ‘alleen track-art als bron’ en ‘altijd originele vierkante hoes als layer’ zijn vervangen.

## 3. Rol van mood, seizoen, compositie en passe-partout

**Mood stuurt het visuele ritme**, waaronder dichtheid, ademruimte, ordening, gelaagdheid, asymmetrie en spanning. Niet alleen een druktegetal: rustig versus gefocust kan een andere ordening geven. Mood verandert de bestaande Session mood niet en dicteert geen palet, beeldhelderheid, animatie- of wisselsnelheid. Gebruik de bevestigde bestaande Session mood; geen tweede Canvas-mood of nieuwe moodtaxonomie.

**Kleurpalet** komt uit geschikte visuele referenties of de gekozen artistieke richting. Geen verplichte overname van app-/Session-moodkleuren. Geen extra kleurkiezer/moodkleurentoggle.

**Seizoen** mag subtiel licht, materiaal en sfeer inspireren; niet verplicht sneeuw/bladeren of een vast seizoenspalet. Gebruik datum en de reeds beschikbare HA-locatie voor het juiste halfrond indien voldoende betrouwbaar; geen nieuwe precieze locatievraag. Bij onvoldoende context seizoen weglaten in plaats van gokken. **Geen actueel weer, temperatuur of weerintegratie**, geen seizoentoggle. Alleen bij reguliere nieuwe generatie meewegen; een seizoensgrens triggert niet zelfstandig een nieuw beeld.

**Compositie:** `Centraal · Vrij · Beeldvullend`. Dit zijn ruimtelijke richtingen, geen rustige/gemiddelde/intense varianten. Bij vrije generatieve kunst slaat Centraal op het focuspunt/kunstvlak, niet op een verplichte albumhoes. Native beeldverhouding behouden; geen vierkante bron ongedocumenteerd uitrekken tot 16:9.

**Passe-partout:** één driewegkeuze `Uit · Passend · Contrasterend`. Passend = rustige tint passend bij compositie/palet; Contrasterend = bewust contrasterende neutrale rand, bijvoorbeeld zwart. Per scherm is bij Passend of Contrasterend de dikte instelbaar op Smal, Gemiddeld of Breed. Gemiddeld behoudt de bestaande standaarddikte. De keuze wordt bewaard als het passe-partout uit staat. Passe-partout rondom het werk, niet als crop/overlay over inhoud. Generieke compositor levert dit; native adaptermatte alleen indien equivalent en zonder dubbele rand.

**Geen intensiteits-/dynamiekslider en geen extra artworkgrootte-slider in Music Canvas v1.** Bestaande lokale VibeScape-bediening blijft ongemoeid. Presentatie aanpassen mag niet onnodig een nieuwe modelgeneratie starten; passe-partout is waar mogelijk deterministische heropmaak.

## 4. Persistent profiel en automatische lifecycle

**Instellingen zijn HA Core Profile-owned, geen sessie- of clientlokale defaults.** Bewaar duurzaam:
- enabled;
- geselecteerde stabiele device-ID's (meerdere tegelijk);
- compositie;
- passe-partout;
- gezamenlijke wisselfrequentie en expliciete afwijkingen per device.

Een wijziging vanuit de sessiewerkbalk geldt voor de huidige én volgende sessies van hetzelfde profiel. Geen ‘bewaar als standaard’-stap. Geen dubbele preference authority in Swift/local storage. Hergebruik bestaande Profile-/Session-settingsauthority met revisies, validatie, geautoriseerde writes, migratie en teruggelezen acceptatie.

**Pairing/tokens/capabilities zijn apparaat-/installatie-owned in Core**, niet in het profiel of op de telefoon. Profielen verwijzen naar gekoppelde toegestane devices. Profielwissel is geen re-pair; machtigingen blijven wel gerespecteerd.

- Eerste keer selecteren/koppelen/instellen; eenmaal aan = automatisch meedoen aan volgende DJ-sessies totdat expliciet uitgezet.
- Nieuwe sessie: direct activeren voor geselecteerde geschikte schermen en het eerste werk voorbereiden zodra de eerste track stabiel speelt. Niet eerst 15/30/60 minuten wachten. Tot nieuwe muziek bekend is status ‘Wacht op muziek’, geen verzonnen track.
- Werkelijke Session-einde: stoppen met nieuw onderzoek/generatie/aflevering; enabled en instellingen blijven behouden. Laat laatste werk in beginsel staan; geen ongevraagd uitschakelen van tv/frame.
- App afsluiten/vergrendelen is géén sessie-einde. Core werkt zelfstandig door.
- Expliciet Music Canvas uit: duurzaam disabled voor huidige en toekomstige sessies; stop eigen werk, niet de muziek. Toepassen van profielvoorkeur mag geen nieuwe muzieksessie starten.
- HA-herstart: herstel voorkeuren, pairings en uitvoer aan de hand van de werkelijk actieve/herstelde Session. Geen oude batch inhalen, geen gefingeerde actieve sessie.
- Profile/Session-switch, stoppen, rechtenintrekking en vergeten fencen late callbacks op hun oorspronkelijke context. Geen retarget naar een nieuwe sessie of gebruiker.

Enabled is een **voorkeur**, niet bewijs van weergave. Scheid desired state, actuele fase en observed per-device resultaat. Handmatige tv-bediening en daadwerkelijk tv-kijken gaan voor; enabled mag geen blijvende strijd om het scherm veroorzaken. Stoppen/uit mag geen toepassing beëindigen die de gebruiker intussen zelf heeft gestart. Maak handover/resume-/wakebeleid expliciet in het contract; geen impliciete extra wake-toggle invoeren.

## 5. Wisselfrequentie: clientbediening, Core-scheduler

Keuzes exact: **`Ieder nummer · Ieder kwartier · Ieder half uur · Ieder uur`**. Startwaarde: ieder half uur. Eén gezamenlijke instelling; per geselecteerd scherm kan een expliciete afwijking gelden, zonder alle schermen verplicht apart te configureren.

- Ieder nummer: confirmed/stable trackwissel, kort debounce tegen snel skippen; coalesce naar nieuwste relevante track. Geen generatie voor iedere voorbijgaande skip.
- Tijdsinterval: pas op de beurt context/generatie starten voor de dan spelende muziek. Niet toch per track genereren en afbeeldingen onzichtbaar weggooien.
- Bij activering/nieuwe sessie geldt de directe eerste generatie, daarna de cadence. Bij pauze/geen actieve muziek geen periodieke nieuwe werken; hervatten zonder achterstallige wissels inhalen.
- Mood bepaalt nooit cadence. Zelfde frame kan langer blijven terwijl tracks wisselen: dat is expliciet doelgedrag bij intervalkeuze.
- Bevries context/track bij de gekozen renderopdracht. In per-trackmodus mag inmiddels achterhaalde track niet alsnog verschijnen; intervalmodus mag zijn gekozen moment interpreteren zonder iedere volgende track als nieuwe opdracht te behandelen. Session-/profiel-/settings-/device-epochwijzigingen hebben altijd de afgesproken geldigheidscontrole.
- Geen onbegrensde wachtrij; per device maximaal lopend werk plus nieuwste relevante intent. E-paper/cloudlatentie respecteren; gemiste termijnen niet inhalen.
- Werkende tv's niet laten wachten op een traag/offline frame. Technische uitvoertijd is geen garantie op seconde-exact synchroon beeld.

## 6. Meerdere schermen en apparaatprofielen

Gelijktijdige selectie en uitvoer zijn essentieel, o.a. twee Samsung Frames plus een SwitchBot AI Art Frame. Gezamenlijke artistieke intent kan worden gedeeld wanneer wisselmoment/context overeenkomen; uiteindelijke compositie en aflevering passen bij ieder scherm. Gelijkwaardige doelprofielen mogen artifactbytes delen; niet automatisch N dure generaties voor N identieke schermen.

**Screen profile** omvat bekende fysieke maat, native pixelresolutie, aspect ratio, feitelijke oriëntatie, bruikbare imageformats/gamut en uitvoercapabilities. Volgorde: betrouwbaar uitgelezen apparaat-/HA-capability → geverifieerd vast modelprofiel → alleen ontbrekende niet-afleidbare gegevens eenmalig vragen. IP-adres, modelmaat of discovery alléén bewijst geen ophangoriëntatie. Nooit doen alsof ieder apparaat alle velden exposeert.

De SwitchBot van de eigenaar hangt portrait; ondersteun dit echt als native compositie, niet als gecropte 16:9-tv-export. Wanneer oriëntatie niet uitleesbaar is, eenmalig bij setup vragen en in het apparaatprofiel bewaren. Wanneer wel uitleesbaar: geen overbodige toggle. Dit principe geldt ook voor Samsung. 4K bij een gekwalificeerd 4K-doel, niet ‘altijd 4K’ voor ieder frame; alleen vergroten levert geen echt detail.

Leg eigenaarschap/arbitrage vast wanneer meerdere actieve profielen hetzelfde fysieke scherm willen aansturen. Geen twee ongecoördineerde writers of stil last-client-wins. Bouw op bestaande Core-auth/ownership waar passend, zonder nieuwe muziek-/Session-owner.

## 7. Architectuurgrenzen

`confirmed Session context → passende bronnen → artistieke intent → server-side image generation → target-aware compositie/passe-partout → delivery adapter → observed status`

Core owns research/orchestration, profielinstellingen, scheduling, gedeelde art-intent, generation/asset lifecycle, device registry en authorization. Adapters own transport, pairing/protocol, capability probing, feitelijke afleverstatus en device-opruiming. Geen Samsung-content-ID, SwitchBot-uploadparameter of HA-servicenaam in de generieke kunstspecificatie.

Zware generatie/compositie buiten de HA-eventloop via passende bestaande async/workerpatronen. Hergebruik huidige providers/credentials/budgets en bekende research-/imagebouwstenen. Nieuwe vereiste imageprovider of externe uitvoering expliciet als integration gap/afhankelijkheid vastleggen; niet heimelijk een extra infrastructuurrepo/service of nieuwe kostenroute maken. Een worker is een technische grens, niet verplicht een apart product dat de gebruiker moet installeren.

Apple owns compacte native bediening/preview; geen eigen scheduler, LLM, discoveryscanner, tv-tokenopslag, SwitchBot-cloudcredentials of fabrikantprotocol. Appsluiten mag uitvoer niet onderbreken. Alleen capability-/versiegebonden Core-contracten gebruiken, niet gegokte endpointnamen.

Op externe schermen staat het laatste goede werk tijdens wachten/renderen/fouten. Geen foutbeeld/lege canvas als normale fallback. Eerste generatie zonder vorig beeld laat bestaande apparaatpresentatie intact totdat een geschikt werk klaar is.

## 8. Samsung-adapter: zelfstandig geïntegreerd in DJConnect

Geen vooraf geïnstalleerde officiële Samsung- of custom HACS-integratie vereisen. Gebruik HA gedeelde netwerkdiscovery (o.a. SSDP) en waar aanwezig HA-devicegegevens; dedupe op stabiele identiteit, niet op alleen IP. Geen parallelle generieke LAN-scanner. Discovery = kandidaat, niet toestemming of uploadgeschiktheid.

Start lokale autorisatie alleen na bewuste keuze door gebruiker. Ondersteun toestemmingsmelding op tv en eigen per-device tokens in Core; niet tokens uit de interne opslag van een andere integratie stelen of op Apple bewaren. Onafhankelijk geïnitialiseerde HA-Samsung-integratie blijft ongemoeid.

Hergebruik een geschikte onderhoudbare protocolbibliotheek (onderzoek o.a. samsungtvws) na bron-, versie-, licentie- en modelkwalificatie. Geen volledige fork/kopie van TheFab21 HACS-media_player. Gerichte protocolverbetering/adaptershim kan; houd notices en onderhoudsgrens expliciet.

Minimaal: ontdek/koppel/probe profiel; upload; selecteer kunst; lees daadwerkelijke Art Mode-/contentstatus waar ondersteund; detecteer handmatige takeover; beheer uitsluitend eigen geüploade content-ID's; forget/revoke voor zover protocol dit ondersteunt. Ontdekt/gepaird/onbereikbaar/unsupported/ready zijn afzonderlijke toestanden.

Uploaden en selecteren bewust scheiden. Onderzoek ook of upload zelf kan wekken; ‘show=false’ of alleen een guard bij selecteren mag geen valse no-wakegarantie geven. Geen HDMI-/audio-/volume-/speakerwijzigingen. Kwalificeer echte modellen/firmwares en librarygedrag; simulatie bewijst geen 2025/2026-hardwarecompatibiliteit.

## 9. SwitchBot-adapter v1: bestaande HA-cloudkoppeling

Alleen apparaten aanbieden uit de door de gebruiker **al ingestelde relevante SwitchBot Cloud-integratie**, met benodigde native uploadactie/capability. Bluetooth-only discovery is geen bewijs van deze route. Geen SwitchBot-accountlogin, BLE-upload, reverse-engineering, eigen cloudprotocol of automatische installatie van de integratie vanuit Music Canvas.

Gebruik de daadwerkelijk aanwezige `switchbot_cloud.upload_art_frame_image`-actie en het schema van de gebruikte HA-versie; verifieer bij pickup de exacte parameters/identitymapping. Core selecteert bestaande registry-apparaten, Apple krijgt generieke doelen.

Een HA-beheerder kan per geregistreerde fotolijst automatisch ruimte vrijmaken inschakelen. Standaard blijft dit uit. Alleen met deze instelling gebruikt Core de officiële SwitchBot OpenAPI met de signer van de reeds geladen HA-cloudkoppeling. De normale HA-uploadactie geeft geen bruikbare albumlimiet terug. Core bewaart geen SwitchBot-inloggegevens en stuurt de ondertekening uitsluitend naar de officiële SwitchBot-host. Alleen een expliciete albumlimietfout 7301 leidt tot een statuscontrole. Als SwitchBot een statisch getoonde afbeelding bevestigt, mag Core één keer de oudste niet-getoonde afbeelding permanent verwijderen. Dat kan een eigen foto zijn. Na een bevestigde verwijdering volgt één uploadpoging, zonder tweede verwijdering. Een onbekende fout of een diavoorstelling leidt niet tot verwijdering. Vergeten blijft een afzonderlijke actie.

Native cloudupload kan een vanaf SwitchBot bereikbare afbeeldings-URL nodig hebben. Gebruik een beperkte, tijdelijke HTTPS-assettoegang via een geschikte bestaande/expliciet ingerichte voorziening; alleen het bedoelde bestand, beperkte geldigheid, geen HA-token in URL/logs, geen algemene openbare `/www`-kunstcollectie, geen veronderstelde LAN-URL/cloudbereikbaarheid. Als geen geschikte route bestaat: expliciete setupblokkade, niet heimelijk een publiek endpoint of proxy aanmaken. Geen alternatieve Base64-route in deze v1.

Een geaccepteerde HA-actie/cloudrequest bewijst niet dat het fysieke scherm klaar is. Maak ‘aangeleverd/observed onbekend’ eerlijk zichtbaar in de app waar display-ACK ontbreekt. Respecteer e-paper latency, kleurprofiel en zichtbare refresh; geen snelle animatie-/uploadlus. Test volle frameopslag/herhaald afleveren; lokale cache-opruiming is geen device-opruiming. Bied verwijderen van remote eigen kunst alleen aan wanneer de native route dit aantoonbaar kan.

## 10. Alleen functioneel noodzakelijke opslag

**De eerdere vaste rolling cache van 30 beelden per device is expliciet vervallen. Geen v1-galerij/geschiedenis.**

Bewaar normaliter het actuele succesvolle renderresultaat per device voor preview/herstel en het nieuwe in-flight resultaat zolang nodig voor aflevering/beperkte retry. Tijdelijke bronnen en tussenproducten zo snel mogelijk opruimen; TTL/bounds volgen bronprivacy en technisch nut. Compacte provenance/ownershipmapping mag blijven zolang nodig om eigen remote uploads veilig te beheren.

Deel identieke artifacts met refcounts; opruimen op één device mag een lopende aflevering aan een ander niet breken. SwitchBot-URL niet meteen na service-call verwijderen: ontvangst/expiry en beperkte retrytermijn bepalen de lease. Geen onbeperkte bewaring als displaybevestiging ontbreekt. Revoke URLs bij vergeten/rechtenintrekking waar technisch mogelijk; wees eerlijk dat reeds opgehaalde cloudbytes niet worden teruggehaald.

## 11. ‘Vergeet apparaat’: blijvende Core-beheeractie

Apple: `Music Canvas → Schermen → [apparaat] → Vergeet apparaat`.

Bevestiging noemt doel, impact en eventueel andere profielen. Gewone deselectie = dit profiel gebruikt scherm niet; vergeten = gedeelde apparaatkoppeling verwijderen met passende beheerbevoegdheid.

Optioneel, **standaard uit en alleen indien ondersteund**:
**‘Verwijder ook de door Music Canvas opgeslagen kunstwerken op dit scherm’.** Geen claim dat native SwitchBot-opruiming bestaat. Nooit persoonlijke foto's, Art Store-werken of uploads van andere apps verwijderen. Identificeer eigen content via echte geregistreerde ownership, niet op een naam-/MY-prefix alleen.

Veilige volgorde:
1. Stop/fence uitvoer, nieuwe jobs/retries/scheduler en in-flight callbacks voor de device-epoch; markeer forgetting, zodat automatische resume niets terugplaatst.
2. Eventueel gevraagde eigen remote kunst opruimen zolang benodigde pairing nog bestaat.
3. Verwijder DJConnect-pairinggeheimen, apparaatregistratie/-instellingen en verwijzingen uit betrokken profielselecties. Ruim lokale/private previews/artifacts/URL-leases op, behoud alleen nog door andere actieve apparaten benodigde gedeelde bytes.
4. Readback naar clients; andere schermen/Music Canvas-profielvoorkeuren blijven intact.

Offline/failed delete: gebruiker krijgt eerlijk ‘kunst kan achterblijven’ en kan alsnog vergeten. Geen eindeloze deferred delete met heimelijk bewaarde tokens; geen succes claimen op remote wipe zonder bewijs. Een extern reeds ingediende niet-annuleerbare cloudjob kan nog effect hebben: documenteer/test die grens en claim niet dat tokenwissen iedere eerder verzonden opdracht ongedaan maakt.

Samsung: alleen eigen lokale koppeling; waar mogelijk device-side autorisatie intrekken, anders onderscheid lokale tokenverwijdering en achterblijvende tv-autorisatie. SwitchBot: verwijder alleen Music Canvas-registratie, nooit de gedeelde HA-integratie/accountcredentials/device. Rediscovery mag apparaat beschikbaar tonen maar nooit automatisch opnieuw selecteren, pairen of gebruiken; expliciet opnieuw toevoegen vereist.

## 12. Core↔Apple contractdeliverable

Inventariseer huidige Profile/Session/device/operation-contracten en publiceer een versiegebonden Music Canvas-capability en minimale producer-consumerdelta; geen endpoint als bestaand presenteren voordat geïmplementeerd/gekwalificeerd.

Contract dekt ten minste:
- authoritative prefs/revision en wijzigingsacceptatie (enabled, selected targets, composition, matte, cadence/overrides);
- device descriptor/stabiele ID, pairing-/discoverystatus, supported adapter/capabilities, known/unknown profielvelden met provenance;
- connect/setup/cancel, select/deselect, authorized forget met optionele eigen-remote-cleanup en effectscope;
- desired state versus runtime/observed per-device status en veilige preview/source metadata;
- operation IDs, retries/statusreadback, scope/epoch fences, expiry/ownership, error taxonomy en capabilityversion;
- lifecycle Session start/end/pause, appclose, Core restart, profile switch en handmatige tv-takeover.

Gebruik geautoriseerde bestaande routes en transportpolicy; geen nieuwe client-LLM of zelfstandig firmwarecredentialkanaal. Preview en source-info zijn geen publiek schermproduct. Geen nieuwe Listen/Ask DJ-spraak- of voicecommandimplementatie uit voorbeeldzinnen afleiden.

## 13. VERPLICHT: ontwerp in repo én bestaande roadmap vastleggen

De Core-opdracht is niet klaar met comments. Lever als eerste documentary/contractslice via de bestaande writer:

1. **`docs/product/MUSIC_CANVAS_V1.md`** als canoniek productontwerp, of één aantoonbaar equivalent bestaand canoniek document uitbreiden en exact terugmelden. Neem alle vastgestelde UX, artistieke vrijheid, uitsluitingen, lifecycle, adapters, opslag, beheer, failure cases en superseded-keuzes uit dit comment op.
2. Technische architectuur/contractdelta in passende bestaande contractdocumentatie; waar nodig een companion, bijv. **`docs/technical/MUSIC_CANVAS_V1_CONTRACT.md`**. Pad is voorgesteld, geen claim dat het bestaat. Inventariseer werkelijke Core-/Apple-componenten, discovery, providers, Profile/Session-owners en worker-/operationpatronen met REUSE/ADAPT/NEW/RETIRE. Geen fictieve endpoints, fields of bewezen hardwarecaps.
3. Werk bestaande documentatie-index/architectuurverwijzingen en owning productbacklog bij; voorkom een tweede huidige productspecificatie. Relatie en duidelijke scheiding t.o.v. VibeScape/VibeCast vastleggen.
4. **Werk de canonieke `docs/roadmap/v1/djconnect-platform-v1.json` bij** via de bestaande maintenanceprocedure. Nieuwe feature/node(s) waar werkelijk nodig, bestaande IDs/autoriteit hergebruiken. Genereer lane-, dependency-, handoff-, open-work- en relevante diagramprojecties opnieuw; niet uitsluitend gegenereerde Markdown editten. Behoud historische snapshots en bestaande deliveryevidence.
5. Splits/documenteer afhankelijkheden: product-/contractdocumentatie → Core profiel/lifecycle/research/render/assetproducer + twee adapters → Apple-consumer → joint/native/hardwareacceptatie. Parallel voorbereidende UI-/adapterwerkzaamheden kunnen alleen met heldere contract-/writergrenzen; geen fictieve serieblokkade voor onafhankelijke adapters, geen volledige acceptatie door Core-unitfixtures alleen.
6. Geef Apple #87 vroeg een versiegebonden contract/handoff met fixtures, fout-/capabilitymatrix en exacte doc-/PRlinks. Vraag gerichte ontbrekende consumerfeedback. Geen werk of nieuwe opdracht in VibeCast/API/release-lanes door scope creep.
7. Draai actuele roadmapvalidator/rendercheck en relevante tests volgens repositorypolicy; bestaande README noemt o.a. `validate_snapshot.py ... --check-rendered` en snapshot/maintenance-tests — verifieer actuele invocation bij pickup. Onafhankelijke review, noodzakelijke fixes, protected delivery, exact-main readback en verplichte Finalization volgens bestaande lane-governance; geen bypass.
8. Rapporteer afzonderlijk: ontwerp vastgelegd, roadmap bijgewerkt, contract geleverd, code geïmplementeerd, software getest, native/hardware geaccepteerd, release/deployment. Registratie/draft/source-merge is nooit bewijs van alle volgende fasen.

## 14. Acceptatiematrix voor latere implementatie

| Gebied | Verplicht bewijs |
|---|---|
| Naam/scope | Music Canvas exact; VibeScape/VibeCast ongewijzigd; geen Cast-route. |
| Artistieke kern | Rijke geschikte referenties én titel-only zoals Born Slippy leveren geldige originele kunst; geen fictieve muziekfeiten; geen verplichte albumhoes. |
| Visueel | Geen extra tekst/controls/logo/glass/klok/statuslagen; matte museumachtige resultaten; mood verandert ritme, niet vaste appkleuren; seizoen optioneel, geen weer. |
| Presentatie | Alle drie composities en alle drie passe-partouts; deterministische heropmaak waar mogelijk; landscape/portrait en passende native kwaliteit. |
| Persistente UX | Enable + schermen + instellingen overleven sessie-einde, nieuwe sessie, appclose en Core-restart. Geen opnieuw pairen/kiezen. Profilewissel en multi-clientconflict veilig. |
| Cadence | Alle vier intervallen; eerste werk direct; debounce/skip; pauze/einde; geen per-trackgeneratie bij interval; geen catchupstorm of late stale aflevering. |
| Multi-device | Minimaal twee Samsungs plus portrait-frame; onafhankelijke voortgang/fouten; gedeelde assets niet voortijdig verwijderd; meerdere profielen vechten niet om scherm. |
| Samsung | Ontdekken zonder HACS, expliciete pairing, supported/unsupported/unknown, IP-wijziging, autorisatie vervallen, upload/select/readback, no-takeover/no-onbedoeld-wake en uitsluitend eigen cleanup op echte compatibele hardware. |
| SwitchBot | Alleen met ingestelde passende HA-cloudintegratie; echte native actie; cloudbereikbare tijdelijke URL; latency/offline/storage-full; geen aangenomen delete/displayACK/local route. |
| Settings auto | Bekende apparaatdata vragen geen toggles; onbekende orientation alleen eenmalig; model ≠ feitelijke ophanging. |
| Privacy/opslag | Bronbeleid en prompt-injectiongrens, beperkte providercalls, bounded leases/storage, geen 30-archief, scopes/tokens niet lekken. |
| Forget | Online/offline, met/zonder remote cleanup, ontbrekende capability, gedeeld profielgebruik, lopende generatie/overdracht, partial failure, rediscovery; geen andere foto's/accounts/integraties verwijderd. |
| E2E | Apple→Core→Samsung en Apple→Core→SwitchBot afzonderlijk bewezen; cloudaccepted ≠ displayed; previews/status eerlijk. |

## 15. Expliciet vervallen voorstellen / niet terugbrengen

AmbientView als productnaam; Google Cast-route; afhankelijkheid van Samsung HACS; local SwitchBot v1; track-art als enige bron; verplichte ingeplakte Spotify-hoes; image-to-text als rechtenomweg; vaste moodkleurpaletten; weerinput; dynamics-/intensiteit-/artworkgrootte-slider; trackinfo-toggle; klok/controls/glass in het kunstwerk; passe-partout smal/breed; verplicht 30-beeldenarchief; slechts één scherm; app-owned timer/defaults; enabled resetten bij sessie-einde; opnieuw pairen bij iedere sessie; onbekende hardwarevelden als automatisch beschikbaar presenteren.

### Pickup-instructie

`DJC-CORE` vervolgt via bestaande owning lane/bronwriter na verse admission, zonder huidige WIP te overschrijven. Begin met actuele broninventaris en de verplichte **repositoryontwerp + roadmap/contractslice**, geef Apple de handoff, en zet de afgebakende implementatie/acceptatieslices in de bestaande roadmap. ACK, actuele base/branch, werkelijke paden, eerste documentaire oplevering en resterende technische verificatie terugmelden in dit register. Geen nieuwe writer/release/installatie/hardwareactie veronderstellen uit dit comment.

**Status bij registratie: DEFINITIEF PRODUCTONTWERP KLAARGEZET; REPO-DOCUMENTATIE/ROADMAP-DELTA NOG TE LEVEREN DOOR CORE; EXECUTOR-ACK/IMPLEMENTATIE/DEPLOYMENT NIET GECLAIMD.**
