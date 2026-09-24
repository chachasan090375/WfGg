plugins {
    id("com.android.application")
}

android {
    namespace = "com.wfgg.chachadev.operator"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.wfgg.chachadev.operator"
        minSdk = 26
        targetSdk = 36
        versionCode = 3
        versionName = "0.3.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
