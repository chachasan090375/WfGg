package com.wfgg.chachadev.operator;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.RecognizerIntent;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import javax.net.ssl.HttpsURLConnection;

public class OperatorActivity extends Activity {
    private static final int VOICE_REQUEST = 42;
    private static final int SHELL_PROTOCOL_VERSION = 2;

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());

    private WebView webView;
    private String baseUrl;
    private Uri allowedOrigin;
    private boolean pageReady = false;
    private String pendingMode = ChaChaWidgetProvider.MODE_TYPE;
    private TextToSpeech textToSpeech;
    private volatile boolean textToSpeechReady = false;
    private volatile boolean voiceSessionActive = false;
    private volatile boolean voiceRequestInFlight = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        baseUrl = getString(R.string.operator_base_url);
        allowedOrigin = Uri.parse(baseUrl);
        pendingMode = modeFrom(getIntent());

        webView = new WebView(this);
        setContentView(webView);
        configureWebView();
        initVoiceGateway();
        loadRemoteUi();
    }

    private void configureWebView() {
        WebView.setWebContentsDebuggingEnabled(false);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setGeolocationEnabled(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, false);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                if ("chacha".equalsIgnoreCase(u.getScheme()) && "retry".equalsIgnoreCase(u.getHost())) {
                    loadRemoteUi();
                    return true;
                }
                return !isAllowed(u);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (isAllowed(Uri.parse(url))) {
                    pageReady = true;
                    handlePendingMode();
                    ChaChaWidgetProvider.refreshRemote(OperatorActivity.this);
                }
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, android.webkit.WebResourceError error) {
                if (request.isForMainFrame()) showFallback();
            }
        });
    }

    private void initVoiceGateway() {
        webView.addJavascriptInterface(new VoiceBridge(), "ChaChaVoice");
        textToSpeech = new TextToSpeech(this, status -> {
            textToSpeechReady = status == TextToSpeech.SUCCESS;
            if (textToSpeechReady && textToSpeech != null) {
                textToSpeech.setLanguage(Locale.getDefault());
            }
            voiceState(textToSpeechReady ? "READY" : "TTS_UNAVAILABLE");
        });
        textToSpeech.setOnUtteranceProgressListener(new UtteranceProgressListener() {
            @Override public void onStart(String utteranceId) { voiceState("SPEAKING"); }
            @Override public void onDone(String utteranceId) {
                main.post(() -> {
                    voiceState("READY");
                    if (voiceSessionActive) main.postDelayed(OperatorActivity.this::startVoice, 260);
                });
            }
            @Override public void onError(String utteranceId) {
                voiceSessionActive = false;
                voiceState("TTS_ERROR");
            }
        });
    }

    private void voiceState(String state) {
        main.post(() -> eval("window.chachaVoiceNativeState && window.chachaVoiceNativeState(" + JSONObject.quote(state) + ");"));
    }

    private void stopSpeech() {
        if (textToSpeech != null) textToSpeech.stop();
    }

    private boolean isAllowed(Uri uri) {
        if (uri == null) return false;
        if (!"https".equalsIgnoreCase(uri.getScheme())) return false;
        if (allowedOrigin.getHost() == null || !allowedOrigin.getHost().equalsIgnoreCase(uri.getHost())) return false;
        return normalizedPort(allowedOrigin) == normalizedPort(uri);
    }

    private int normalizedPort(Uri uri) {
        int port = uri.getPort();
        return port == -1 ? 443 : port;
    }

    private void loadRemoteUi() {
        pageReady = false;
        executor.execute(() -> {
            String uiPath = "/";
            try {
                JSONObject cfg = getJson("/api/v1/app-config");
                int min = cfg.optInt("min_shell_protocol_version", 1);
                if (min > SHELL_PROTOCOL_VERSION) {
                    main.post(() -> showFallbackMessage("Mise à jour native requise", "Cette interface demande un shell Android plus récent."));
                    return;
                }
                String candidate = cfg.optString("ui_path", "/");
                if (candidate.startsWith("/") && !candidate.startsWith("//")) uiPath = candidate;
            } catch (Exception ignored) {
                // Fail soft: the canonical private root is still safe to load.
            }
            final String target = baseUrl + uiPath;
            main.post(() -> webView.loadUrl(target));
        });
    }

    private JSONObject getJson(String path) throws Exception {
        URL url = new URL(baseUrl + path);
        if (!isAllowed(Uri.parse(url.toString()))) throw new SecurityException("LIVE_SHELL_ORIGIN_BLOCKED");
        HttpsURLConnection c = (HttpsURLConnection) url.openConnection();
        c.setRequestMethod("GET");
        c.setConnectTimeout(8000);
        c.setReadTimeout(12000);
        c.setUseCaches(false);
        c.setRequestProperty("Accept", "application/json");
        int code = c.getResponseCode();
        InputStream in = code >= 200 && code < 300 ? c.getInputStream() : c.getErrorStream();
        StringBuilder sb = new StringBuilder();
        if (in != null) {
            try (BufferedReader br = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
                String line;
                while ((line = br.readLine()) != null) sb.append(line);
            }
        }
        c.disconnect();
        if (code < 200 || code >= 300) throw new IllegalStateException("HTTP " + code + " " + sb);
        return new JSONObject(sb.toString());
    }

    private String modeFrom(Intent intent) {
        if (intent == null) return ChaChaWidgetProvider.MODE_TYPE;
        String mode = intent.getStringExtra(ChaChaWidgetProvider.EXTRA_MODE);
        return mode == null ? ChaChaWidgetProvider.MODE_TYPE : mode;
    }

    private void handlePendingMode() {
        if (!pageReady) return;
        String mode = pendingMode;
        pendingMode = ChaChaWidgetProvider.MODE_TYPE;
        if (ChaChaWidgetProvider.MODE_STATUS.equals(mode)) {
            eval("window.chachaSubmit && window.chachaSubmit('Allo');");
        } else if (ChaChaWidgetProvider.MODE_VOICE.equals(mode)) {
            voiceSessionActive = true;
            eval("window.chachaStartVoiceSession && window.chachaStartVoiceSession();");
            main.postDelayed(this::startVoice, 180);
        } else {
            eval("window.chachaSetPrompt && window.chachaSetPrompt('');");
        }
    }

    private void eval(String js) {
        if (pageReady && webView != null) webView.evaluateJavascript(js, null);
    }

    private final class VoiceBridge {
        @JavascriptInterface public void listen() {
            main.post(() -> {
                voiceSessionActive = true;
                stopSpeech();
                startVoice();
            });
        }

        @JavascriptInterface public void speak(String text, boolean continueListening) {
            final String safe = text == null ? "" : text.trim();
            main.post(() -> {
                voiceSessionActive = continueListening;
                if (!textToSpeechReady || textToSpeech == null || safe.isEmpty()) {
                    voiceSessionActive = false;
                    voiceState("TTS_UNAVAILABLE");
                    return;
                }
                textToSpeech.speak(safe, TextToSpeech.QUEUE_FLUSH, null, "chacha-reply-" + System.currentTimeMillis());
            });
        }

        @JavascriptInterface public void stop() {
            main.post(() -> {
                voiceSessionActive = false;
                stopSpeech();
                voiceState("STOPPED");
            });
        }

        @JavascriptInterface public boolean isAvailable() { return textToSpeechReady; }
    }

    private void startVoice() {
        if (voiceRequestInFlight) return;
        stopSpeech();
        voiceRequestInFlight = true;
        voiceState("LISTENING");
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault());
        intent.putExtra(RecognizerIntent.EXTRA_PROMPT, "Demander à ChaCha…");
        try {
            startActivityForResult(intent, VOICE_REQUEST);
        } catch (ActivityNotFoundException e) {
            voiceRequestInFlight = false;
            voiceSessionActive = false;
            voiceState("STT_UNAVAILABLE");
            eval("window.chachaSetPrompt && window.chachaSetPrompt('Dictée indisponible sur ce téléphone');");
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != VOICE_REQUEST) return;
        voiceRequestInFlight = false;
        if (resultCode == RESULT_OK && data != null) {
            ArrayList<String> choices = data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
            if (choices != null && !choices.isEmpty()) {
                voiceState("TRANSCRIPT_READY");
                eval("window.chachaVoiceTranscript && window.chachaVoiceTranscript(" + JSONObject.quote(choices.get(0)) + ");");
                return;
            }
        }
        voiceSessionActive = false;
        voiceState("STOPPED");
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        pendingMode = modeFrom(intent);
        handlePendingMode();
    }

    private void showFallback() {
        showFallbackMessage("ChaCha est momentanément hors ligne", "Vérifie Tailscale puis réessaie. Le widget et l’application restent installés.");
    }

    private void showFallbackMessage(String title, String detail) {
        pageReady = false;
        String html = "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>" +
                "<style>body{font-family:system-ui;background:#111116;color:#fff;margin:0;padding:28px}" +
                ".c{max-width:540px;margin:14vh auto;background:#211e29;border:1px solid #423b50;border-radius:24px;padding:24px}" +
                "h1{font-size:24px}p{color:#b8b2c4;line-height:1.5}a{display:block;text-align:center;margin-top:20px;padding:14px;border-radius:15px;background:#7c5cff;color:white;text-decoration:none;font-weight:800}</style></head>" +
                "<body><div class='c'><div style='font-size:36px'>💨</div><h1>" + escapeHtml(title) + "</h1><p>" + escapeHtml(detail) +
                "</p><a href='chacha://retry'>Réessayer</a></div></body></html>";
        webView.loadDataWithBaseURL(baseUrl + "/", html, "text/html", "UTF-8", null);
    }

    private String escapeHtml(String value) {
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;");
    }

    @Override
    protected void onResume() {
        super.onResume();
        ChaChaWidgetProvider.refreshRemote(this);
        NativeUpdateManager.checkForUpdate(this, baseUrl, getString(R.string.native_update_signing_cert_sha256));
    }

    @Override
    protected void onDestroy() {
        voiceSessionActive = false;
        if (textToSpeech != null) {
            textToSpeech.stop();
            textToSpeech.shutdown();
            textToSpeech = null;
        }
        if (webView != null) {
            webView.stopLoading();
            webView.loadUrl("about:blank");
            webView.destroy();
            webView = null;
        }
        executor.shutdownNow();
        super.onDestroy();
    }
}
