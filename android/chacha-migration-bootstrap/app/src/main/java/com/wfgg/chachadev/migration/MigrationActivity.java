package com.wfgg.chachadev.migration;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MigrationActivity extends Activity {
    private static final String TARGET_PACKAGE = "com.wfgg.chachadev.operator";
    private static final long TARGET_VERSION_CODE = 6L;
    private static final String TARGET_VERSION_NAME = "0.6.0";
    private static final String TARGET_APK_URL =
            "https://chachavps.tail3ab05a.ts.net:8445/chacha-jai-pete-v0.6.0-200cbe417be3.apk";
    private static final String TARGET_APK_SHA256 =
            "b5088f7965c56b8298e88812ba73f7630dffdf71937bf3bd2e574531c967428e";
    private static final String TARGET_CERT_SHA256 =
            "3a39f13de1191aec28526d5d8e7c9b490723d514b8dd87e5cb30aaa86a6bff88";

    private static final int REQ_UNINSTALL = 7001;
    private static final int REQ_UNKNOWN_SOURCES = 7002;
    private static final String ACTION_INSTALL_STATUS =
            "com.wfgg.chachadev.migration.INSTALL_STATUS";

    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private TextView title;
    private TextView status;
    private TextView detail;
    private ProgressBar progress;
    private Button primary;
    private Button secondary;
    private boolean firstResume = true;
    private boolean installStarted = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildUi();
        handleInstallStatus(getIntent());
        if (!ACTION_INSTALL_STATUS.equals(getIntent().getAction())) {
            primary.post(this::startMigration);
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleInstallStatus(intent);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (firstResume) {
            firstResume = false;
            return;
        }
        String phase = phase();
        if ("WAIT_INSTALL_PERMISSION".equals(phase) &&
                Build.VERSION.SDK_INT >= 26 &&
                getPackageManager().canRequestPackageInstalls()) {
            setPhase("READY_TO_INSTALL");
            installDownloadedApk();
        } else if ("WAIT_UNINSTALL".equals(phase) && !isTargetInstalled()) {
            setPhase("DOWNLOAD");
            downloadAndInstall();
        }
    }

    @Override
    protected void onDestroy() {
        io.shutdownNow();
        super.onDestroy();
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(dp(28), dp(44), dp(28), dp(28));
        root.setBackgroundColor(Color.rgb(247, 244, 251));

        title = new TextView(this);
        title.setText("ChaCha Migration ✨");
        title.setTextSize(28);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setTextColor(Color.rgb(78, 42, 132));
        root.addView(title, fullWidth());

        TextView subtitle = new TextView(this);
        subtitle.setText("Une seule bascule vers la version signée permanente");
        subtitle.setTextSize(16);
        subtitle.setTextColor(Color.rgb(75, 67, 88));
        subtitle.setPadding(0, dp(10), 0, dp(26));
        root.addView(subtitle, fullWidth());

        status = new TextView(this);
        status.setText("Préparation…");
        status.setTextSize(20);
        status.setTypeface(Typeface.DEFAULT_BOLD);
        status.setTextColor(Color.rgb(38, 31, 48));
        root.addView(status, fullWidth());

        detail = new TextView(this);
        detail.setText("Le migrateur va vérifier l’installation actuelle.");
        detail.setTextSize(15);
        detail.setTextColor(Color.rgb(86, 78, 96));
        detail.setPadding(0, dp(8), 0, dp(20));
        root.addView(detail, fullWidth());

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        progress.setProgress(5);
        root.addView(progress, fullWidth());

        primary = new Button(this);
        primary.setText("Démarrer la migration");
        primary.setAllCaps(false);
        primary.setOnClickListener(v -> startMigration());
        LinearLayout.LayoutParams bp = fullWidth();
        bp.topMargin = dp(24);
        root.addView(primary, bp);

        secondary = new Button(this);
        secondary.setText("Fermer");
        secondary.setAllCaps(false);
        secondary.setOnClickListener(v -> finish());
        LinearLayout.LayoutParams sp = fullWidth();
        sp.topMargin = dp(8);
        root.addView(secondary, sp);

        setContentView(root);
    }

    private LinearLayout.LayoutParams fullWidth() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private void startMigration() {
        primary.setEnabled(false);
        secondary.setEnabled(false);
        setStatus("Vérification de ChaCha…",
                "Je contrôle la signature de la version déjà installée.", 12);

        io.execute(() -> {
            String installedCert = installedTargetCertificate();
            runOnUiThread(() -> {
                if (installedCert == null) {
                    setPhase("DOWNLOAD");
                    downloadAndInstall();
                } else if (TARGET_CERT_SHA256.equals(installedCert)) {
                    setStatus("Bonne identité détectée",
                            "ChaCha utilise déjà la clé release permanente. Aucune désinstallation n’est nécessaire.", 30);
                    setPhase("DOWNLOAD");
                    downloadAndInstall();
                } else {
                    setStatus("Ancienne version détectée",
                            "Android va demander la confirmation pour la désinstaller. C’est nécessaire car sa clé de signature est différente.", 25);
                    requestOldVersionUninstall();
                }
            });
        });
    }

    private void requestOldVersionUninstall() {
        try {
            Intent uninstall = new Intent(
                    Intent.ACTION_UNINSTALL_PACKAGE,
                    Uri.parse("package:" + TARGET_PACKAGE));
            uninstall.putExtra(Intent.EXTRA_RETURN_RESULT, true);
            setPhase("WAIT_UNINSTALL");
            startActivityForResult(uninstall, REQ_UNINSTALL);
        } catch (Exception e) {
            fail("Impossible d’ouvrir la désinstallation Android", e);
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_UNINSTALL) {
            if (!isTargetInstalled()) {
                setPhase("DOWNLOAD");
                downloadAndInstall();
            } else {
                retry("Désinstallation annulée",
                        "L’ancienne version est toujours installée. Appuie pour reprendre.");
            }
        } else if (requestCode == REQ_UNKNOWN_SOURCES) {
            if (Build.VERSION.SDK_INT < 26 || getPackageManager().canRequestPackageInstalls()) {
                setPhase("READY_TO_INSTALL");
                installDownloadedApk();
            } else {
                retry("Autorisation nécessaire",
                        "Autorise « Installer des applis inconnues » pour ChaCha Migration, puis reprends.");
            }
        }
    }

    private void downloadAndInstall() {
        setStatus("Téléchargement sécurisé…",
                "ChaCha 0.6.0 arrive depuis ton canal privé Tailscale.", 42);
        primary.setEnabled(false);

        io.execute(() -> {
            try {
                File apk = downloadedApk();
                if (!apk.isFile() || !TARGET_APK_SHA256.equals(sha256(apk))) {
                    download(apk);
                }
                verifyArchive(apk);
                runOnUiThread(() -> {
                    setStatus("APK vérifié ✅",
                            "SHA-256, package, version et certificat release sont conformes.", 72);
                    ensureInstallPermissionThenInstall();
                });
            } catch (Exception e) {
                runOnUiThread(() -> fail("Téléchargement ou vérification impossible", e));
            }
        });
    }

    private void download(File output) throws Exception {
        File tmp = new File(output.getParentFile(), output.getName() + ".part");
        if (tmp.exists() && !tmp.delete()) {
            throw new IllegalStateException("TEMP_DELETE_FAILED");
        }
        HttpURLConnection c = (HttpURLConnection) new URL(TARGET_APK_URL).openConnection();
        c.setConnectTimeout(15000);
        c.setReadTimeout(45000);
        c.setInstanceFollowRedirects(true);
        c.setRequestProperty("User-Agent", "ChaCha-Migration/1.0");
        int code = c.getResponseCode();
        if (code != 200) throw new IllegalStateException("HTTP_" + code);
        try (InputStream in = c.getInputStream();
             OutputStream out = new FileOutputStream(tmp)) {
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) >= 0) out.write(buf, 0, n);
        } finally {
            c.disconnect();
        }
        if (!TARGET_APK_SHA256.equals(sha256(tmp))) {
            tmp.delete();
            throw new SecurityException("APK_SHA256_MISMATCH");
        }
        if (output.exists() && !output.delete()) {
            throw new IllegalStateException("OLD_APK_DELETE_FAILED");
        }
        if (!tmp.renameTo(output)) {
            throw new IllegalStateException("APK_ATOMIC_RENAME_FAILED");
        }
    }

    private void verifyArchive(File apk) throws Exception {
        PackageManager pm = getPackageManager();
        int flags = Build.VERSION.SDK_INT >= 28
                ? PackageManager.GET_SIGNING_CERTIFICATES
                : PackageManager.GET_SIGNATURES;
        PackageInfo pi = pm.getPackageArchiveInfo(apk.getAbsolutePath(), flags);
        if (pi == null) throw new SecurityException("APK_PACKAGE_INFO_MISSING");
        if (!TARGET_PACKAGE.equals(pi.packageName)) {
            throw new SecurityException("APK_PACKAGE_MISMATCH:" + pi.packageName);
        }
        long version = Build.VERSION.SDK_INT >= 28 ? pi.getLongVersionCode() : pi.versionCode;
        if (version != TARGET_VERSION_CODE) {
            throw new SecurityException("APK_VERSION_MISMATCH:" + version);
        }
        String cert = certificateDigest(pi);
        if (!TARGET_CERT_SHA256.equals(cert)) {
            throw new SecurityException("APK_CERT_MISMATCH:" + cert);
        }
    }

    private void ensureInstallPermissionThenInstall() {
        if (Build.VERSION.SDK_INT >= 26 && !getPackageManager().canRequestPackageInstalls()) {
            setStatus("Autorisation Android requise",
                    "Active « Autoriser depuis cette source » pour ChaCha Migration.", 78);
            setPhase("WAIT_INSTALL_PERMISSION");
            Intent settings = new Intent(
                    Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + getPackageName()));
            startActivityForResult(settings, REQ_UNKNOWN_SOURCES);
            return;
        }
        setPhase("READY_TO_INSTALL");
        installDownloadedApk();
    }

    private void installDownloadedApk() {
        if (installStarted || "INSTALL_COMMITTED".equals(phase())) return;
        installStarted = true;
        File apk = downloadedApk();
        if (!apk.isFile()) {
            installStarted = false;
            retry("APK introuvable", "Relance la migration pour le télécharger à nouveau.");
            return;
        }
        setStatus("Installation de ChaCha…",
                "Android va afficher sa confirmation d’installation.", 86);

        io.execute(() -> {
            try {
                verifyArchive(apk);
                PackageInstaller installer = getPackageManager().getPackageInstaller();
                PackageInstaller.SessionParams params =
                        new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                params.setAppPackageName(TARGET_PACKAGE);
                int sessionId = installer.createSession(params);
                try (PackageInstaller.Session session = installer.openSession(sessionId);
                     InputStream in = new FileInputStream(apk);
                     OutputStream out = session.openWrite("base.apk", 0, apk.length())) {
                    byte[] buf = new byte[65536];
                    int n;
                    while ((n = in.read(buf)) >= 0) out.write(buf, 0, n);
                    session.fsync(out);

                    Intent callback = new Intent(this, MigrationActivity.class);
                    callback.setAction(ACTION_INSTALL_STATUS);
                    callback.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
                    PendingIntent pending = PendingIntent.getActivity(
                            this,
                            sessionId,
                            callback,
                            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_MUTABLE);
                    setPhase("INSTALL_COMMITTED");
                    session.commit(pending.getIntentSender());
                }
            } catch (Exception e) {
                runOnUiThread(() -> fail("Installation impossible", e));
            }
        });
    }

    private void handleInstallStatus(Intent intent) {
        if (intent == null || !ACTION_INSTALL_STATUS.equals(intent.getAction())) return;
        int installStatus = intent.getIntExtra(
                PackageInstaller.EXTRA_STATUS,
                PackageInstaller.STATUS_FAILURE);

        if (installStatus == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            setStatus("Confirmation Android",
                    "Valide maintenant l’installation de ChaCha 0.6.0.", 92);
            Intent confirm = intent.getParcelableExtra(Intent.EXTRA_INTENT);
            if (confirm != null) {
                confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                startActivity(confirm);
            } else {
                retry("Confirmation indisponible", "Relance l’installation.");
            }
            return;
        }

        if (installStatus == PackageInstaller.STATUS_SUCCESS) {
            setPhase("DONE");
            setStatus("Migration terminée 🎉",
                    "ChaCha 0.6.0 est maintenant installée avec sa clé release permanente. Si Android a retiré l’ancien widget pendant la désinstallation, rajoute une seule fois « ChaCha j’ai pété » à l’écran d’accueil.", 100);
            primary.setEnabled(true);
            primary.setText("Ouvrir ChaCha");
            primary.setOnClickListener(v -> launchTarget());
            secondary.setEnabled(true);
            secondary.setText("Supprimer ChaCha Migration");
            secondary.setOnClickListener(v -> requestSelfUninstall());
            return;
        }

        String message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
        retry("Installation non terminée",
                message == null ? "Android n’a pas installé ChaCha. Tu peux reprendre." : message);
    }

    private void launchTarget() {
        Intent launch = getPackageManager().getLaunchIntentForPackage(TARGET_PACKAGE);
        if (launch != null) startActivity(launch);
    }

    private void requestSelfUninstall() {
        Intent uninstall = new Intent(
                Intent.ACTION_UNINSTALL_PACKAGE,
                Uri.parse("package:" + getPackageName()));
        startActivity(uninstall);
    }

    private boolean isTargetInstalled() {
        try {
            getPackageManager().getPackageInfo(TARGET_PACKAGE, 0);
            return true;
        } catch (PackageManager.NameNotFoundException e) {
            return false;
        }
    }

    private String installedTargetCertificate() {
        try {
            PackageManager pm = getPackageManager();
            PackageInfo pi;
            if (Build.VERSION.SDK_INT >= 33) {
                pi = pm.getPackageInfo(
                        TARGET_PACKAGE,
                        PackageManager.PackageInfoFlags.of(PackageManager.GET_SIGNING_CERTIFICATES));
            } else {
                int flags = Build.VERSION.SDK_INT >= 28
                        ? PackageManager.GET_SIGNING_CERTIFICATES
                        : PackageManager.GET_SIGNATURES;
                pi = pm.getPackageInfo(TARGET_PACKAGE, flags);
            }
            return certificateDigest(pi);
        } catch (Exception e) {
            return null;
        }
    }

    private String certificateDigest(PackageInfo pi) throws Exception {
        Signature[] signatures;
        if (Build.VERSION.SDK_INT >= 28 && pi.signingInfo != null) {
            signatures = pi.signingInfo.hasMultipleSigners()
                    ? pi.signingInfo.getApkContentsSigners()
                    : pi.signingInfo.getSigningCertificateHistory();
        } else {
            signatures = pi.signatures;
        }
        if (signatures == null || signatures.length == 0) {
            throw new SecurityException("SIGNING_CERT_MISSING");
        }
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        return hex(md.digest(signatures[0].toByteArray()));
    }

    private File downloadedApk() {
        File dir = new File(getFilesDir(), "migration");
        if (!dir.exists() && !dir.mkdirs()) {
            throw new IllegalStateException("MIGRATION_DIR_CREATE_FAILED");
        }
        return new File(dir, "chacha-0.6.0.apk");
    }

    private String sha256(File file) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        try (InputStream in = new FileInputStream(file)) {
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) >= 0) md.update(buf, 0, n);
        }
        return hex(md.digest());
    }

    private String hex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) sb.append(String.format(Locale.ROOT, "%02x", b));
        return sb.toString();
    }

    private void setStatus(String headline, String body, int percent) {
        status.setText(headline);
        detail.setText(body);
        progress.setProgress(percent);
    }

    private void retry(String headline, String body) {
        installStarted = false;
        setStatus(headline, body, Math.max(20, progress.getProgress()));
        primary.setEnabled(true);
        primary.setText("Reprendre");
        primary.setOnClickListener(v -> startMigration());
        secondary.setEnabled(true);
        secondary.setText("Fermer");
        secondary.setOnClickListener(v -> finish());
    }

    private void fail(String headline, Exception e) {
        retry(headline, e.getClass().getSimpleName() + " · " + String.valueOf(e.getMessage()));
    }

    private void setPhase(String value) {
        getSharedPreferences("migration", MODE_PRIVATE)
                .edit().putString("phase", value).apply();
    }

    private String phase() {
        return getSharedPreferences("migration", MODE_PRIVATE)
                .getString("phase", "START");
    }
}
