"""Add owner-requested local self-service guidance; never registers backend articles."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'adk-project/knowledge/reviewed'

CASES = [
 ('KB-027', 'WIFI_DISABLED', 'WIFI_FAILURE', 'Wi-Fi switched off',
  'Wi-Fi is turned off and I cannot connect to the office network.',
  'هل مفتاح الواي فاي مغلق؟',
  ['Does the Wi-Fi setting show Off, and are you allowed to enable it here?', 'Can another device connect to the same approved network at this location?'],
  ['The user observes Wi-Fi=Off on their own device.', 'The expected network is an approved saved network and changing the setting is permitted.', 'There is no contradictory shared-service or security evidence.'],
  ['Open the device network settings and turn Wi-Fi on if permitted.', 'Select the known approved saved network. If credentials are needed, use the approved local sign-in flow; never share them in chat.', 'Retry the originally affected service once.'],
  ['Wi-Fi shows connected to the intended approved network.', 'The user explicitly confirms the original connectivity problem is fixed.'],
  ['Wi-Fi is already on or no adapter is present.', 'Peers cannot connect, the control is policy-locked, or the expected approved network is absent.'],
  'https://support.microsoft.com/en-us/windows/experience/connectivity-networking/fix-wi-fi-connection-issues-in-windows'),
 ('KB-028', 'WRONG_PRINTER_SELECTED', 'PRINTER_OFFLINE', 'Wrong printer selected',
  'The print dialog selects the wrong printer or Print to PDF.',
  'هل تم اختيار طابعة غير المقصودة؟',
  ['Which installed printer is selected in the print dialog, and which approved printer did you intend to use?', 'Is the intended printer available and are other users able to print to it?'],
  ['The selected installed printer differs from the intended approved printer.', 'The user can identify and access the intended installed printer.', 'The intended printer is available; shared faults or an actual offline state are not assumed away.'],
  ['Open the print dialog without submitting the original document.', 'Choose the intended installed approved printer; change the default only if the user wants that change.', 'Print a harmless non-sensitive test page to that printer and collect it.'],
  ['The harmless page arrives at the intended printer.', 'The user confirms the original wrong-destination problem is fixed.'],
  ['The intended printer is missing/offline or peers also cannot print.', 'Installing drivers, clearing other users jobs, or changing shared print settings would be required.'],
  'https://support.microsoft.com/en-us/windows/hardware/printer/set-a-default-printer-in-windows'),
 ('KB-029', 'SPEAKERS_MUTED', 'LOCAL_ENDPOINT', 'Speakers muted or volume zero',
  'Speakers are muted or system volume is zero; no sound plays.',
  'هل الصوت مكتوم أو مستوى الصوت صفر؟',
  ['Is the intended connected output device selected, and does its volume show muted or zero?', 'Does the same harmless test sound fail in more than one application?'],
  ['The intended output is present and selected.', 'The user observes mute enabled or volume zero.', 'A missing output, hardware fault or only-one-app problem has not been treated as system mute.'],
  ['Verify the intended connected output device before changing volume.', 'Unmute and set a low comfortable volume.', 'Play a harmless system test sound; raise the volume gradually only as needed.'],
  ['The user hears the test sound at a comfortable level.', 'The original no-sound task works and the user confirms it is fixed.'],
  ['The output device is missing or the volume was already appropriate.', 'Sound remains absent, distorted or intermittent after the change.'],
  'https://support.microsoft.com/en-us/windows/hardware/audio/fix-audio-issues-when-no-sound-plays-from-speakers-or-headphones-in-windows'),
 ('KB-030', 'WRONG_AUDIO_OUTPUT', 'LOCAL_ENDPOINT', 'Wrong audio output device',
  'Sound is routed to the wrong audio output such as a monitor instead of my connected headset.',
  'هل تم توجيه الصوت إلى جهاز إخراج آخر؟',
  ['Which output is selected, and which connected speaker or headset do you intend to hear?', 'Is the intended device present, powered on and unmuted?'],
  ['The selected output differs from the intended known connected output.', 'The intended output is present and available.', 'Muted volume, a disconnected device and hardware faults remain alternatives until checked.'],
  ['Open sound output selection on the user device.', 'Choose the intended connected device and set a low comfortable volume.', 'Play a harmless test sound and retry the original audio task.'],
  ['The test sound comes from the intended output.', 'The user confirms the original audio-routing problem is fixed.'],
  ['The intended device is absent or disconnected.', 'Selection is managed or audio still fails; do not install drivers or reset devices through this guide.'],
  'https://support.microsoft.com/en-us/windows/hardware/audio/fix-audio-issues-when-no-sound-plays-from-speakers-or-headphones-in-windows'),
 ('KB-031', 'WRONG_TEAMS_MICROPHONE', 'LOCAL_ENDPOINT', 'Wrong microphone selected in Teams',
  'Teams uses the wrong microphone even though my intended microphone is connected.',
  'هل اختار Teams ميكروفونًا غير المقصود؟',
  ['Which microphone is selected in Teams, and which connected microphone do you intend to use?', 'Is the intended microphone unmuted and available in the device list?'],
  ['Teams is using a different microphone from the intended connected one.', 'The intended microphone is present and locally permitted.', 'Hardware mute, blocked permissions or an organization restriction have not been silently bypassed.'],
  ['Open Teams device/audio settings outside a live call.', 'Select the intended connected microphone without changing organization-managed permissions.', 'If available, use the built-in Teams test-call feature with a harmless phrase; otherwise use an approved local microphone test. Do not send recordings into this chat.'],
  ['The approved test captures the intended microphone clearly.', 'The user confirms the original microphone-selection problem is fixed.'],
  ['The microphone is absent, policy-blocked or does not work in an approved local test.', 'A test feature is unavailable; do not simulate that it ran or contact other people automatically.'],
  'https://support.microsoft.com/en-us/teams/notifications-settings/manage-your-device-settings-in-microsoft-teams'),
 ('KB-032', 'BROWSER_ZOOM_SETTING', 'LOCAL_ENDPOINT', 'Accidental browser page zoom',
  'The browser page is too large or too small because its zoom setting changed.',
  'هل تغير تكبير الصفحة داخل المتصفح فقط؟',
  ['Is only the webpage affected, and what zoom level does the browser show?', 'Was that zoom level intentional for accessibility or a personal preference?'],
  ['The user observes a changed browser page-zoom setting explaining the display symptom.', 'The user wants to adjust it; accessibility preferences are respected.', 'System display scaling or a broken page layout has not been mistaken for page zoom.'],
  ['Open the browser page-zoom controls for the affected site.', 'Adjust to the user preferred level; use 100 percent only if the user wants it.', 'Check the original page and its controls without changing system-wide display scaling.'],
  ['The page and required controls are readable and usable.', 'The user confirms the original page-display problem is fixed.'],
  ['The problem affects the entire desktop or persists at the desired zoom.', 'A managed setting or accessibility requirement prevents the proposed change.'],
  'https://support.google.com/chrome/answer/96810'),
 ('KB-033', 'KEYBOARD_LAYOUT_SETTING', 'LOCAL_ENDPOINT', 'Wrong keyboard input layout',
  'The keyboard layout is wrong and keys type different characters.',
  'هل تخطيط لوحة المفاتيح أو لغة الإدخال غير المقصودة؟',
  ['Which installed input layout is selected, and which layout matches the keyboard you intend to use?', 'Do the unexpected characters also appear in a harmless local text editor?'],
  ['The selected installed input layout differs from the intended layout.', 'A harmless local typing test is consistent with that mismatch.', 'A damaged key, a one-application shortcut or an unavailable layout remains an alternative.'],
  ['Use the input-language selector to choose the correct already-installed keyboard layout.', 'Type a harmless sample in a local editor; never type or reveal a password for this test.', 'Retry the original non-sensitive typing task.'],
  ['The harmless sample produces the expected characters.', 'The user confirms the original typing problem is fixed.'],
  ['The needed layout is not installed or the selector is managed.', 'Only specific damaged keys fail; do not install language packs or alter display language through this guide.'],
  'https://support.microsoft.com/en-gb/windows/hardware/input-devices/manage-the-language-and-keyboard-input-layout-settings-in-windows'),
 ('KB-034', 'LOW_DISPLAY_BRIGHTNESS', 'LOCAL_ENDPOINT', 'Display brightness set too low',
  'My working screen is unusually dim and the brightness setting is low.',
  'هل الشاشة تعمل لكن السطوع منخفض؟',
  ['Is the display working but dim, and is its available brightness control set low?', 'Is this the built-in display or an external monitor with its own brightness controls?'],
  ['The user can see a working display and observes a low brightness setting.', 'The correct display and a permitted brightness control are identified.', 'A blank display, flicker, physical damage or an intentional accessibility setting is not treated as low brightness.'],
  ['Locate the available brightness control for the affected display.', 'Adjust gradually to the user preferred comfortable level; use the monitor controls if applicable.', 'Check the original task without modifying drivers, HDR or color profiles.'],
  ['The affected display is comfortably visible.', 'The user confirms the original dim-screen problem is fixed.'],
  ['The setting is unavailable or policy-managed, or brightness was already adequate.', 'The screen is blank, flickering, damaged or remains dim.'],
  'https://support.microsoft.com/en-us/windows/hardware/display-graphics/change-display-brightness-and-color-in-windows'),
 ('KB-035', 'DISPLAY_PROJECTION_SETTING', 'LOCAL_ENDPOINT', 'Incorrect multiple-display mode',
  'The second monitor is detected but the wrong display mode is selected.',
  'هل الشاشة الثانية مكتشفة لكن وضع العرض غير مناسب؟',
  ['Are the intended connected displays detected, and do you want Duplicate or Extend?', 'Are these your authorized displays, with no unintended public or shared audience?'],
  ['The intended displays are detected and available.', 'The current projection mode differs from the user intended mode.', 'The user confirms which displays may show the desktop; no unapproved casting destination is selected.'],
  ['Identify the intended connected displays and the desired mode.', 'Select the intended Duplicate or Extend option in display/projection settings.', 'Verify the expected content on both screens and revert the change if it is unsuitable.'],
  ['Both displays show the intended content or extended workspace.', 'The user confirms the original display-mode problem is fixed.'],
  ['The display is not detected or cables/hardware are faulty.', 'The destination is unknown, shared without permission or policy-controlled.'],
  'https://support.microsoft.com/en-us/windows/hardware/display-graphics/how-to-use-multiple-monitors-in-windows'),
 ('KB-036', 'BLUETOOTH_DISABLED', 'LOCAL_ENDPOINT', 'Bluetooth off for a known paired device',
  'Bluetooth is switched off and my already-paired headset will not connect.',
  'هل البلوتوث مغلق والجهاز الشخصي مقترن سابقًا؟',
  ['Is Bluetooth switched off, and is the intended device your known previously paired device?', 'Is that device powered, in range and permitted to connect here?'],
  ['The user observes Bluetooth=Off.', 'The intended owned/authorized device is already paired, powered and in range.', 'A new pairing, unknown device or organization restriction is not being treated as a simple reconnect.'],
  ['Turn Bluetooth on if permitted in this location.', 'Choose the known previously paired device and reconnect; do not remove pairings or accept an unfamiliar device.', 'Test the original device function, such as a harmless headset sound.'],
  ['The known device reports connected and passes the functional test.', 'The user confirms the original connection problem is fixed.'],
  ['Bluetooth was already on, the device is unknown/unpaired or controls are managed.', 'A PIN, driver change, pairing reset or broader hardware troubleshooting would be needed.'],
  'https://support.microsoft.com/en-US/Windows/Hardware/bluetooth/pair-a-bluetooth-device-in-windows'),
 ('KB-037', 'CAMERA_SHUTTER_CLOSED', 'LOCAL_ENDPOINT', 'Camera privacy shutter closed',
  'The camera preview is black because its physical privacy shutter is closed.',
  'هل غطاء خصوصية الكاميرا مغلق؟',
  ['Does the device have a physical camera shutter, and can you see that it is closed?', 'Do you want to use the camera now, in a local preview outside any meeting?'],
  ['The user visually confirms a closed physical shutter on the intended camera.', 'The user wants the camera active for a local preview and controls the device.', 'Blocked permissions, software privacy controls or a hardware fault are not assumed to be the shutter.'],
  ['Ensure no unintended meeting, recording or stream is active.', 'If the user wants to use the camera, have them physically open the shutter; the agent does not control it.', 'Open an approved local preview without recording or sharing it in this chat.'],
  ['The local preview shows the expected image.', 'The user confirms the original shutter-related problem is fixed.'],
  ['There is no shutter or it is already open.', 'The preview remains black, the control is managed or the user does not want the camera enabled.'],
  'https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/camera-privacy-controls'),
 ('KB-038', 'DO_NOT_DISTURB_NOTIFICATIONS', 'LOCAL_ENDPOINT', 'Notifications suppressed by Do Not Disturb',
  'Notification banners are missing while Do Not Disturb is on and notifications reach Notification Center.',
  'هل وضع عدم الإزعاج يمنع ظهور إشعارات البانر؟',
  ['Are the expected notifications present in Notification Center, with Do Not Disturb enabled?', 'Do you want banners enabled now, and is this a user-controlled setting?'],
  ['Expected notifications arrive in Notification Center but banners are suppressed.', 'The user observes Do Not Disturb enabled and wants to change it.', 'App-delivery failure, app-specific settings, intentional focus preferences and organization policy remain distinct.'],
  ['Review the user-controlled Do Not Disturb setting and any automatic focus rule with the user.', 'Disable it only if the user wants banners now; do not override organization policy or change lock-screen privacy.', 'Wait for an expected non-sensitive ordinary notification; do not claim success before one is observed or send messages on the user behalf.'],
  ['An expected ordinary notification banner appears.', 'The user confirms the original notification-display problem is fixed.'],
  ['Notifications never arrive, Do Not Disturb was already off or the setting is policy-managed.', 'The user prefers suppression; no notification arrives to verify the change.'],
  'https://support.microsoft.com/en-us/windows/experience/notifications-and-do-not-disturb-in-windows'),
]

path = DIRECTORY / 'diagnostic_articles.json'
articles = json.loads(path.read_text(encoding='utf-8'))
existing = {a['article_id']: a for a in articles}
register_path = DIRECTORY / 'approval_register.json'
register = json.loads(register_path.read_text(encoding='utf-8'))
approvals = {a['article_id']: a for a in register['article_approvals']}
manifest = []
for identifier, scenario, code, title, symptom, arabic, questions, evidence, steps, success, exclusions, url in CASES:
    article = {'article_id': identifier, 'version': 1, 'approved': True, 'title': title,
        'diagnosis_code': code, 'scenario_code': scenario, 'domain': 'Network' if code == 'WIFI_FAILURE' else 'Endpoints',
        'category': 'Connectivity' if code == 'WIFI_FAILURE' else 'Printing' if code == 'PRINTER_OFFLINE' else 'Device',
        'symptoms_en': [symptom], 'symptoms_ar': [arabic], 'keywords': [title, scenario.replace('_', ' ')],
        'possible_causes': [title, 'A different device, application, hardware or shared-service fault may explain similar symptoms.'],
        'discriminating_questions': questions, 'required_evidence': evidence,
        'safe_checks': ['Ask the user to inspect the named setting and perform only a harmless permitted local test.',
            'No implemented agent tool reads these endpoint settings. Record observations as USER_RESPONSE, never TOOL_CHECK.',
            'Missing, unknown or conflicting observations do not establish this scenario.'],
        'exclusion_criteria': exclusions,
        'competing_diagnoses': ['LOCAL_ENDPOINT', 'WIFI_FAILURE', 'APP_ERROR'] if code != 'LOCAL_ENDPOINT' else ['APP_ERROR', 'LOCAL_ENDPOINT'],
        'resolution_steps': [{'step_id': scenario + '-' + str(i), 'level': 'SELF_SERVICE', 'instruction': text}
            for i, text in enumerate(steps, 1)],
        'success_criteria': success, 'agent_resolvable': False, 'resolution_conditions': [],
        'guided_self_service': True, 'backend_reference': False, 'backend_status': 'LOCAL_ONLY_NOT_REGISTERED',
        'mandatory_human_escalation_conditions': ['Security-sensitive or privileged access, critical priority, shared-service impact, managed/forbidden settings, contradictory evidence or failure of the permitted self-service steps requires human handling.',
            'Do not install drivers, alter security controls, delete data, collect credentials or repeat unsuccessful configuration changes through this guide.'],
        'resolver_group_id': 'GRP-NET' if code == 'WIFI_FAILURE' else 'GRP-END',
        'source_urls': [url], 'approval_scope': 'Owner-requested diagnostic and guided self-service content only; not backend resolution authorization.'}
    if identifier in existing:
        if existing[identifier] != article:
            raise ValueError('Existing article differs; review instead of overwriting ' + identifier)
    else:
        articles.append(article)
    digest = hashlib.sha256(json.dumps(article, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()
    approvals[identifier] = {'article_id': identifier, 'version': 1, 'decision': 'APPROVED',
        'approved_on': '2026-10-25', 'approved_by': 'Project owner / requesting user; requested all proposed scenarios',
        'authorization': 'add all to the agent kb now', 'scope': article['approval_scope'],
        'article_sha256': digest, 'agent_resolvable': False, 'backend_match': 'LOCAL_ONLY_NOT_REGISTERED',
        'deployment_status': 'NOT_DEPLOYED'}
    manifest.append({'article_id': identifier, 'scenario_code': scenario, 'title': title,
        'diagnosis_code': code, 'example_report': symptom, 'source_url': url,
        'backend_registered': False, 'agent_resolvable': False})
assert len(articles) == 38 and len({a['article_id'] for a in articles}) == 38
register.update(approved_article_ids=[a['article_id'] for a in articles],
    article_approvals=[approvals[a['article_id']] for a in articles],
    local_self_service_article_ids=[a['article_id'] for a in manifest],
    note='38 owner-approved diagnostic articles: 24 exact backend mirrors, two earlier local guidance articles, and 12 new local guided-self-service articles. Only KB-001 is a backend-resolution candidate. Policy approval and deployment remain separate.')
path.write_text(json.dumps(articles, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
register_path.write_text(json.dumps(register, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(ROOT / 'docs/self_service_article_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'added': len(manifest), 'total': len(articles), 'ids': [a['article_id'] for a in manifest], 'backend_modified': False}))
