package com.wfgg.chachadev.operator;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.RecognizerIntent;
import android.view.inputmethod.InputMethodManager;
import android.content.Context;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
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
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());

    private EditText input;
    private Button send;
    private Button mic;
    private TextView state;
    private TextView result;
    private String baseUrl;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_operator);
        baseUrl = getString(R.string.operator_base_url);

        input = findViewById(R.id.operator_input);
        send = findViewById(R.id.operator_send);
        mic = findViewById(R.id.operator_mic);
        state = findViewById(R.id.operator_state);
        result = findViewById(R.id.operator_result);

        send.setOnClickListener(v -> submit(input.getText().toString()));
        mic.setOnClickListener(v -> startVoice());

        String mode = getIntent().getStringExtra(ChaChaWidgetProvider.EXTRA_MODE);
        if (ChaChaWidgetProvider.MODE_STATUS.equals(mode)) {
            submit("Allo");
        } else if (ChaChaWidgetProvider.MODE_VOICE.equals(mode)) {
            main.postDelayed(this::startVoice, 180);
        } else {
            main.postDelayed(() -> {
                input.requestFocus();
                InputMethodManager imm = (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
                if (imm != null) imm.showSoftInput(input, InputMethodManager.SHOW_IMPLICIT);
            }, 180);
        }
    }

    private void startVoice() {
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault());
        intent.putExtra(RecognizerIntent.EXTRA_PROMPT, "Demander à ChaCha DEV…");
        try {
            startActivityForResult(intent, VOICE_REQUEST);
        } catch (ActivityNotFoundException e) {
            state.setText("DICTÉE INDISPONIBLE");
            result.setText("Aucun service de reconnaissance vocale n’est disponible sur ce téléphone.");
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == VOICE_REQUEST && resultCode == RESULT_OK && data != null) {
            ArrayList<String> choices = data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
            if (choices != null && !choices.isEmpty()) {
                input.setText(choices.get(0));
                input.setSelection(input.length());
            }
        }
    }

    private void submit(String text) {
        final String trimmed = text == null ? "" : text.trim();
        if (trimmed.isEmpty()) return;
        send.setEnabled(false);
        state.setText("TRANSMISSION");
        result.setText("Envoi au Functional Translator…");
        ChaChaWidgetProvider.updatePrompt(this, "ChaCha DEV • transmission…");

        executor.execute(() -> {
            try {
                JSONObject accepted = postJson("/api/v1/intent", new JSONObject().put("text", trimmed));
                String jobId = accepted.getString("job_id");
                JSONObject job = waitForJob(jobId);
                JSONObject response = job.getJSONObject("response");
                String status = response.optString("status", "OK");
                String next = response.optString("next_action", "");
                String project = response.optString("project_id", "");
                String message = status;
                if (!next.isEmpty()) message += "\n\n" + next;
                if (!project.isEmpty()) message += "\n\nProjet : " + project;
                final String finalMessage = message;
                main.post(() -> {
                    state.setText(status);
                    result.setText(finalMessage);
                    ChaChaWidgetProvider.updatePrompt(OperatorActivity.this, "✓ " + shortText(status + (next.isEmpty() ? "" : " • " + next), 52));
                    send.setEnabled(true);
                });
            } catch (Exception e) {
                String message = friendlyError(e);
                main.post(() -> {
                    state.setText("ERREUR");
                    result.setText(message);
                    ChaChaWidgetProvider.updatePrompt(OperatorActivity.this, "ChaCha DEV • connexion requise");
                    send.setEnabled(true);
                });
            }
        });
    }

    private JSONObject waitForJob(String jobId) throws Exception {
        for (int i = 0; i < 900; i++) {
            Thread.sleep(800);
            JSONObject job = getJson("/api/v1/jobs/" + jobId);
            String s = job.optString("state", "...");
            final String shown = s;
            main.post(() -> state.setText(shown));
            if ("COMPLETE".equals(s)) return job;
            if ("FAILED".equals(s)) throw new IllegalStateException(job.optString("error", "Échec ChaCha DEV"));
        }
        throw new IllegalStateException("Le cerveau central n’a pas produit de receipt dans la fenêtre d’attente.");
    }

    private JSONObject postJson(String path, JSONObject payload) throws Exception {
        HttpsURLConnection c = open(path, "POST");
        c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        byte[] body = payload.toString().getBytes(StandardCharsets.UTF_8);
        c.setFixedLengthStreamingMode(body.length);
        try (OutputStream os = c.getOutputStream()) { os.write(body); }
        return readJson(c);
    }

    private JSONObject getJson(String path) throws Exception {
        return readJson(open(path, "GET"));
    }

    private HttpsURLConnection open(String path, String method) throws Exception {
        URL url = new URL(baseUrl + path);
        HttpsURLConnection c = (HttpsURLConnection) url.openConnection();
        c.setRequestMethod(method);
        c.setConnectTimeout(10000);
        c.setReadTimeout(20000);
        c.setUseCaches(false);
        c.setRequestProperty("Accept", "application/json");
        if ("POST".equals(method)) c.setDoOutput(true);
        return c;
    }

    private JSONObject readJson(HttpURLConnection c) throws Exception {
        int code = c.getResponseCode();
        InputStream in = code >= 200 && code < 300 ? c.getInputStream() : c.getErrorStream();
        StringBuilder sb = new StringBuilder();
        if (in != null) {
            try (BufferedReader br = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
                String line;
                while ((line = br.readLine()) != null) sb.append(line);
            }
        }
        if (code == 403) throw new SecurityException("TAILSCALE_IDENTITY_REQUIRED");
        if (code < 200 || code >= 300) throw new IllegalStateException("HTTP " + code + " " + sb);
        return new JSONObject(sb.toString());
    }

    private String friendlyError(Exception e) {
        String m = e.getMessage() == null ? e.toString() : e.getMessage();
        if (m.contains("TAILSCALE") || m.contains("Unable to resolve host") || m.contains("Connect")) {
            return "Connexion privée indisponible. Ouvre Tailscale et vérifie que le téléphone est connecté à ton tailnet, puis réessaie.";
        }
        return m;
    }

    private static String shortText(String text, int max) {
        if (text.length() <= max) return text;
        return text.substring(0, Math.max(1, max - 1)) + "…";
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        executor.shutdownNow();
    }
}
