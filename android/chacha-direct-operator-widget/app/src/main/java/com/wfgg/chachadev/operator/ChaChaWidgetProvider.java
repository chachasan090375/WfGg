package com.wfgg.chachadev.operator;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

public class ChaChaWidgetProvider extends AppWidgetProvider {
    public static final String EXTRA_MODE = "mode";
    public static final String MODE_TYPE = "type";
    public static final String MODE_VOICE = "voice";
    public static final String MODE_STATUS = "status";

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        for (int id : ids) {
            RemoteViews views = buildViews(context, id, context.getString(R.string.widget_prompt), 86, 0, "PRÊT");
            manager.updateAppWidget(id, views);
        }
    }

    private static RemoteViews buildViews(Context context, int widgetId, String prompt, int globalPercent, int workPercent, String state) {
        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_chacha);
        views.setTextViewText(R.id.widget_prompt, prompt);
        views.setTextViewText(R.id.widget_global, globalPercent + "%");
        views.setProgressBar(R.id.widget_global_progress, 100, Math.max(0, Math.min(100, globalPercent)), false);
        views.setProgressBar(R.id.widget_work_progress, 100, Math.max(0, Math.min(100, workPercent)), false);
        views.setTextViewText(R.id.widget_status, "ERREUR".equals(state) ? "!" : ("COMPLETE".equals(state) ? "✓" : "●"));
        views.setOnClickPendingIntent(R.id.widget_prompt, activityIntent(context, widgetId * 10 + 1, MODE_TYPE));
        views.setOnClickPendingIntent(R.id.widget_mic, activityIntent(context, widgetId * 10 + 2, MODE_VOICE));
        views.setOnClickPendingIntent(R.id.widget_status, activityIntent(context, widgetId * 10 + 3, MODE_STATUS));
        return views;
    }

    private static PendingIntent activityIntent(Context context, int requestCode, String mode) {
        Intent intent = new Intent(context, OperatorActivity.class);
        intent.putExtra(EXTRA_MODE, mode);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        return PendingIntent.getActivity(
                context,
                requestCode,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
    }

    public static void updatePrompt(Context context, String prompt) {
        updateContext(context, 86, 0, prompt, "PRÊT");
    }

    public static void updateContext(Context context, int globalPercent, int workPercent, String message, String state) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        ComponentName component = new ComponentName(context, ChaChaWidgetProvider.class);
        int[] ids = manager.getAppWidgetIds(component);
        for (int id : ids) {
            manager.updateAppWidget(id, buildViews(context, id, message, globalPercent, workPercent, state));
        }
    }
}
