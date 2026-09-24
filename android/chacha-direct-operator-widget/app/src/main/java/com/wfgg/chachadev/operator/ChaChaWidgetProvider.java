package com.wfgg.chachadev.operator;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.appwidget.AppWidgetProviderInfo;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URL;
import java.nio.charset.StandardCharsets;

import javax.net.ssl.HttpsURLConnection;

public class ChaChaWidgetProvider extends AppWidgetProvider {
    public static final String EXTRA_MODE = "mode";
    public static final String MODE_TYPE = "type";
    public static final String MODE_VOICE = "voice";
    public static final String MODE_STATUS = "status";

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        String title = "💨  ChaCha j’ai pété";
        for (int id : ids) {
            manager.updateAppWidget(id, buildViews(context, id, title, context.getString(R.string.widget_prompt), 86, 0, "PRÊT"));
        }
        refreshRemote(context);
    }

    private static RemoteViews buildViews(Context context, int widgetId, String title, String prompt,
                                          int globalPercent, int workPercent, String state) {
        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_chacha);
        views.setTextViewText(R.id.widget_title, title);
        views.setTextViewText(R.id.widget_prompt, prompt);
        views.setTextViewText(R.id.widget_global, globalPercent + "%");
        views.setProgressBar(R.id.widget_global_progress, 100, clamp(globalPercent), false);
        views.setProgressBar(R.id.widget_work_progress, 100, clamp(workPercent), false);
        views.setTextViewText(R.id.widget_status, "ERROR".equals(state) || "ERREUR".equals(state) ? "!" :
                ("COMPLETE".equals(state) ? "✓" : "●"));
        views.setOnClickPendingIntent(R.id.widget_prompt, activityIntent(context, widgetId * 10 + 1, MODE_TYPE));
        views.setOnClickPendingIntent(R.id.widget_mic, activityIntent(context, widgetId * 10 + 2, MODE_VOICE));
        views.setOnClickPendingIntent(R.id.widget_status, activityIntent(context, widgetId * 10 + 3, MODE_STATUS));
        return views;
    }

    private static int clamp(int v) {
        return Math.max(0, Math.min(100, v));
    }

    private static PendingIntent activityIntent(Context context, int requestCode, String mode) {
        Intent intent = new Intent(context, OperatorActivity.class);
        intent.putExtra(EXTRA_MODE, mode);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        return PendingIntent.getActivity(
                context, requestCode, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
    }

    public static void updatePrompt(Context context, String prompt) {
        updateContext(context, 86, 0, prompt, "PRÊT");
    }

    public static void updateContext(Context context, int globalPercent, int workPercent, String message, String state) {
        updateAll(context, "💨  ChaCha j’ai pété", globalPercent, workPercent, message, state);
    }

    public static void refreshRemote(Context context) {
        Context app = context.getApplicationContext();
        new Thread(() -> {
            String title = "💨  ChaCha j’ai pété";
            String idlePrompt = app.getString(R.string.widget_prompt);
            int global = 86;
            int work = 0;
            String state = "IDLE";
            String message = idlePrompt;
            try {
                String base = app.getString(R.string.operator_base_url);
                JSONObject cfg = getJson(base + "/api/v1/app-config");
                JSONObject widget = cfg.optJSONObject("widget");
                if (widget != null) {
                    title = widget.optString("title", title);
                    idlePrompt = widget.optString("idle_prompt", idlePrompt);
                    global = widget.optInt("global_maturity_fallback", global);
                }
                JSONObject progress = getJson(base + "/api/v1/progress");
                global = progress.optInt("platform_maturity_percent", global);
                work = progress.optInt("active_work_percent", 0);
                state = progress.optString("status", "IDLE");
                String headline = progress.optString("headline", "");
                message = headline.isEmpty() || "IDLE".equals(state) ? idlePrompt : headline;
            } catch (Exception ignored) {
                // Fail soft: keep the last safe local defaults.
            }
            updateAll(app, title, global, work, message, state);
        }, "chacha-widget-refresh").start();
    }

    private static JSONObject getJson(String url) throws Exception {
        HttpsURLConnection c = (HttpsURLConnection) new URL(url).openConnection();
        c.setRequestMethod("GET");
        c.setConnectTimeout(7000);
        c.setReadTimeout(10000);
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
        if (code < 200 || code >= 300) throw new IllegalStateException("HTTP " + code);
        return new JSONObject(sb.toString());
    }

    private static void updateAll(Context context, String title, int global, int work, String message, String state) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        ComponentName component = new ComponentName(context, ChaChaWidgetProvider.class);
        int[] ids = manager.getAppWidgetIds(component);
        for (int id : ids) {
            manager.updateAppWidget(id, buildViews(context, id, title, message, global, work, state));
        }
    }
}
