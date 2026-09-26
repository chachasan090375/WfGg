#!/usr/bin/env python3
from __future__ import annotations
import json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
policy=json.load(open(ROOT/'dev-hub/config/voice-gateway.v1.json'))
assert policy['schema']=='chacha.dev/voice-gateway-policy/v1'
assert policy['input']['provider']=='ANDROID_RECOGNIZER_INTENT'
assert policy['input']['auto_submit_transcript'] is True
assert policy['input']['target_channel']=='CONVERSATION'
assert policy['input']['raw_audio_persistence'] is False
assert policy['output']['provider']=='ANDROID_TEXT_TO_SPEECH'
assert policy['output']['speak_assistant_message_only'] is True
assert policy['output']['speak_technical_details'] is False
assert policy['turn_taking']['manual_barge_in'] is True
assert policy['turn_taking']['automatic_vad_barge_in'] is False
privacy=policy['privacy']
for key in ('speaker_biometric_identification','age_inference_from_voice',
            'gender_inference_from_voice','accent_to_origin_inference',
            'emotion_diagnosis_from_voice'):
    assert privacy[key] is False,(key,privacy[key])
auth=policy['authority']
assert auth['decision_authority'] is False
assert auth['execution_authority'] is False
assert auth['mutation_authority'] is False
assert auth['build_channel_auto_switch'] is False
assert policy['automatic_external_spend_eur']==0

java=(ROOT/'android/chacha-direct-operator-widget/app/src/main/java/com/wfgg/chachadev/operator/OperatorActivity.java').read_text()
assert 'TextToSpeech' in java
assert 'UtteranceProgressListener' in java
assert 'addJavascriptInterface(new VoiceBridge(), "ChaChaVoice")' in java
assert 'RecognizerIntent.ACTION_RECOGNIZE_SPEECH' in java
assert 'window.chachaVoiceTranscript' in java
assert 'stopSpeech();' in java
assert 'voiceSessionActive = true' in java
assert 'voiceSessionActive = false;\n                voiceState("TTS_ERROR");' in java
assert 'private static final int SHELL_PROTOCOL_VERSION = 2;' in java
assert 'AudioRecord' not in java
assert 'MediaRecorder' not in java

manifest=(ROOT/'android/chacha-direct-operator-widget/app/src/main/AndroidManifest.xml').read_text()
assert 'android.permission.RECORD_AUDIO' not in manifest

gradle=(ROOT/'android/chacha-direct-operator-widget/app/build.gradle.kts').read_text()
assert 'versionCode = 7' in gradle
assert 'versionName = "0.7.0"' in gradle

shell=json.load(open(ROOT/'dev-hub/config/android-live-shell.v1.json'))
assert shell['shell_protocol_version']==2
assert shell['min_shell_protocol_version']==1
assert shell['voice_gateway']['minimum_native_version_code']==7
assert shell['voice_gateway']['progressive_enhancement'] is True
assert shell['voice_gateway']['old_shell_text_mode_preserved'] is True
ui=(ROOT/'dev-hub/direct-operator-ui/index.html').read_text()
assert "voiceNativeState==='TTS_ERROR'" in ui
assert 'window.chachaStartVoiceSession' in ui
assert 'window.chachaVoiceTranscript' in ui
assert "submit(spoken,true,'CONVERSATION')" in ui
assert 'window.ChaChaVoice.speak(answer,!terminalVoice)' in ui
assert 'window.ChaChaVoice.stop()' in ui
assert "['BUILD_HANDOFF_REQUIRED','AWAITING_APPROVAL','FAILED','BLOCKED']" in ui
assert 'Le mode vocal complet nécessite la mise à jour Android 0.7.0.' in ui
assert '⏹ Vocal' in ui

contracts=json.load(open(ROOT/'dev-hub/config/guardian-role-contracts.v1.json'))['contracts']
c=next(x for x in contracts if x.get('contract_id')=='role:voice-gateway')
for action in ('EXECUTE_PROJECT_MUTATION','AUTO_SWITCH_TO_BUILD','STORE_RAW_AUDIO',
               'INFER_AGE_FROM_VOICE','INFER_GENDER_FROM_VOICE','INFER_ORIGIN_FROM_ACCENT'):
    assert action in c['forbidden_actions'],action
assert 'SPEAK_ASSISTANT_MESSAGE' in c['allowed_actions']
targets=json.load(open(ROOT/'dev-hub/config/assurance-agent-instrumentation.v1.json'))['priority_targets']
assert any(x.get('agent_id')=='voice-gateway' for x in targets)

dual=json.load(open(ROOT/'dev-hub/config/dual-channel.v1.json'))
assert dual['routing']['manual_switch_is_authoritative'] is True
assert dual['routing']['conversation_never_auto_escalates_to_build'] is True

print('CHACHA_DEV_V814_ANDROID_STT=PASS')
print('CHACHA_DEV_V814_ANDROID_TTS=PASS')
print('CHACHA_DEV_V814_TURN_LOOP=PASS')
print('CHACHA_DEV_V814_MANUAL_BARGE_IN=PASS')
print('CHACHA_DEV_V814_RAW_AUDIO_PERSISTENCE=NO')
print('CHACHA_DEV_V814_VOICE_DEMOGRAPHIC_INFERENCE=NO')
print('CHACHA_DEV_V814_CONVERSATION_CHANNEL_ONLY=PASS')
print('CHACHA_DEV_V814_OLD_SHELL_TEXT_COMPATIBILITY=PASS')
print('CHACHA_DEV_V814_GUARDIAN_ROLE_CONTRACT=PASS')
print('CHACHA_DEV_V814_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
