package com.wfgg.chachadev.operator;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;

import javax.net.ssl.HttpsURLConnection;

public final class NativeUpdateManager {
    private NativeUpdateManager() {}

    public static void checkForUpdate(Activity activity, String baseUrl, String pinnedCertSha256) {
        new Thread(() -> {
            try {
                JSONObject manifest = getJson(baseUrl + "/api/v1/native-update");
                if (!"chacha.dev/android-native-update/v1".equals(manifest.optString("schema"))) return;
                if (!"AVAILABLE".equals(manifest.optString("status"))) return;
                if (!activity.getPackageName().equals(manifest.optString("package_id"))) return;
                long current = currentVersionCode(activity);
                long offered = manifest.optLong("version_code", 0);
                if (offered <= current) return;
                String cert = normalizeHex(manifest.optString("signing_cert_sha256", ""));
                if (!normalizeHex(pinnedCertSha256).equals(cert)) return;
                String apkPath = manifest.optString("apk_path", "");
                String sha256 = normalizeHex(manifest.optString("apk_sha256", ""));
                if (!apkPath.startsWith("/native-updates/") || apkPath.contains("..") || sha256.length() != 64) return;
                String versionName = manifest.optString("version_name", String.valueOf(offered));
                activity.runOnUiThread(() -> showPrompt(activity, baseUrl, apkPath, sha256, cert, offered, versionName));
            } catch (Exception ignored) {
                // Native updates are optional; Live UI remains operational on any check failure.
            }
        }, "chacha-native-update-check").start();
    }

    private static void showPrompt(Activity activity, String baseUrl, String apkPath, String sha256,
                                   String certSha256, long versionCode, String versionName) {
        if (activity.isFinishing()) return;
        new AlertDialog.Builder(activity)
                .setTitle("Mise à jour ChaCha prête")
                .setMessage("Version " + versionName + " disponible. Elle conserve la même application et la même signature.")
                .setNegativeButton("Plus tard", null)
                .setPositiveButton("Installer", (d, w) ->
                        new Thread(() -> downloadVerifyAndInstall(activity, baseUrl, apkPath, sha256, certSha256, versionCode),
                                "chacha-native-update-install").start())
                .show();
    }

    private static void downloadVerifyAndInstall(Activity activity, String baseUrl, String apkPath,
                                                 String expectedSha, String expectedCert, long offeredVersion) {
        File apk = null;
        try {
            Uri base = Uri.parse(baseUrl);
            Uri target = Uri.parse(baseUrl + apkPath);
            if (!"https".equalsIgnoreCase(target.getScheme()) ||
                    !safeEquals(base.getHost(), target.getHost()) ||
                    normalizedPort(base) != normalizedPort(target)) {
                throw new SecurityException("NATIVE_UPDATE_ORIGIN_BLOCKED");
            }

            File dir = new File(activity.getCacheDir(), "native-updates");
            if (!dir.exists() && !dir.mkdirs()) throw new IllegalStateException("UPDATE_CACHE_CREATE_FAILED");
            apk = new File(dir, "chacha-update-" + offeredVersion + ".apk");

            HttpsURLConnection c = (HttpsURLConnection) new URL(target.toString()).openConnection();
            c.setRequestMethod("GET");
            c.setConnectTimeout(10000);
            c.setReadTimeout(60000);
            c.setUseCaches(false);
            int code = c.getResponseCode();
            if (code < 200 || code >= 300) throw new IllegalStateException("HTTP_" + code);
            try (InputStream in = c.getInputStream(); OutputStream out = new FileOutputStream(apk)) {
                byte[] buf = new byte[64 * 1024];
                for (int n; (n = in.read(buf)) >= 0;) if (n > 0) out.write(buf, 0, n);
            } finally {
                c.disconnect();
            }

            if (!normalizeHex(expectedSha).equals(sha256(apk))) throw new SecurityException("APK_SHA256_MISMATCH");
            PackageInfo archive = archiveInfo(activity, apk);
            if (archive == null || !activity.getPackageName().equals(archive.packageName)) {
                throw new SecurityException("APK_PACKAGE_MISMATCH");
            }
            long archiveVersion = Build.VERSION.SDK_INT >= 28 ? archive.getLongVersionCode() : archive.versionCode;
            if (archiveVersion != offeredVersion || archiveVersion <= currentVersionCode(activity)) {
                throw new SecurityException("APK_VERSION_INVALID");
            }
            String archiveCert = signingCertSha256(archive);
            if (!normalizeHex(expectedCert).equals(archiveCert)) throw new SecurityException("APK_SIGNING_CERT_MISMATCH");

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
                    !activity.getPackageManager().canRequestPackageInstalls()) {
                Intent settings = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        Uri.parse("package:" + activity.getPackageName()));
                activity.runOnUiThread(() -> {
                    Toast.makeText(activity, "Autorise ChaCha à installer sa mise à jour, puis relance l’installation.", Toast.LENGTH_LONG).show();
                    activity.startActivity(settings);
                });
                return;
            }
            install(activity, apk);
        } catch (Exception e) {
            if (apk != null) apk.delete();
            String message = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            activity.runOnUiThread(() -> Toast.makeText(activity, "Mise à jour refusée : " + message, Toast.LENGTH_LONG).show());
        }
    }

    private static void install(Activity activity, File apk) throws Exception {
        PackageInstaller installer = activity.getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        params.setAppPackageName(activity.getPackageName());
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED);
        }
        int sessionId = installer.createSession(params);
        try (PackageInstaller.Session session = installer.openSession(sessionId)) {
            try (InputStream in = new FileInputStream(apk);
                 OutputStream out = session.openWrite("base.apk", 0, apk.length())) {
                byte[] buf = new byte[64 * 1024];
                for (int n; (n = in.read(buf)) >= 0;) if (n > 0) out.write(buf, 0, n);
                session.fsync(out);
            }

            // All session streams must be closed before commit().
            Intent status = new Intent(activity, NativeUpdateReceiver.class);
            status.setAction("com.wfgg.chachadev.operator.NATIVE_UPDATE_STATUS");
            PendingIntent pending = PendingIntent.getBroadcast(activity, sessionId, status,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_MUTABLE);
            session.commit(pending.getIntentSender());
        }
    }

    private static PackageInfo archiveInfo(Activity activity, File apk) {
        PackageManager pm = activity.getPackageManager();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            return pm.getPackageArchiveInfo(apk.getAbsolutePath(), PackageManager.GET_SIGNING_CERTIFICATES);
        }
        return pm.getPackageArchiveInfo(apk.getAbsolutePath(), PackageManager.GET_SIGNATURES);
    }

    private static String signingCertSha256(PackageInfo info) throws Exception {
        Signature[] signatures;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P && info.signingInfo != null) {
            signatures = info.signingInfo.getApkContentsSigners();
        } else {
            signatures = info.signatures;
        }
        if (signatures == null || signatures.length != 1) throw new SecurityException("APK_SIGNER_COUNT_INVALID");
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        return hex(md.digest(signatures[0].toByteArray()));
    }

    private static long currentVersionCode(Activity activity) throws Exception {
        PackageInfo p = activity.getPackageManager().getPackageInfo(activity.getPackageName(), 0);
        return Build.VERSION.SDK_INT >= 28 ? p.getLongVersionCode() : p.versionCode;
    }

    private static JSONObject getJson(String url) throws Exception {
        HttpsURLConnection c = (HttpsURLConnection) new URL(url).openConnection();
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
        if (code < 200 || code >= 300) throw new IllegalStateException("HTTP_" + code);
        return new JSONObject(sb.toString());
    }

    private static String sha256(File file) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        try (InputStream in = new FileInputStream(file)) {
            byte[] buf = new byte[64 * 1024];
            for (int n; (n = in.read(buf)) >= 0;) if (n > 0) md.update(buf, 0, n);
        }
        return hex(md.digest());
    }

    private static String hex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) sb.append(String.format(Locale.ROOT, "%02x", b & 0xff));
        return sb.toString();
    }

    private static String normalizeHex(String value) {
        return value == null ? "" : value.replace(":", "").replace(" ", "").toLowerCase(Locale.ROOT);
    }

    private static boolean safeEquals(String a, String b) {
        return a != null && b != null && a.equalsIgnoreCase(b);
    }

    private static int normalizedPort(Uri uri) {
        int p = uri.getPort();
        return p == -1 ? 443 : p;
    }
}
